"""
KV adapter for fast key-value state persistence.

Provides high-performance key-value access for graph state,
shard metadata, and frequently-accessed memory objects.
"""

from typing import Dict, Any, Optional

from memograph.core.shard import MemoryShard
from memograph.core.types import RetrievalEngine
from memograph.engines.base import RetrievalResult, RetrievalAdapter


class KVAdapter(RetrievalAdapter):
    """
    Key-value adapter for fast state persistence.
    
    Provides:
    - O(1) shard lookup by hash
    - Batch operations for bulk load/save
    - In-memory caching for hot data
    - Pluggable backends (Redis, Memcached, etc.)
    """
    
    def __init__(self, backend: str = "memory"):
        super().__init__(name="kv", engine_type=RetrievalEngine.HYBRID)
        self.backend = backend
        self._store: Dict[str, Any] = {}
    
    def index_shard(self, shard: MemoryShard) -> bool:
        """Index a shard in the KV store."""
        self._store[shard.shard_hash] = shard.to_dict()
        return True
    
    def retrieve(self, query: str, max_results: int = 10,
                 scope: Optional[str] = None,
                 content_types: Optional[List[ContentType]] = None) -> RetrievalResult:
        # KV is for exact lookups, not semantic queries
        # This returns the shard matching the query hash if available
        from memograph.core.shard import MemoryShard, ShardDomain
        from memograph.core.types import ContentType
        
        if query in self._store:
            data = self._store[query]
            shard = MemoryShard.create(
                content=data["content"],
                owner=data["owner"],
                scope=data["scope"],
                domain=ShardDomain(data["domain"]),
                parent_hash=data.get("parent_hash"),
                permissions=data.get("permissions", ["*"]),
                timestamp=data["timestamp"],
                version=data["version"],
                content_type=ContentType(data.get("content_type", "CONVERSATIONAL"))
            )
            return RetrievalResult(
                shards=[shard],
                scores=[1.0],
                metadata={"query": query, "engine": "kv", "match": "exact"},
                total_found=1,
                engine_type=RetrievalEngine.HYBRID
            )
        
        return RetrievalResult(
            shards=[],
            scores=[],
            metadata={"query": query, "engine": "kv"},
            total_found=0,
            engine_type=RetrievalEngine.HYBRID
        )
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value by key (fast lookup)."""
        return self._store.get(key)
    
    def set(self, key: str, value: Any) -> bool:
        """Set a key-value pair."""
        self._store[key] = value
        return True
    
    def delete(self, shard_hash: str) -> bool:
        """Delete a key-value pair."""
        if shard_hash in self._store:
            del self._store[shard_hash]
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine": "kv",
            "backend": self.backend,
            "stored_objects": len(self._store),
            "memory_usage": sum(len(str(v)) for v in self._store.values())
        }