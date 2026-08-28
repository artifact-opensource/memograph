"""
MemoGraph: Topological memory navigator with token-capped traversal.

Implements:
- Content-addressed node storage
- Edge-based graph traversal (parent, child, and cross-domain links)
- Token-capped context assembly (knapsack algorithm)
- Stream boundary preservation in assembled contexts
- Citation tracking for explainability

Key design principle:
    Memory is a graph, not a folder hierarchy.
    Each relationship is addressable and verifiable.
    Context assembly preserves the topology — shards are not merged.
"""

import heapq
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Set, Any

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.types import ContentType


@dataclass
class ContextEnvelope:
    """
    Preserves stream boundaries when assembling context.
    
    Critical for the "counter merge" architecture:
    Live, Project, and Enterprise memories remain separate
    but are combined into a single context envelope.
    
    The agent sees each shard with its domain label intact.
    """
    shards: List[MemoryShard] = field(default_factory=list)
    domains: Dict[ShardDomain, int] = field(default_factory=dict)
    total_tokens: int = 0
    max_tokens: int = 0
    
    def add(self, shard: MemoryShard) -> None:
        """Add a shard to the envelope."""
        self.shards.append(shard)
        self.domains[shard.domain] = self.domains.get(shard.domain, 0) + 1
        self.total_tokens += len(str(shard.content)) // 4
    
    def by_domain(self, domain: ShardDomain) -> List[MemoryShard]:
        """Retrieve all shards from a specific domain."""
        return [s for s in self.shards if s.domain == domain]
    
    def __len__(self) -> int:
        return len(self.shards)


class MemoGraph:
    """
    A content-addressed memory graph.
    
    Nodes are MemoryShards; edges represent causal, temporal,
    and structural relationships. Graph traversal is token-capped
    to respect LLM context limits.
    
    The graph is immutable — mutations create new nodes with
    parent_hash edges, preserving the original state.
    """
    
    def __init__(self):
        # Content-addressed node store
        self.nodes: Dict[str, MemoryShard] = {}
        
        # Adjacency list: parent_hash -> [child_hashes]
        self.edges: Dict[str, List[str]] = defaultdict(list)
        
        # Reverse index: child_hash -> [parent_hashes]
        self.reverse_edges: Dict[str, List[str]] = defaultdict(list)
        
        # Domain index for quick filtering
        self.domain_index: Dict[ShardDomain, Set[str]] = defaultdict(set)
        
        # Scope index for project/organization filtering
        self.scope_index: Dict[str, Set[str]] = defaultdict(set)
    
    def add_shard(self, shard: MemoryShard) -> str:
        """
        Add a shard to the graph.
        
        If a shard with the same hash already exists, it is not duplicated.
        If the shard has a parent_hash, an edge is created from parent to child.
        
        Returns:
            The shard_hash of the added (or existing) shard.
        """
        if shard.shard_hash in self.nodes:
            return shard.shard_hash
        
        # Store node
        self.nodes[shard.shard_hash] = shard
        
        # Update indices
        self.domain_index[shard.domain].add(shard.shard_hash)
        self.scope_index[shard.scope].add(shard.shard_hash)
        
        # Update edges
        if shard.parent_hash and shard.parent_hash in self.nodes:
            self.edges[shard.parent_hash].append(shard.shard_hash)
            self.reverse_edges[shard.shard_hash].append(shard.parent_hash)
        
        return shard.shard_hash
    
    def get_shard(self, shard_hash: str) -> Optional[MemoryShard]:
        """Retrieve a shard by its cryptographic hash."""
        return self.nodes.get(shard_hash)
    
    def get_children(self, shard_hash: str) -> List[MemoryShard]:
        """Get all child shards of a given shard."""
        return [self.nodes[h] for h in self.edges.get(shard_hash, []) if h in self.nodes]
    
    def get_parents(self, shard_hash: str) -> List[MemoryShard]:
        """Get all parent shards of a given shard."""
        return [self.nodes[h] for h in self.reverse_edges.get(shard_hash, []) if h in self.nodes]
    
    def get_lineage(self, shard_hash: str, max_depth: int = 10) -> List[MemoryShard]:
        """
        Trace the lineage of a shard back through parent references.
        
        Returns the chain from current shard to root, in order.
        """
        lineage = []
        current = shard_hash
        depth = 0
        visited = set()
        
        while current is not None and depth < max_depth:
            if current in visited:
                break  # Cycle detected
            visited.add(current)
            
            shard = self.get_shard(current)
            if shard is None:
                break
            
            lineage.append(shard)
            current = shard.parent_hash
            depth += 1
        
        return lineage
    
    def query_by_domain(self, domain: ShardDomain, scope: Optional[str] = None) -> List[MemoryShard]:
        """Get all shards in a specific domain, optionally filtered by scope."""
        shard_hashes = self.domain_index.get(domain, set())
        if scope:
            shard_hashes = shard_hashes & self.scope_index.get(scope, set())
        return [self.nodes[h] for h in shard_hashes if h in self.nodes]
    
    def query_by_scope(self, scope: str) -> List[MemoryShard]:
        """Get all shards in a specific scope (project/organization)."""
        return [self.nodes[h] for h in self.scope_index.get(scope, set()) if h in self.nodes]

    def remove_shard(self, shard_hash: str) -> bool:
        """Remove a shard from the graph. Returns True if found and removed."""
        if shard_hash not in self.nodes:
            return False

        shard = self.nodes[shard_hash]

        # Remove from indices
        self.domain_index[shard.domain].discard(shard_hash)
        self.scope_index[shard.scope].discard(shard_hash)

        # Remove from edges
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

    def save(self, path: str) -> None:
        """Serialize graph to JSON for persistence."""
        data = {
            "nodes": {h: s.to_dict() for h, s in self.nodes.items()},
            "edges": dict(self.edges),
            "reverse_edges": dict(self.reverse_edges),
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> "MemoGraph":
        """Restore graph from JSON."""
        with open(path) as f:
            data = json.load(f)

        graph = cls()
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

    def traverse(self, start_hash: str, max_depth: int = 5,
                 include_leaves: bool = True, include_roots: bool = True) -> List[MemoryShard]:
        """
        Graph traversal from a starting shard.
        
        Performs BFS/DFS to discover connected shards.
        Returns shards in a list (order may vary by traversal strategy).
        """
        visited = set()
        result = []
        queue = [start_hash]
        
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            
            shard = self.get_shard(current)
            if shard:
                result.append(shard)
            
            # Explore children
            for child_hash in self.edges.get(current, []):
                if child_hash not in visited:
                    queue.append(child_hash)
            
            # Explore parents
            for parent_hash in self.reverse_edges.get(current, []):
                if parent_hash not in visited:
                    queue.append(parent_hash)
            
            if len(visited) >= max_depth:
                break
        
        return result
    
    def assemble_context(self, scored_shards: List[Tuple[MemoryShard, float]],
                         max_tokens: int = 4096) -> ContextEnvelope:
        """
        Token-capped context assembly with stream boundary preservation.
        
        Uses a knapsack-like algorithm to select the highest-scoring
        shards that fit within the token budget.
        
        IMPORTANT: Stream boundaries are preserved — the returned
        ContextEnvelope carries domain labels, so the agent can
        distinguish live from project from enterprise memory.
        
        Args:
            scored_shards: List of (shard, score) tuples
            max_tokens: Maximum tokens for the assembled context
            
        Returns:
            ContextEnvelope containing selected shards with domain labels
        """
        envelope = ContextEnvelope(max_tokens=max_tokens)
        
        # Sort by score descending (highest first)
        sorted_candidates = sorted(scored_shards, key=lambda x: x[1], reverse=True)
        
        for shard, score in sorted_candidates:
            # Estimate token cost (~4 chars per token)
            content_str = str(shard.content)
            token_cost = len(content_str) // 4
            
            if envelope.total_tokens + token_cost <= max_tokens:
                envelope.add(shard)
                if envelope.total_tokens >= max_tokens:
                    break
        
        return envelope
    
    @staticmethod
    def estimate_tokens(shard: MemoryShard) -> int:
        """Estimate token count for a shard's content."""
        content_str = str(shard.content)
        return len(content_str) // 4


# Convenience factory
graph = MemoGraph()