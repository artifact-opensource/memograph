# Memograph API Reference

## Core Module

### `MemoryShard`

Content-addressed memory unit with cryptographic identity.

```python
class MemoryShard:
    content: Dict[str, Any]
    owner: str
    scope: str
    domain: ShardDomain
    parent_hash: Optional[str]
    permissions: List[str]
    timestamp: float
    version: int
    shard_hash: str  # SHA256 of canonical state

    @staticmethod
    def create(content, owner, scope, domain, ...) -> "MemoryShard"
    def to_dict() -> Dict[str, Any]
    @staticmethod
    def from_dict(data) -> "MemoryShard"
```

### `ShardDomain`

```python
class ShardDomain(Enum):
    LIVE = "live"         # Current conversation / ephemeral
    PROJECT = "project"   # Project-level persistent
    ENTERPRISE = "enterprise"  # Org-wide policy
```

### `MemoGraph`

```python
class MemoGraph:
    def add_shard(shard) -> str           # Add shard by hash
    def get_shard(shard_hash) -> Optional[MemoryShard]
    def remove_shard(shard_hash) -> bool
    def get_children(shard_hash) -> List[MemoryShard]
    def get_parents(shard_hash) -> List[MemoryShard]
    def get_lineage(shard_hash, max_depth) -> List[MemoryShard]
    def query_by_domain(domain, scope=None) -> List[MemoryShard]
    def query_by_scope(scope) -> List[MemoryShard]
    def traverse(start_hash, max_depth) -> List[MemoryShard]
    def assemble_context(scored, max_tokens) -> ContextEnvelope
    def save(path) -> None
    @classmethod
    def load(path) -> "MemoGraph"
```

### `ContextEnvelope`

```python
@dataclass
class ContextEnvelope:
    shards: List[MemoryShard]
    domains: Dict[ShardDomain, int]
    total_tokens: int
    max_tokens: int

    def add(shard) -> None
    def by_domain(domain) -> List[MemoryShard]
```

## Router Module

### `ContextRouter`

Multi-dimensional context scoring.

```python
class ContextRouter:
    WEIGHTS = {"semantic": 0.40, "recency": 0.25, "authority": 0.20, "affinity": 0.15}

    def score_shard(shard, query) -> float
    def route(shards, query) -> List[Tuple[MemoryShard, float]]
    def assemble_context(candidates, query, max_tokens=4096) -> List[MemoryShard]
```

### `ContextQuery`

```python
@dataclass
class ContextQuery:
    text: str
    project_id: Optional[str]
    entity_ids: List[str]
    scope: str
    min_tokens: int
    max_tokens: int
```

## Lifecycle Module

### `LifecyclePipeline`

```python
class LifecyclePipeline:
    @staticmethod
    def promote_shard(shard, target_domain, actor) -> LifecycleResult
    @staticmethod
    def demote_shard(shard, target_domain, actor) -> LifecycleResult
    @staticmethod
    def apply_context(source_shard, target_domain, actor, purpose) -> ContextSnapshot
```

### `MemoryEvictor`

```python
class MemoryEvictor:
    def evict_live_shards(graph, ttl_seconds) -> EvictionResult
```

## Engines Module

### `RetrievalAdapter` (Base)

```python
class RetrievalAdapter:
    def index_shard(shard) -> bool
    def retrieve(query, max_results, scope, content_types) -> RetrievalResult
    def delete(shard_hash) -> bool
    def get_stats() -> Dict[str, Any]
```

### Adapters

- `SemanticAdapter` / `HektorAdapter` — vector similarity
- `StructuredAdapter` — AST/symbol lookup
- `LexicalAdapter` — full-text search
- `TemporalAdapter` — time-series queries
- `GraphAdapter` — knowledge graph traversal
- `KVAdapter` — fast key-value state

## Auth Module

### `PermissionEngine`

```python
class PermissionEngine:
    def check(context: PermissionContext) -> PolicyDecision
    def can_read(context) -> bool
    def can_write(context) -> bool
    def can_promote(context) -> bool
```

## Tools Module

### `memograph_tool(session_id, storage_dir, default_owner)`

Factory for the agent-callable tool.

```python
from memograph import memograph_tool
tool = memograph_tool("agent-001")
```

### `MemographTool`

```python
class MemographTool:
    def __call__(
        action="retrieve" | "store" | "promote" | "evict" | "audit" | "status" | "query_traits",
        query="",
        shard_hash="",
        content=None,
        domain="live" | "project" | "enterprise",
        scope="",
        owner="",
        max_tokens=4096,
        max_results=10,
        metadata=None,
    ) -> ToolResponse

    def inject_into_context(query, **kwargs) -> str
    def store_decision(decision, scope, domain, **kwargs) -> str
    def retrieve_for_decision(question, max_tokens=2048) -> ToolResponse
```

### `ToolResponse`

```python
@dataclass
class ToolResponse:
    success: bool
    action: str
    message: str
    context: Optional[Dict[str, Any]]   # Inject this into agent context
    shard_hash: str
    shard_count: int
    domains: List[str]
    audit_trail: List[Dict[str, Any]]
    injected_tokens: int
    error: str

    def to_context_string() -> str     # Pre-formatted for prompt injection
    def to_dict() -> Dict[str, Any]
```

### `MEMOGRAPH_TOOL_MANIFEST`

Hermes/MCP-compatible tool manifest dict for native agent tool registration.

## Events Module

### `MemoryEvent`

```python
class MemoryEvent:
    event_id: int
    event_type: EventType
    actor: str
    scope: str
    parent_hash: str
    previous_state_hash: str
    new_state_hash: str
    reason: str
    evidence: Dict[str, Any]
    model_version: str
    timestamp: float
    event_hash: str  # Hash chain link
```

### `EventType`

```python
class EventType(Enum):
    CREATED = "created"
    UPDATED = "updated"
    PROMOTED = "promoted"
    DEMOTED = "demoted"
    EVICTED = "evicted"
    ACCESSED = "accessed"
    APPLIED = "applied"
```
