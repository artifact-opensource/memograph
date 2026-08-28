"""
Base retrieval adapter interface.

Defines the contract for all memory retrieval mechanisms.
Each adapter implements content-type-specific retrieval:
- SemanticAdapter: vector similarity search
- StructuredAdapter: AST/symbol lookup
- GraphAdapter: graph traversal queries
- TemporalAdapter: time-series/range queries
- LexicalAdapter: full-text search

Adapters are registered with the central registry and invoked
by the ContextRouter based on shard content type.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from memograph.core.shard import MemoryShard
from memograph.core.types import RetrievalEngine, ContentType


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""
    shards: List[MemoryShard]
    scores: List[float]
    metadata: Dict[str, Any] = None
    total_found: int = 0
    engine_type: RetrievalEngine = RetrievalEngine.SEMANTIC
    took_ms: float = 0.0


class RetrievalAdapter(ABC):
    """
    Abstract base class for memory retrieval adapters.
    
    Each adapter is specialized for a particular content type
    and uses the appropriate retrieval mechanism.
    """
    
    def __init__(self, name: str = "", engine_type: RetrievalEngine = None):
        self.name = name or self.__class__.__name__
        self.engine_type = engine_type or RetrievalEngine(self.__class__.__name__.replace("Adapter", "").lower())
        self._initialized = False
    
    @abstractmethod
    def index_shard(self, shard: MemoryShard) -> bool:
        """Index a shard for retrieval. Returns True on success."""
        pass
    
    @abstractmethod
    def retrieve(self, query: str, max_results: int = 10,
                 scope: Optional[str] = None,
                 content_types: Optional[List[ContentType]] = None) -> RetrievalResult:
        """Execute a retrieval query. Returns ranked results."""
        pass
    
    @abstractmethod
    def delete(self, shard_hash: str) -> bool:
        """Remove a shard from the index."""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Return adapter statistics."""
        pass
    
    def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the adapter with configuration."""
        self._config = config or {}
        self._initialized = True
    
    def supports_content_type(self, content_type: ContentType) -> bool:
        """Check if this adapter handles the given content type."""
        return True  # Base class supports all by default


class AdapterRegistry:
    """
    Central registry for retrieval adapters.
    
    Maps content types to their specialized adapters.
    The router uses this registry to select the right engine
    for each shard type.
    """
    
    def __init__(self):
        self._adapters: Dict[ContentType, List[RetrievalAdapter]] = {}
        self._adapter_by_name: Dict[str, RetrievalAdapter] = {}
    
    def register(self, adapter: RetrievalAdapter, 
                 content_types: Optional[List[ContentType]] = None) -> None:
        """Register an adapter for specific content types."""
        self._adapter_by_name[adapter.name] = adapter
        
        if content_types:
            for ct in content_types:
                if ct not in self._adapters:
                    self._adapters[ct] = []
                self._adapters[ct].append(adapter)
        else:
            # Registers as default for all types
            for ct in ContentType:
                if ct not in self._adapters:
                    self._adapters[ct] = []
                self._adapters[ct].insert(0, adapter)  # At front as fallback
    
    def get_adapters(self, content_type: ContentType) -> List[RetrievalAdapter]:
        """Get all adapters that handle a content type."""
        return self._adapters.get(content_type, [self._adapter_by_name.get("default")])
    
    def get_adapter(self, name: str) -> Optional[RetrievalAdapter]:
        """Get a specific adapter by name."""
        return self._adapter_by_name.get(name)
    
    def list_adapters(self) -> List[str]:
        """List all registered adapter names."""
        return list(self._adapter_by_name.keys())