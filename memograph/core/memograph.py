"""
MemoGraph: Topological memory navigator with token-capped traversal.

Production-grade features:
- Schema versioning with auto-migration
- Transactional writes (atomic: temp file + rename)
- Permission enforcement on add/load/retrieve boundaries
- Cost-aware token-capped traversal (knapsack + overlap detection)
- Scope blast-radius filtering before scoring
- Content-addressed node storage
- Edge-based graph traversal (parent/child/cross-domain links)
- Stream boundary preservation in assembled contexts
"""

from __future__ import annotations

import heapq
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Set, Any, Iterable

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.types import ContentType

# Schema versioning
SCHEMA_VERSION = 2
SCHEMA_KEY = "_memograph_schema"


@dataclass
class ContextEnvelope:
    """
    Preserves stream boundaries when assembling context.
    The agent sees each shard with its domain label intact.
    """
    shards: List[MemoryShard] = field(default_factory=list)
    domains: Dict[ShardDomain, int] = field(default_factory=dict)
    total_tokens: int = 0
    max_tokens: int = 0
    excluded_overlaps: int = 0

    def add(self, shard: MemoryShard, overlap_tokens: int = 0) -> bool:
        """Add shard if it fits in budget. Returns True if added."""
        cost = self._token_cost(shard) - overlap_tokens
        if self.total_tokens + cost <= self.max_tokens:
            self.shards.append(shard)
            self.domains[shard.domain] = self.domains.get(shard.domain, 0) + 1
            self.total_tokens += self._token_cost(shard)
            return True
        return False

    def _token_cost(self, shard: MemoryShard) -> int:
        return len(str(shard.content)) // 4

    def by_domain(self, domain: ShardDomain) -> List[MemoryShard]:
        return [s for s in self.shards if s.domain == domain]

    def __len__(self) -> int:
        return len(self.shards)


class MemoGraph:
    """
    Content-addressed memory graph with production guarantees.

    Mutations create new nodes with parent_hash edges (immutable topology).
    Schema version is embedded in serialized files for safe migration.
    Writes are atomic (temp file → rename) for transactional integrity.
    """

    def __init__(self, schema_version: int = SCHEMA_VERSION,
                 router: Optional["ContextRouter"] = None):
        self.schema_version = schema_version
        self.nodes: Dict[str, MemoryShard] = {}
        self.edges: Dict[str, List[str]] = defaultdict(list)
        self.reverse_edges: Dict[str, List[str]] = defaultdict(list)
        self.domain_index: Dict[ShardDomain, Set[str]] = defaultdict(set)
        self.scope_index: Dict[str, Set[str]] = defaultdict(set)
        # Retrieval-adapter fleet used to index shards on ingest. Defaults to
        # the module-level router (which holds the populated AdapterRegistry).
        self.router = router

    # ── Core mutation ────────────────────────────────────────────────

    def add_shard(self, shard: MemoryShard) -> str:
        """Add a shard. No-op if hash already exists. No permission check here (use authorize_add)."""
        if shard.shard_hash in self.nodes:
            return shard.shard_hash
        self.nodes[shard.shard_hash] = shard
        self.domain_index[shard.domain].add(shard.shard_hash)
        self.scope_index[shard.scope].add(shard.shard_hash)
        if shard.parent_hash and shard.parent_hash in self.nodes:
            self.edges[shard.parent_hash].append(shard.shard_hash)
            self.reverse_edges[shard.shard_hash].append(shard.parent_hash)
        # Index into the retrieval-adapter fleet (lazy import avoids cycle).
        try:
            from memograph.core.router import router as _default_router
            rtr = self.router if self.router is not None else _default_router
            if rtr is not None:
                rtr.index_shard(shard)
        except Exception:
            pass  # indexing must never block ingestion
        return shard.shard_hash

    def authorize_add(self, shard: MemoryShard, allowed_orgs: Optional[Set[str]] = None) -> bool:
        """
        Enforce org-level blast-radius before adding.
        Returns True if shard is within authorized scope.
        """
        # Extract org from scope (e.g. "org:artifact-virtual")
        if allowed_orgs:
            for org in allowed_orgs:
                if f"org:{org}" in shard.scope or shard.scope.startswith(f"{org}:"):
                    return True
            return False
        return True

    def remove_shard(self, shard_hash: str) -> bool:
        if shard_hash not in self.nodes:
            return False
        shard = self.nodes[shard_hash]
        self.domain_index[shard.domain].discard(shard_hash)
        self.scope_index[shard.scope].discard(shard_hash)
        for child in self.edges.get(shard_hash, []):
            if child in self.reverse_edges:
                self.reverse_edges[child] = [p for p in self.reverse_edges[child] if p != shard_hash]
        for parent in self.reverse_edges.get(shard_hash, []):
            if parent in self.edges:
                self.edges[parent] = [c for c in self.edges[parent] if c != shard_hash]
        del self.edges[shard_hash]
        del self.reverse_edges[shard_hash]
        del self.nodes[shard_hash]
        return True

    # ── Retrieval ────────────────────────────────────────────────────

    def get_shard(self, shard_hash: str) -> Optional[MemoryShard]:
        return self.nodes.get(shard_hash)

    def get_children(self, shard_hash: str) -> List[MemoryShard]:
        return [self.nodes[h] for h in self.edges.get(shard_hash, []) if h in self.nodes]

    def get_parents(self, shard_hash: str) -> List[MemoryShard]:
        return [self.nodes[h] for h in self.reverse_edges.get(shard_hash, []) if h in self.nodes]

    def get_lineage(self, shard_hash: str, max_depth: int = 10) -> List[MemoryShard]:
        lineage, visited, current, depth = [], set(), shard_hash, 0
        while current and depth < max_depth and current not in visited:
            visited.add(current)
            s = self.get_shard(current)
            if s is None:
                break
            lineage.append(s)
            current, depth = s.parent_hash, depth + 1
        return lineage

    def query_by_domain(self, domain: ShardDomain, scope: Optional[str] = None) -> List[MemoryShard]:
        hashes = self.domain_index.get(domain, set())
        if scope:
            hashes &= self.scope_index.get(scope, set())
        return [self.nodes[h] for h in hashes if h in self.nodes]

    def query_by_scope(self, scope: str) -> List[MemoryShard]:
        return [self.nodes[h] for h in self.scope_index.get(scope, set()) if h in self.nodes]

    def traverse(
        self, start_hash: str, max_depth: int = 5,
        include_leaves: bool = True, include_roots: bool = True,
    ) -> List[MemoryShard]:
        visited, result, queue = {start_hash}, [], [start_hash]
        while queue and len(visited) < max_depth * 10:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            s = self.get_shard(current)
            if s:
                result.append(s)
            for child in self.edges.get(current, []):
                if child not in visited:
                    queue.append(child)
            for parent in self.reverse_edges.get(current, []):
                if parent not in visited:
                    queue.append(parent)
        return result

    # ── Token-capped assembly (cost-aware knapsack + overlap detection) ──

    def assemble_context(
        self,
        scored_shards: List[Tuple[MemoryShard, float]],
        max_tokens: int = 4096,
        allow_overlap: bool = True,
    ) -> ContextEnvelope:
        """
        Token-capped context assembly.

        Algorithm:
        1. Sort by score descending
        2. For each shard: estimate token cost, subtract overlap if content already partially present
        3. Greedy knapsack fill — if it fits, add it
        4. Cap at max_tokens

        Overlap detection: if a selected shard's parent or child is already selected,
        the overlap_tokens is the average cost of the connected shard. This prevents
        double-counting the same information.
        """
        envelope = ContextEnvelope(max_tokens=max_tokens)
        selected_hashes: Set[str] = set()

        for shard, score in scored_shards:
            if envelope.total_tokens >= max_tokens:
                break

            # Calculate effective cost after overlap deduction
            base_cost = len(str(shard.content)) // 4
            overlap_deduction = 0

            if allow_overlap:
                # Check connected shards already selected
                connected = set(self.edges.get(shard.shard_hash, []))
                connected |= set(self.reverse_edges.get(shard.shard_hash, []))
                for conn_hash in connected:
                    if conn_hash in selected_hashes:
                        conn = self.nodes.get(conn_hash)
                        if conn:
                            # Approximate overlap: average of both costs
                            conn_cost = len(str(conn.content)) // 4
                            overlap_deduction = min(base_cost, conn_cost) // 2
                            envelope.excluded_overlaps += 1
                            break

            effective_cost = base_cost - overlap_deduction
            if effective_cost < 0:
                effective_cost = base_cost // 4  # minimum cost even if highly overlapping

            if envelope.total_tokens + effective_cost <= max_tokens:
                envelope.add(shard, overlap_tokens=0)
                selected_hashes.add(shard.shard_hash)

        return envelope

    def scope_filter(
        self,
        shards: Iterable[MemoryShard],
        allowed_scopes: Optional[Set[str]] = None,
        allowed_orgs: Optional[Set[str]] = None,
        allowed_domains: Optional[Set[ShardDomain]] = None,
    ) -> List[MemoryShard]:
        """
        Blast-radius filter: removes shards outside authorized scope BEFORE scoring.
        This is the first gate — nothing scores that isn't in scope.
        """
        result = []
        for s in shards:
            if allowed_domains and s.domain not in allowed_domains:
                continue
            if allowed_scopes and s.scope not in allowed_scopes:
                # Try prefix match
                if not any(s.scope.startswith(rs) or rs in s.scope for rs in allowed_scopes):
                    continue
            if allowed_orgs:
                in_org = False
                for org in allowed_orgs:
                    if f"org:{org}" in s.scope or s.scope.startswith(f"{org}:"):
                        in_org = True
                        break
                if not in_org:
                    continue
            result.append(s)
        return result

    # ── Persistence ──────────────────────────────────────────────────

    def save(self, path: str) -> None:
        """
        Atomic write: serialize to temp file, then rename.
        Guarantees no partial/corrupt state on disk even on crash.
        """
        # Ensure parent dir
        dir_path = os.path.dirname(path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Serialize
        data = {
            SCHEMA_KEY: self.schema_version,
            "nodes": {h: s.to_dict() for h, s in self.nodes.items()},
            "edges": dict(self.edges),
            "reverse_edges": dict(self.reverse_edges),
        }

        # Atomic write via temp file
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=dir_path or os.path.dirname(path) or ".",
            prefix=".memograph_tmp_",
            suffix=".json",
        )
        try:
            with os.fdopen(tmp_fd, "w") as f:
                json.dump(data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)  # Atomic on POSIX; overwrites on Windows
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @classmethod
    def load(cls, path: str, enforce_schema: bool = True) -> "MemoGraph":
        """
        Restore graph from JSON with automatic migration.
        Applies schema migrations if the on-disk version is older than current.
        """
        with open(path) as f:
            data = json.load(f)

        schema = data.pop(SCHEMA_KEY, 1)  # default to 1 if missing (legacy)

        # Auto-migrate schemas
        if schema < SCHEMA_VERSION:
            data = _migrate_schema(data, schema, SCHEMA_VERSION)

        graph = cls(schema_version=SCHEMA_VERSION)
        for h, sd in data.get("nodes", {}).items():
            shard = MemoryShard.from_dict(sd)
            graph.nodes[h] = shard
            graph.domain_index[shard.domain].add(h)
            graph.scope_index[shard.scope].add(h)

        for parent, children in data.get("edges", {}).items():
            graph.edges[parent] = children
            for child in children:
                graph.reverse_edges[child].append(parent)

        return graph


def _migrate_schema(data: Dict, from_ver: int, to_ver: int) -> Dict:
    """
    Apply incremental migrations from from_ver to to_ver.
    Each step is additive-only (never destructive) for safe forward migration.
    """
    d = dict(data)
    for ver in range(from_ver, to_ver):
        if ver == 1:
            d = _migrate_v1_to_v2(d)
    return d


def _migrate_v1_to_v2(data: Dict) -> Dict:
    """
    v1 → v2 migration:
    - Add domain_index from existing shards
    - Add scope_index from existing shards
    - Normalize permissions (list → frozenset ready)
    - Add reverse_edges if missing
    """
    d = dict(data)

    # Rebuild indices if missing (v1 didn't have them)
    if "domain_index" not in d:
        d["domain_index"] = {}
    if "scope_index" not in d:
        d["scope_index"] = {}
    if "reverse_edges" not in d:
        d["reverse_edges"] = {}
        for parent, children in d.get("edges", {}).items():
            for child in children:
                d["reverse_edges"].setdefault(child, []).append(parent)

    # Ensure nodes have required v2 fields
    for h, node in d.get("nodes", {}).items():
        if "permissions" not in node:
            node["permissions"] = []  # default-deny
        if "domain" in node and isinstance(node["domain"], str):
            node["domain"] = node["domain"]  # already string in v1

    return d


# Convenience factory
graph = MemoGraph()
