# Memograph Architecture Documentation

## Overview

Memograph implements a **topological memory architecture** for AI agents. Unlike traditional RAG systems that treat memory as a single semantic index, Memograph organizes memory into three distinct streams that remain physically separated but can be dynamically composed by a context router.

## Core Design Principles

1. **Memory is persistence; context is execution** — never conflate them
2. **Streams remain separated** — only the router composes them for a query
3. **Every mutation is an auditable event** — append-only, cryptographic integrity
4. **Promotion is a proposal** — policy gates the actual transition
5. **Retrieval is heterogeneous** — different memory types use appropriate engines
6. **Context has ownership** — a piece of memory has place, owner, scope, lineage, lifecycle, permission boundary, and audit history
7. **The topology IS the memory** — not a vector database, not a folder hierarchy

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                          USER / AGENT                            │
│                        "Why this architecture?"                  │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       CONTEXT ROUTER                             │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────┐   │
│  │  Auth Engine │  │  Event Store │  │  Policy Engine      │   │
│  │  (perms)     │  │  (audit)     │  │  (governance)       │   │
│  └──────────────┘  └──────────────┘  └─────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │          MULTI-DIMENSIONAL SCORING ENGINE            │      │
│  │  semantic │ recency │ authority │ affinity │ provenance│     │
│  └──────────────────────────────────────────────────────┘      │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      MEMORY TOPOLOGY                             │
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌──────────────┐ │
│  │   LIVE STREAM   │    │  PROJECT STREAM │    │  ENTERPRISE  │ │
│  │                 │    │                 │    │  STREAM      │ │
│  │ ┌─────┐ ┌─────┐ │    │ ┌─────┐ ┌─────┐ │    │ ┌──────────┐ │ │
│  │ │Shard│ │Shard│ │    │ │Shard│ │Shard│ │    │ │Shard     │ │ │
│  │ │ A   │ │ B   │ │    │ │ A   │ │ B   │ │    │ │Policy    │ │ │
│  │ └─────┘ └─────┘ │    │ └─────┘ └─────┘ │    │ └──────────┘ │ │
│  │                 │    │                 │    │              │ │
│  │ TTL: 1hr       │    │ TTL: persistent │    │ TTL: perm    │ │
│  └─────────────────┘    └─────────────────┘    └──────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              MEMOGRAPH (DAG)                              │   │
│  │  Parent links │ Cross-stream edges │ Version chains       │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   TOKEN-CAPPED CONTEXT ASSEMBLY                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Knapsack algorithm: select shards fitting max_tokens      │   │
│  │ Stream boundaries preserved in ContextEnvelope            │   │
│  │ Agent receives: ContextEnvelope[shard_domain → shards]    │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   REASONING / DECISION                           │
│                                                                  │
│  Agent reasons over assembled context and produces a decision.   │
│  Decision is recorded as an event with full provenance.          │
└──────────────────────────────────────────────────────────────────┘
```

## Context Streams

### Live Conversational Memory

| Property | Value |
|----------|-------|
| **Domain** | `ShardDomain.LIVE` |
| **Lifespan** | Minutes to hours |
| **Authority** | 0.5 |
| **Eviction** | TTL-based (default 1 hour) |
| **Typical shards** | Intent, Decision, Constraint, Preference, Active Task, Working Knowledge, Ephemeral State |
| **Use case** | Current task, recent decisions, temporary assumptions |

Live shards do not need to become permanent. Memory has a lifecycle.

### Project Memory

| Property | Value |
|----------|-------|
| **Domain** | `ShardDomain.PROJECT` |
| **Lifespan** | Persistent |
| **Authority** | 0.8 |
| **Eviction** | Policy-driven |
| **Typical shards** | Architecture, Decisions, Research, Documents, Agents, Data |
| **Use case** | Project identity, history, decisions, artifacts |

Project memory has its own identity, history, and knowledge graph. An agent working on Project A does not need to know Project B exists.

### Enterprise / Organization Memory

| Property | Value |
|----------|-------|
| **Domain** | `ShardDomain.ENTERPRISE` |
| **Lifespan** | Persistent |
| **Authority** | 1.0 |
| **Eviction** | Policy-driven |
| **Typical shards** | Policies, Governance, SOPs, Compliance, Architecture, Shared datasets, Security policies |
| **Use case** | Institutional knowledge, governance, compliance |

Enterprise memory contains knowledge belonging to the organization rather than a specific project.

## The Lifecycle (Promotion / Demotion / Application)

```
LIVE ──promotion──▶ PROJECT ──institutionalization──▶ ENTERPRISE
 │                     │                              │
 │                     │  demotion                    │  apply_context
 │                     │◀─────────────────────────────│
 │◀────────────────────│
 │  apply_context
 └─────────────────────│
```

- **Promotion** (`LIVE → PROJECT`): Decision becomes part of project history. Requires policy approval.
- **Promotion** (`PROJECT → ENTERPRISE`): Discovery becomes an organizational standard. Requires governance approval.
- **Demotion** (`ENTERPRISE → PROJECT`): Policy becomes a project-specific constraint.
- **Application** (context injection): Higher-domain knowledge flows downward without promotion. Creates a `ContextSnapshot` that exists only for the duration of reasoning.

**Critical**: Promotion is a state transition that creates a new shard with a new hash, new permissions, and parent reference. The original shard is never modified.

## The MemoGraph

The MemoGraph is the topological layer connecting all memory across domains:

- **Nodes**: MemoryShards (content-addressed by SHA256 hash)
- **Edges**: Parent references, cross-stream relationships, temporal ordering
- **Properties**: Each edge can itself be addressable and verifiable

The graph supports:
- Lineage tracing (back through parent hashes)
- Cross-domain traversal (follow relationships across streams)
- Version chains (track evolution of a concept)
- Causal links (decision → conversation → research → dataset → model)

## Context Routing

The ContextRouter is the intelligence layer. It evaluates memory based on multiple dimensions:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| **semantic** | 0.40 | Cosine similarity to query (embedding-based) |
| **recency** | 0.25 | Exponential decay based on age |
| **authority** | 0.20 | Domain-level trust (LIVE=0.5, PROJECT=0.8, ENTERPRISE=1.0) |
| **affinity** | 0.15 | Project/organization proximity |

Additional scoring dimensions (configurable): provenance, temporal validity, access policy, ownership.

The router does NOT decide what the agent retrieves. It ranks candidates by contextual score. The agent decides.

## Heterogeneous Retrieval

| Content Type | Engine | Retrieval Method |
|-------------|--------|-----------------|
| CONVERSATIONAL | Semantic | Vector similarity (HEKTOR) |
| SOURCE_CODE | Structured | AST/symbol lookup |
| DOCUMENT | Lexical | Full-text search |
| DATASET | Temporal | Time-series/range queries |
| DECISION | Semantic | Vector similarity |
| POLICY | Graph | Relationship traversal |
| GRAPH | Graph | Graph traversal |
| EPISTEMIC | Semantic | Meta-knowledge vectors |

The `AdapterRegistry` maps content types to specialized engines. The router delegates to the appropriate adapter based on shard content type.

## Authentication & Authorization

- **PermissionEngine**: Evaluates authorization rules
- **PermissionContext**: Request context for authorization checks
- **PolicyDecision**: ALLOW, DENY, CONDITIONAL, REQUIRES_REVIEW
- **PolicyRule**: Individual authorization rules with conditions

Every access to a memory shard is verified against the engine's policy.

## Audit Trail

Every meaningful memory mutation is recorded as a `MemoryEvent`:

```
Event #12831
├── id: 12831
├── event_type: PROMOTED
├── actor: "agent-001"
├── scope: "project:payment-service"
├── previous_state_hash: "a7f9..."
├── new_state_hash: "8d21..."
├── reason: "Architecture decision for v2.0 migration"
├── evidence: {"plan": "migration_plan_v2.pdf"}
├── model_version: "claude-sonnet-4"
├── parent_event_hash: "3b7c..."
├── timestamp: 1718323232.123
└── event_hash: "9f2c..."
```

The hash chain enables:
- Machine-verifiable provenance
- Temporal reconstruction of agent decision context
- Forensic analysis of how memory evolved
- "What did the agent know when it made this decision?"

## Memory Specialization

Different memory shards use different retrieval mechanisms:
- **Conversational shards** → semantic embeddings
- **Source code shards** → lexical and structural indexing
- **Financial data shards** → numerical or temporal indexing
- **Knowledge graph shards** → graph traversal
- **Sensor data shards** → multidimensional vector indices
- **Document archives** → full-text search
- **Project dependency graphs** → relationship traversal

The router doesn't care how retrieval works internally. It cares about retrieving the right evidence.

## Cross-Stream Composition

When a query spans multiple domains:

```python
query = "Why did we choose this architecture?"

# Router finds:
# - Live: current conversation about architecture
# - Project: previous design decisions
# - Enterprise: security and compliance requirements

# Assembled context preserves stream boundaries:
context = {
    "live": [shard_1, shard_2],
    "project": [shard_3],
    "enterprise": [shard_4]
}

# Agent sees which stream each fact came from
# without merging the underlying memories
```

## Multi-Organization Context

Memograph supports agents operating across multiple organizations:

```
Organization A
├── Projects A1, A2, A3
└── Trust boundary: A's credentials

Organization B
├── Projects B1, B2
└── Trust boundary: B's credentials

Agent requests context with appropriate authorization.
Each organization remains its own trust domain.
The router verifies access before composing context.
```

## Configuration

```toml
# pyproject.toml
[tool.memograph]
default_ttl_seconds = 3600
max_context_tokens = 4096
max_candidates = 50
enable_audit = true
default_access_level = "project"

[tool.memograph.engine.semantic]
model = "text-embedding-3-small"
namespace = "memograph"

[tool.memograph.engine.hektor]
endpoint = "http://localhost:8080"
api_key = ""

[tool.memograph.auth]
strict_mode = false
default_policy = "allow"
```

## API Reference

### Core Classes

| Class | Description |
|-------|-------------|
| `MemoryShard` | Content-addressed, auditable memory unit |
| `ShardDomain` | LIVE / PROJECT / ENTERPRISE |
| `MemoGraph` | Topological memory graph |
| `ContextRouter` | Multi-dimensional context scoring |
| `ContextQuery` | User query for context assembly |
| `ContextEnvelope` | Stream-preserved context assembly |
| `MemoryEvent` | Immutable audit event |
| `EventType` | CREATED, PROMOTED, DEMOTED, APPLIED, etc. |
| `ContentType` | CONVERSATIONAL, SOURCE_CODE, DOCUMENT, etc. |
| `RetrievalEngine` | SEMANTIC, STRUCTURED, LEXICAL, etc. |

### Lifecycle Classes

| Class | Description |
|-------|-------------|
| `LifecyclePipeline` | Promotion/demotion state machine |
| `ContextApplication` | Downward context injection |
| `ContextSnapshot` | Ephemeral context for reasoning |
| `MemoryEvictor` | TTL-based forgetting |
| `EvictionStrategy` | TTL, LRU, SIZE, BATCH |
| `EvictionResult` | Eviction operation results |

### Engine Classes

| Class | Description |
|-------|-------------|
| `RetrievalAdapter` | Abstract base for retrieval |
| `AdapterRegistry` | Central adapter registry |
| `SemanticAdapter` | Vector similarity search |
| `HektorAdapter` | HEKTOR-specific semantic search |
| `GraphAdapter` | Graph traversal queries |
| `TemporalAdapter` | Time-series queries |
| `LexicalAdapter` | Full-text search |
| `MemoryStore` | Persistence layer |

### Auth Classes

| Class | Description |
|-------|-------------|
| `PermissionEngine` | Authorization evaluation |
| `PermissionContext` | Authorization request context |
| `PolicyDecision` | ALLOW/DENY/CONDITIONAL |
| `PolicyRule` | Individual authorization rule |

## Running the Project

```bash
# Setup
$ ./setup_project.sh

# Install
$ pip install -e .

# Run tests
$ pytest

# Build package
$ python -m build
```

## Version

0.2.0