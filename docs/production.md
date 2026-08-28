# Production Readiness

Memograph v0.2.0 ships with the production-grade layer that the MVP lacked. This doc covers the implementation details for operators running memograph in production.

---

## Schema Versioning

Every serialized file embeds `SCHEMA_VERSION` (current: `2`).

```json
{
  "_memograph_schema": 2,
  "nodes": { ... },
  "edges": { ... },
  "reverse_edges": { ... }
}
```

On load (`MemoGraph.load()`), the file version is compared to `SCHEMA_VERSION`. If `file_version < SCHEMA_VERSION`, `_migrate_schema()` applies incremental migrations:

- **v1 → v2**: rebuilds `domain_index` and `scope_index`; ensures `permissions` exists (default-deny); creates `reverse_edges`; normalizes domain values.

Migration is additive-only — existing node content and hashes are preserved. Old files load safely; new versions never corrupt old files.

---

## Transactional Persistence

`MemoGraph.save()` writes atomically:

```python
tmp_path = tempfile.mkstemp(...)
with open(tmp_path, 'w') as f:
    json.dump(data, f)
    f.flush()
    os.fsync(f.fileno())  # flush to disk
os.rename(tmp_path, path)  # atomic rename (POSIX guarantee)
```

If the process crashes between `fsync()` and `rename()`, the temp file is cleaned up by `unlink()` in the exception handler. The original file remains intact. No partial `.json` ever exists at the target path.

---

## Permission Enforcement (Default-Deny)

Every shard has a `permissions` list (string tokens). The `Identity` model enforces access:

```python
from memograph.auth import is_authorized, identity, AGENT_IDENTITY

# A shard without permissions is DENIED
is_authorized([], AGENT_IDENTITY)  # False

# Wildcard grants access
is_authorized(["*"], AGENT_IDENTITY)  # True

# Role-based match
is_authorized(["agent"], AGENT_IDENTITY)  # True

# User-scoped match
is_authorized(["user:ali"], identity(id="ali"))  # True
```

Access rules apply in this order: wildcard (`*`) → role token (`agent`, `system`) → user/project/org scoped tokens (`user:<id>`, `project:<pid>`, `org:<oid>`) → bare identity string. Any mismatch = `False` (default deny).

The `ContextRouter._is_allowed()` enforces this at retrieval time. The `scope_filter()` applies blast-radius filtering before scoring (before any shard enters the context window).

---

## Blast-Radius Filtering (Scope Isolation)

`scope_filter()` runs before `route()` and `score_shard()`:

```python
shards = router.scope_filter(
    all_shards,
    allowed_scopes={"skills:catalog", "skills:catalog:full"},
    allowed_orgs={"artifact-virtual"},
)
```

Only shards whose `scope` matches the allowed scopes or org prefix (`org:artifact-virtual`) proceed to scoring. Everything else is excluded before any computation is spent.

---

## Cost-Aware Token-Capped Traversal

`assemble_context()` calculates effective cost per shard:

```python
effective_cost = base_cost - overlap_deduction
```

Overlap deduction triggers when a shard's connected shard (via edge) has already been selected. The overlap is estimated as `min(base_cost, conn_cost) // 2` — approximately half the shared token cost. This prevents double-counting the same information in context budgets.

The `ContextEnvelope` tracks:
- `total_tokens`: accumulated budget
- `excluded_overlaps`: count of overlap deductions applied
- `shards`: selected shards (domain-tagged, never merged)

---

## Audit Trail

Every mutation (add, promote, audit event) writes to `.audit_trail/session_audit.json` (append-only, append-mode file open). Each entry includes: timestamp, actor identity, operation, previous/new hash chain, reason, evidence reference, scope, and model version.

---

## Multi-Organization Isolation

The `scope` field carries organization identity (`org:artifact-virtual`). `scope_filter()` and `is_authorized()` both enforce this. A project in `org:artifact-virtual` cannot see shards from `org:other-org` unless explicitly granted `org:other-org` in permissions or `allowed_orgs`.

The stream boundary (`LIVE` vs `PROJECT` vs `ENTERPRISE`) is preserved by the `ContextEnvelope.by_domain()` method — assembled context never flattens streams; each shard retains its domain label.
