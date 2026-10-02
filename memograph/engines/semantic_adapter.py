"""Semantic retrieval adapter interface for configured vector backends."""

from typing import List, Dict, Any, Optional

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.types import RetrievalEngine, ContentType
from memograph.engines.base import RetrievalResult
from memograph.engines.base import RetrievalAdapter


class SemanticAdapter(RetrievalAdapter):
    """
    Semantic search adapter using vector embeddings.
    
    Provides cosine similarity search for conversational
    and decision-type memory shards.
    """
    
    def __init__(self, model: str = "text-embedding-3-small",
                 namespace: str = "default"):
        super().__init__(name="semantic", engine_type=RetrievalEngine.SEMANTIC)
        self.model = model
        self.namespace = namespace
        self._vectors: Dict[str, List[float]] = {}
        self._initialized = False
    
    def index_shard(self, shard: MemoryShard) -> bool:
        if shard.content_type not in (ContentType.CONVERSATIONAL, 
                                       ContentType.DECISION,
                                       ContentType.EPISTEMIC):
            return False  # Not a semantic search candidate
        # Embedding generation is supplied by a configured backend.
        return True
    
    def retrieve(self, query: str, max_results: int = 10,
                 scope: Optional[str] = None,
                 content_types: Optional[List[ContentType]] = None) -> RetrievalResult:
        # No semantic backend is configured in the standalone package.
        return RetrievalResult(
            shards=[],
            scores=[],
            metadata={"query": query, "model": self.model},
            total_found=0,
            engine_type=RetrievalEngine.SEMANTIC
        )
    
    def delete(self, shard_hash: str) -> bool:
        if shard_hash in self._vectors:
            del self._vectors[shard_hash]
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "engine": "semantic",
            "indexed_vectors": len(self._vectors),
            "model": self.model,
            "namespace": self.namespace
        }
