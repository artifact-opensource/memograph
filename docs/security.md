# Security and Governance

## Threat Model

Memograph stores organizational memory. Key risks:

| Threat | Mitigation |
|--------|-----------|
| Tampered memory | SHA256 content-addressed shards; any mutation changes hash |
| Unauthorized access | `PermissionEngine` with scope/domain checks |
| Replay attacks | Append-only event log; prior state preserved |
| Data leakage | Per-agent session isolation; no global memory dump |
| Privilege escalation | Policy-gated promotion (not automatic) |

## Hash Verification

Every shard carries a cryptographic identity. To verify integrity:

```python
expected = shard.compute_hash()
assert expected == shard.shard_hash, "Shard tampered"
```

When promoting, the new shard references the old via `parent_hash`. The chain is verifiable.

## Permission Model

```python
from memograph.auth.permissions import PermissionEngine, PermissionContext

engine = PermissionEngine()
decision = engine.check(PermissionContext(
    actor="agent-001",
    action="promote",
    shard=enterprise_policy,
    actor_role="project_member",
))
```

- **LIVE shards**: Agent/session-level access
- **PROJECT shards**: Project members + authorized agents
- **ENTERPRISE shards**: Org-wide policies; promotion requires explicit authorization

## Audit Trail

Every promotion, store, evict, or access creates a timestamped, hash-linked event. To reconstruct agent knowledge at decision time:

```python
events = [e for e in session_events if e.event_type == EventType.PROMOTED]
# Walk back to the original context state
```

## Multi-Organization Isolation

An agent may operate across organizations but receives only the permitted shards per request. The router never dumps enterprise memory into a project context; it scores and selects within authorized scope.
