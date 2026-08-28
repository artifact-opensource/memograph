# Memograph v0.2.0

This release introduces the full multi-tenant memory architecture.

### Added
- MemoryShard with SHA256 identity
- MemoryEvent audit trail
- ContextRouter multi-dimensional scoring
- MemoGraph with ContextEnvelope stream preservation
- LifecyclePipeline promotion/demotion
- MemoryEvictor TTL-based forgetting
- PermissionEngine authorization
- Seven retrieval adapters (semantic, structured, lexical, temporal, graph, kv, hybrid)
- MemoryStore persistence layer

### Changes
- Renamed from MCP (conflicts with Model Context Protocol)
- Added bidirectional lifecycle management
- Added stream-boundary preservation in context assembly
- Added cryptographic audit trails
