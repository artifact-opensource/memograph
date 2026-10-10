import json

from memograph.core.shard import MemoryShard
from memograph.reseal import reseal


def test_reseal_fixes_stale_hashes_and_links():
    parent = MemoryShard.create(content={"a": "x"}, owner="o", scope="s")
    child = MemoryShard.create(content={"b": "y"}, owner="o", scope="s", parent_hash=parent.shard_hash)
    p, c = parent.to_dict(), child.to_dict()
    p["content"] = {"a": "edited"}  # content changed after hashing
    snapshot = {
        "nodes": {p["shard_hash"]: p, c["shard_hash"]: c},
        "edges": {p["shard_hash"]: [c["shard_hash"]]},
        "reverse_edges": {c["shard_hash"]: [p["shard_hash"]]},
    }

    sealed = reseal(snapshot)

    for h, node in sealed["nodes"].items():
        MemoryShard.from_dict(node)  # raises on mismatch
        assert node["shard_hash"] == h
    (new_parent,) = [h for h, n in sealed["nodes"].items() if n["parent_hash"] is None]
    (new_child,) = [h for h, n in sealed["nodes"].items() if n["parent_hash"]]
    assert sealed["nodes"][new_child]["parent_hash"] == new_parent
    assert sealed["edges"] == {new_parent: [new_child]}
    assert sealed["reverse_edges"] == {new_child: [new_parent]}
    json.dumps(sealed)
