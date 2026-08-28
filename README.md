# Memograph

**Topological Memory Management Framework for AI Agents**

> *The future agent doesn't need one giant memory. It needs streams.*

---

Memograph is a memory management system that treats memory not as a single semantic index, but as a **multi-domain topological fabric** — where live, project, and enterprise memory exist as independent, persistent, addressable streams that are dynamically composed at query time without ever being physically merged.

---

## The Problem With Memory Today

Most agent memory systems make one critical mistake: they conflate the **persistence layer** with the **execution layer**.

They pour everything into a vector database, retrieve the k-most-similar documents, stuff it all into a context window, and call it "RAG."

This approach has fundamental limits:

| Symptom | Root Cause |
|---------|-----------|
| Context wall | Context window becomes the database |
| No provenance | System can't explain how it "knew" something |
| Permission blindness | Every retrieval sees everything it's authorized to see |
| No forgetting | Ephemeral memory accumulates forever |
| Blob context | Live conversation mixed with enterprise policy as if equal |

---

## What Memograph Does Differently

### 1. Three Independent Memory Streams

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY TOPOLOGY                          │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────┐ │
│  │   LIVE STREAM   │  │  PROJECT STREAM │  │ ENTERPRISE  │ │
│  │   Authority 0.5 │  │  Authority 0.8  │  │ Authority 1 │ │
│  │   TTL: 1hr      │  │  Persistent     │  │ Policy-level│ │
│  │                 │  │                  │  │              │ │
│  │ Intent          │  │ Architecture     │  │ Governance   │ │
│  │ Constraints     │  │ Decisions        │  │ SOPs         │ │
│  │ Active Task     │  │ Research         │  │ Compliance   │ │
│  │ Working State   │  │ Artifacts        │  │ Security     │ │
│  │ Ephemeral       │  │ Project history  │  │ Shared data  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────┘ │
│         ↕                    ↕                      ↕       │
│         └────────────────────┼────────────────────┘        │
│                              │                             │
│                    ┌─────────▼─────────┐                   │
│                    │   CONTEXT ROUTER  │                   │
│                    │                   │                   │
│                    │ semantic 0.40     │                   │
│                    │ recency   0.25     │                   │
│                    │ authority 0.20     │                   │
│                    │ affinity  0.15     │                   │
│                    └─────────┬───────────┘                   │
│                              │                               │
│                    ┌─────────▼───────────────┐             │
│                    │  TOKEN-CAPPED CONTEXT     │             │
│                    │  STREAMS PRESERVED        │             │
│                    │  live │ project │ ent    │             │
│                    └───────┴─────────┴─────────┘             │
└─────────────────────────────────────────────────────────────┘
```

**The memories remain separate. The context becomes composable.**

### 2. Cryptographic Memory Identity

Every memory shard is content-addressed by SHA256:

```python
shard = MemoryShard.create(
    content={"decision": "use postgresql for payments"},
    owner="agent-001",
    scope="project:payment-service",
    domain=ShardDomain.PROJECT
)
# shard.shard_hash = "a7f9e3b2c1d4..."
```

Change *anything* — content, permissions, even timestamp — and the hash changes. The shard becomes tamper-evident.

### 3. Verifiable Lineage

```
Decision shard → references Conversation shard → references Research shard
     ↑                    ↑                           ↑
     └─────────────────────┴───────────────────────────┘
                     parent_hash chain
```

Trace back through any memory to understand how it came to exist.

### 4. Bidirectional Lifecycle

```python
# LIVE → PROJECT: Decision becomes part of project history
result = LifecyclePipeline.promote_shard(
    shard=live_decision,
    target_domain=ShardDomain.PROJECT,
    actor="agent-001",
    reason="Approved as architectural standard"
)

# PROJECT → ENTERPRISE: Discovery becomes org-wide policy
result = LifecyclePipeline.promote_shard(
    shard=project_decision,
    target_domain=ShardDomain.ENTERPRISE,
    actor="architect-lead",
    reason="Standard across all services"
)

# ENTERPRISE → PROJECT: Context flows DOWN without promotion
snapshot = apply_context(
    source_shard=enterprise_policy,
    target_domain=ShardDomain.PROJECT,
    actor="agent-001",
    purpose="compliance check"
)
```

### 5. Audit Trail

Every meaningful operation is an append-only event:

```python
event = MemoryEvent.create(
    event_id=12831,
    event_type=EventType.PROMOTED,
    actor="agent-001",
    scope="project:payment-service",
    previous_state_hash="a7f9...",
    new_state_hash="8d21...",
    reason="Architecture decision for v2.0 migration",
    evidence={"plan": "migration_plan_v2.pdf"},
    model_version="claude-sonnet-4"
)
```

Now you can answer: *"What did the agent actually know when it made this decision?"*

### 6. Token-Capped Context Assembly

The router assembles context using a knapsack algorithm that respects your LLM's context window:

```python
context = graph.assemble_context(
    scored_candidates,
    max_tokens=4096
)
# Returns ContextEnvelope preserving stream boundaries
# context.by_domain(ShardDomain.ENTERPRISE)  # just the policy shards
# context.by_domain(ShardDomain.LIVE)         # just the conversation
```

---

## Quick Start

```bash
# Install
pip install memograph

# Or from source
git clone https://github.com/artifact-opensource/memory_context_protocol.git
cd memory_context_protocol
./setup_project.sh
pip install -e .
```

```python
from memograph import (
    MemoryShard, ShardDomain, MemoGraph,
    ContextRouter, ContextQuery, ContextEnvelope
)

# 1. Create memory
graph = MemoGraph()
shard = MemoryShard.create(
    content={"architecture": "microservices", "db": "postgresql"},
    owner="agent-001",
    scope="project:payment-service",
    domain=ShardDomain.PROJECT
)
graph.add_shard(shard)

# 2. Query with context
router = ContextRouter()
query = ContextQuery(text="database architecture decisions")
candidates = router.route(graph.query_by_domain(ShardDomain.PROJECT), query)

# 3. Get bounded context for LLM
context = graph.assemble_context(candidates, max_tokens=2048)
print(f"Context has {len(context)} shards from {context.domains}")
```

---

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full specification.

```
memograph/
├── core/           # Core primitives: shard, events, router, memograph, types
├── lifecycle/      # Promotion, demotion, eviction, context application
├── engines/        # Heterogeneous retrieval adapters
│   ├── base.py              # RetrievalAdapter interface + AdapterRegistry
│   ├── semantic_adapter.py  # Vector similarity (HEKTOR)
│   ├── structured_adapter.py # AST/symbol lookup for code
│   ├── graph_adapter.py     # Graph traversal
│   ├── temporal_adapter.py   # Time-series queries
│   ├── lexical_adapter.py   # Full-text search
│   ├── kv_adapter.py        # Key-value state
│   └── memory_store.py      # Persistence layer
└── auth/           # Permission engine + policy decisions
```

---

## Key Design Principles

1. **Memory is persistence; context is execution** — never conflate them
2. **Streams remain physically separated** — only the router composes at query time
3. **Every meaningful mutation is an auditable event** — append-only, cryptographically chained
4. **Promotion is a proposal; policy gates the transition** — not automatic
5. **Retrieval is heterogeneous by design** — different content types use different engines
6. **Context has ownership** — a piece of memory has place, owner, scope, lineage, lifecycle, permission boundary
7. **The topology IS the memory** — not a vector database, not a folder hierarchy

---

## Features

| Feature | Status |
|---------|--------|
| Three-domain memory topology | ✅ |
| SHA256 content-addressed shards | ✅ |
| Parent lineage / DAG | ✅ |
| Multi-dimensional context scoring | ✅ |
| Token-capped context assembly | ✅ |
| Stream boundary preservation | ✅ |
| Bidirectional lifecycle (promote/demote/apply) | ✅ |
| Append-only event audit log | ✅ |
| TTL-based eviction / forgetting | ✅ |
| Permission engine | ✅ |
| Heterogeneous retrieval adapters | ✅ |
| HEKTOR / vector similarity | ✅ |
| Policy-gated promotion | ✅ |
| Explainable decision provenance | ✅ |
| Multi-organization scope isolation | ✅ |

---

## Why Not Just Use RAG?

RAG answers: *"What information should I retrieve?"*

Memograph answers: *"What memory should exist, where should it exist, who owns it, who can access it, how is it related to other memories, and what subset should become context right now?"*

That's a different problem — and a bigger one.

Once agents become persistent, autonomous, and organizationally embedded, they don't just need knowledge retrieval. They need:

- **Memory architecture** — boundaries, identity, provenance
- **Continuity** — the difference between "I was told this five seconds ago" and "This is an established organizational policy"
- **Forgetting** — the ability to let ephemeral things expire
- **Inheritance** — enterprise → project → live context flows
- **Auditability** — reconstruct what the agent knew at decision time

---

## Contributing

See [docs/SPECS.md](docs/SPECS.md) for contribution guidelines.

```bash
# Development setup
pip install -e ".[dev]"
pytest
ruff format .
ruff check --fix .
```

---

## License

MIT

---

## Version

0.2.0
