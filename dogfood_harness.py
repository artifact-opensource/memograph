"""
Memograph Dogfood Harness
=========================
Exercises the FULL documented surface the way a real agent would use it,
and reports PASS / FAIL / GAP honestly. Not a unit test — a capability probe.

Run:  python dogfood_harness.py
"""
import json
import os
import sys
import tempfile
import traceback

from memograph import (
    MemoryShard, ShardDomain, MemoGraph,
    ContextRouter, ContextQuery,
    memograph_tool, LifecyclePipeline,
    MemoryEvictor, EvictionResult,
    is_authorized, identity, AGENT_IDENTITY,
)
from memograph.core.events import MemoryEvent, EventType
from memograph.core.types import ContentType, RetrievalEngine, AccessLevel

WORK = tempfile.mkdtemp(prefix="memograph_dogfood_")
results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))

def section(t): print(f"\n=== {t} ===")

try:
    # ---------------------------------------------------------------
    section("1. Import & constructors (DOGFOOD_REPORT 'Import' row)")
    s = MemoryShard.create(content={"task": "build payments API"},
                            owner="agent-001", scope="project:payments",
                            domain=ShardDomain.LIVE)
    check("MemoryShard.create", bool(s.shard_hash))
    check("shard has content_type", s.content_type is not None,
          f"content_type={s.content_type.name}")

    # ---------------------------------------------------------------
    section("2. Hash identity (DOGFOOD_REPORT 'Hash identity' row)")
    s2 = MemoryShard.create(content={"task": "build payments API"},
                             owner="agent-001", scope="project:payments",
                             domain=ShardDomain.LIVE)
    check("same content -> same hash", s.shard_hash == s2.shard_hash)
    s3 = MemoryShard.create(content={"task": "DIFFERENT"},
                             owner="agent-001", scope="project:payments",
                             domain=ShardDomain.LIVE)
    check("different content -> different hash", s.shard_hash != s3.shard_hash)

    # ---------------------------------------------------------------
    section("3. Audit chain (DOGFOOD_REPORT 'Audit chain' row)")
    e1 = MemoryEvent.create(event_id=1, event_type=EventType.CREATED,
                             actor="agent-001", scope="project:payments",
                             new_state_hash=s.shard_hash, reason="store")
    check("MemoryEvent.create + hash", bool(e1.event_hash))

    # ---------------------------------------------------------------
    section("4. Store / Retrieve via agent tool")
    tool = memograph_tool(session_id="dogfood", storage_dir=WORK)
    r = tool(action="store", query="We chose PostgreSQL",
             content={"db": "postgresql", "reason": "ACID"},
             domain="project", scope="payments")
    check("tool store success", r.success)
    res = tool(action="retrieve", query="payments database decision",
               domain="project", scope="payments")
    check("tool retrieve returns shard", res.success and res.shard_count >= 1,
          f"shard_count={res.shard_count}")
    ctx = res.to_context_string()
    check("to_context_string non-empty", "postgresql" in ctx,
          "injection format contains stored content")

    # ---------------------------------------------------------------
    section("5. Context routing & token-capped assembly")
    g = MemoGraph()
    g.add_shard(s)
    router = ContextRouter()
    cands = g.query_by_domain(ShardDomain.LIVE)
    q = ContextQuery(text="payments", scope="project:payments", max_tokens=2048)
    scored = router.route(cands, q)
    check("router.route returns scored", len(scored) >= 1)
    env = g.assemble_context([(x, sc) for x, sc in scored], max_tokens=2048)
    check("assemble_context returns context", len(env.shards) >= 1)

    # ---------------------------------------------------------------
    section("6. Persistence round-trip (save/load)")
    path = os.path.join(WORK, "graph.json")
    g.save(path)
    g2 = MemoGraph.load(path)
    check("load restores node count", len(g2.nodes) == len(g.nodes),
          f"{len(g2.nodes)} vs {len(g.nodes)}")

    # ---------------------------------------------------------------
    section("7. Lifecycle promotion (LIVE -> PROJECT -> ENTERPRISE)")
    g.add_shard(s)  # ensure base shard is in the graph for lineage
    p1 = LifecyclePipeline.promote_shard(shard=s, target_domain=ShardDomain.PROJECT,
                                         actor="lead", reason="promote1")
    check("promote to PROJECT", p1.success)
    if p1.success:
        g.add_shard(p1.target_shard)
        p2 = LifecyclePipeline.promote_shard(shard=p1.target_shard,
                                             target_domain=ShardDomain.ENTERPRISE,
                                             actor="arch", reason="promote2")
        check("promote to ENTERPRISE", p2.success,
              f"perms={p2.target_shard.permissions if p2.success else None}")
        if p2.success:
            g.add_shard(p2.target_shard)

    # ---------------------------------------------------------------
    section("8. Lineage tracing")
    if p1.success:
        lin = g.get_lineage(p1.target_shard.shard_hash)
        check("get_lineage returns chain", len(lin) >= 2, f"depth={len(lin)}")

    # ---------------------------------------------------------------
    section("9. Permission enforcement (default-deny)")
    check("empty perms denied", is_authorized([], AGENT_IDENTITY) is False)
    check("wildcard allowed", is_authorized(["*"], AGENT_IDENTITY) is True)
    check("agent role allowed", is_authorized(["agent"], AGENT_IDENTITY) is True)

    # ---------------------------------------------------------------
    section("10. Blast-radius scope filter")
    filtered = router.scope_filter([s], allowed_scopes={"project:payments"})
    check("scope_filter keeps matching scope", len(filtered) == 1)
    filtered2 = router.scope_filter([s], allowed_scopes={"project:other"})
    check("scope_filter drops non-matching scope", len(filtered2) == 0)

    # ---------------------------------------------------------------
    section("11. Eviction / TTL forgetting (MemoryEvictor)")
    try:
        ev = MemoryEvictor()
        ev.set_ttl(s, ttl_seconds=0)  # expire immediately
        res_ev = ev.evict_ready([s])
        check("MemoryEvictor.evict_ready runs", isinstance(res_ev, EvictionResult),
              f"evicted={getattr(res_ev,'evicted_shards',None)}")
    except Exception as ex:
        check("MemoryEvictor.evict_ready runs", False, repr(ex))

    # ---------------------------------------------------------------
    section("12. DOCUMENTED-BUT-MISSING features (doc/code gap probe)")
    # (a) MemoryShard.from_dict
    try:
        d = s.to_dict()
        s_back = MemoryShard.from_dict(d)
        check("MemoryShard.from_dict exists", True)
    except AttributeError:
        check("MemoryShard.from_dict exists", False,
              "NOT IMPLEMENTED — yet CHANGELOG/DOGFOOD claim load() uses it")
    # (b) append-only audit trail file
    audit_path = os.path.join(".audit_trail", "session_audit.json")
    check("append-only .audit_trail/session_audit.json", os.path.exists(audit_path),
          "expected by DOGFOOD_REPORT, production.md")
    # (c) 7 retrieval adapters actually wired into the registry/router
    from memograph.engines.base import AdapterRegistry, default_registry
    reg = AdapterRegistry()
    from memograph.engines.base import register_default_adapters
    register_default_adapters(reg)
    check("AdapterRegistry populated at runtime", len(reg.list_adapters()) >= 7,
          f"registered={reg.list_adapters()} — CHANGELOG claims 7 adapters")
    # router must actually use the registry to index + dispatch
    rr = ContextRouter()
    check("ContextRouter holds a populated registry",
          len(rr.registry.list_adapters()) >= 7,
          "router dispatches by ContentType via AdapterRegistry")
    # exercise dispatch: index a shard, confirm an adapter accepts it
    rr.index_shard(s)
    adp = rr.adapter_for(s.content_type)
    check("router resolves adapter for a shard's content type",
          adp is not None, f"adapter={getattr(adp,'name',None)}")
    try:
        # build a real v1-style file manually: schema 1, no reverse_edges/index
        v1 = {"_memograph_schema": 1,
              "nodes": {s.shard_hash: s.to_dict()},
              "edges": {}, "reverse_edges": {}}
        mp = os.path.join(WORK, "v1.json")
        with open(mp, "w") as f:
            json.dump(v1, f)
        gv1 = MemoGraph.load(mp)  # should auto-migrate even without _migrate_schema
        check("MemoGraph.load handles schema v1 file", len(gv1.nodes) == 1,
              "production.md claims v1->v2 auto-migration")
    except Exception as ex:
        check("MemoGraph.load handles schema v1 file", False, repr(ex))

except Exception:
    print("\n!!! HARNESS CRASHED !!!")
    traceback.print_exc()

# ---------------------------------------------------------------
section("SUMMARY")
passed = sum(1 for r in results if r[0] == "PASS")
failed = sum(1 for r in results if r[0] == "FAIL")
print(f"TOTAL: {len(results)}  PASS: {passed}  FAIL: {failed}")
for st, nm, dt in results:
    if st == "FAIL":
        print(f"  FAIL: {nm} — {dt}")
sys.exit(1 if failed else 0)
