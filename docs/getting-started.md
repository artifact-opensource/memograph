# Getting Started with Memograph

## Installation

```bash
# From PyPI (when published)
pip install memograph

# From source
git clone https://github.com/artifact-opensource/memory_context_protocol.git
cd memory_context_protocol
pip install -e .
```

## Your First Memory

```python
from memograph import MemoryShard, ShardDomain, MemoGraph

graph = MemoGraph()

shard = MemoryShard.create(
    content={"task": "build payments API", "priority": "high"},
    owner="agent-001",
    scope="project:payments",
    domain=ShardDomain.LIVE,
)

graph.add_shard(shard)
print(f"Shard hash: {shard.shard_hash}")
```

## Using the Agent Tool

```python
from memograph import memograph_tool

# Get a tool instance for this agent session
tool = memograph_tool(session_id="agent-001")

# Store a decision
tool(
    action="store",
    query="We chose PostgreSQL for the payments database",
    content={"db": "postgresql", "reason": "ACID compliance"},
    domain="project",
    scope="payments"
)

# Retrieve relevant memory
result = tool(action="retrieve", query="payments database decision")
print(result.to_context_string())  # Inject this into your LLM prompt
```

## Querying Across Domains

```python
from memograph import ContextRouter, ContextQuery, ShardDomain

router = ContextRouter()

# Search live + project memory
candidates = (
    graph.query_by_domain(ShardDomain.LIVE) +
    graph.query_by_domain(ShardDomain.PROJECT)
)

query = ContextQuery(text="database architecture decisions")
scored = router.route(candidates, query)

# Token-capped assembly
context = graph.assemble_context(scored, max_tokens=2048)
for shard in context.shards:
    print(shard.content)
```

## Lifecycle: Promote a Decision to Enterprise

```python
from memograph import LifecyclePipeline, ShardDomain

result = LifecyclePipeline.promote_shard(
    shard=decision_shard,
    target_domain=ShardDomain.ENTERPRISE,
    actor="architect-lead",
    reason="Adopted as company-wide standard"
)

if result.success:
    graph.add_shard(result.target_shard)
```

## Persistence

```python
# Save session
graph.save(".memograph_storage/agent-001.json")

# Load session
from memograph import MemoGraph
graph = MemoGraph.load(".memograph_storage/agent-001.json")
```

## Quick Reference

| Action | Method |
|--------|--------|
| Create memory | `MemoryShard.create(...)` |
| Add to graph | `graph.add_shard(shard)` |
| Query by domain | `graph.query_by_domain(ShardDomain.LIVE)` |
| Score candidates | `router.route(shards, query)` |
| Assemble context | `graph.assemble_context(scored, max_tokens=N)` |
| Store (tool) | `tool(action="store", query="...", ...)` |
| Retrieve (tool) | `tool(action="retrieve", query="...")` |
| Promote | `LifecyclePipeline.promote_shard(shard, target_domain)` |
| Save graph | `graph.save("path.json")` |
| Load graph | `MemoGraph.load("path.json")` |
