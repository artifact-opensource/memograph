"""Recompute shard hashes in snapshot files and repair parent/edge references.

Usage: python -m memograph.reseal <snapshot.json> [<snapshot.json> ...]

A snapshot whose content was edited after it was written no longer verifies
(MemoryShard.from_dict raises on a hash mismatch). Resealing recomputes every
shard hash from its current fields, rewrites parent_hash links to the new
hashes, and remaps the node, edge and reverse-edge keys.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

from memograph.core.shard import ContentType, MemoryShard, ShardDomain


def _build(raw: Dict[str, Any], parent_hash: Any) -> MemoryShard:
    content_type = raw.get("content_type", "CONVERSATIONAL")
    shard = MemoryShard(
        content=raw["content"],
        owner=raw["owner"],
        scope=raw["scope"],
        domain=ShardDomain(str(raw.get("domain", "live")).lower()),
        parent_hash=parent_hash,
        permissions=list(raw.get("permissions", [])),
        timestamp=float(raw.get("timestamp", 0.0)),
        version=int(raw.get("version", 1)),
        content_type=ContentType[str(content_type).upper()],
    )
    return shard


def reseal(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    old_nodes: Dict[str, Dict[str, Any]] = snapshot.get("nodes", {})
    mapping: Dict[str, str] = {}
    sealed: Dict[str, Dict[str, Any]] = {}

    def resolve(old_hash: str, stack: tuple = ()) -> str:
        if old_hash in mapping:
            return mapping[old_hash]
        if old_hash in stack:
            raise ValueError(f"Cycle in parent chain at {old_hash}")
        raw = old_nodes[old_hash]
        parent = raw.get("parent_hash")
        new_parent = resolve(parent, stack + (old_hash,)) if parent in old_nodes else parent
        shard = _build(raw, new_parent)
        mapping[old_hash] = shard.shard_hash
        sealed[shard.shard_hash] = shard.to_dict()
        return shard.shard_hash

    for old_hash in old_nodes:
        resolve(old_hash)

    def remap_edges(edges: Dict[str, List[str]]) -> Dict[str, List[str]]:
        return {
            mapping.get(k, k): [mapping.get(v, v) for v in values]
            for k, values in edges.items()
        }

    result = dict(snapshot)
    result["nodes"] = sealed
    for key in ("edges", "reverse_edges"):
        if key in snapshot:
            result[key] = remap_edges(snapshot[key])
    return result


def main(argv: List[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    for path in argv:
        with open(path, encoding="utf-8") as fh:
            snapshot = json.load(fh)
        before = len(snapshot.get("nodes", {}))
        resealed = reseal(snapshot)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(resealed, fh, indent=2)
            fh.write("\n")
        print(f"{path}: resealed {before} shard(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
