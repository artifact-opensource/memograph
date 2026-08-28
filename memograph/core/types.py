"""
Shared types, enums, and constants for Memograph.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Any, List, Optional


class ContentType(Enum):
    """Classification of memory content for heterogeneous retrieval."""
    CONVERSATIONAL = auto()
    SOURCE_CODE = auto()
    DOCUMENT = auto()
    DATASET = auto()
    GRAPH = auto()
    DECISION = auto()
    POLICY = auto()
    EPISTEMIC = auto()  # Meta-knowledge, reasoning traces
    
    def get_default_engine(self) -> 'RetrievalEngine':
        """Map content type to appropriate retrieval engine."""
        mapping = {
            self.CONVERSATIONAL: RetrievalEngine.SEMANTIC,
            self.SOURCE_CODE: RetrievalEngine.STRUCTURED,
            self.DOCUMENT: RetrievalEngine.LEXICAL,
            self.DATASET: RetrievalEngine.TEMPORAL,
            self.GRAPH: RetrievalEngine.GRAPH,
            self.DECISION: RetrievalEngine.SEMANTIC,
            self.POLICY: RetrievalEngine.GRAPH,
            self.EPISTEMIC: RetrievalEngine.SEMANTIC,
        }
        return mapping.get(self, RetrievalEngine.SEMANTIC)


class RetrievalEngine(Enum):
    """Available retrieval engine types for heterogeneous memory."""
    SEMANTIC = "semantic"      # HEKTOR-based vector search
    STRUCTURED = "structured"  # Symbol/AST-based for code
    LEXICAL = "lexical"        # Full-text search
    TEMPORAL = "temporal"      # Time-series / interval indexing
    GRAPH = "graph"            # Graph traversal / relationship queries
    HYBRID = "hybrid"          # Multi-engine composite


class AccessLevel(Enum):
    """Access control levels."""
    PUBLIC = "public"          # No restrictions
    PROJECT = "project"        # Project members only
    ENTERPRISE = "enterprise"  # Organization-wide
    RESTRICTED = "restricted"  # Role-based, audited access


class ModelInfo:
    """Metadata about the AI model that created or influenced a memory."""
    
    def __init__(self, model_id: str, provider: str = "openai",
                 version: str = "1.0", capabilities: Optional[List[str]] = None,
                 parameters: Optional[Dict[str, Any]] = None):
        self.model_id = model_id
        self.provider = provider
        self.version = version
        self.capabilities = capabilities or []
        self.parameters = parameters or {}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "provider": self.provider,
            "version": self.version,
            "capabilities": self.capabilities,
            "parameters": self.parameters,
        }


@dataclass
class RetrievalConfig:
    """Configuration for retrieval operations."""
    max_tokens: int = 4096
    min_relevance_score: float = 0.5
    max_results: int = 10
    include_provenance: bool = True
    include_policy_context: bool = True
    token_budget: Optional[int] = None
    engines: Optional[List[RetrievalEngine]] = None
    
    def __post_init__(self):
        if self.token_budget is None:
            self.token_budget = self.max_tokens


@dataclass
class MemoryMetrics:
    """Metrics about memory usage and performance."""
    total_shards: int = 0
    total_tokens: int = 0
    domain_counts: Dict[str, int] = field(default_factory=dict)
    event_count: int = 0
    oldest_timestamp: Optional[float] = None
    newest_timestamp: Optional[float] = None
    evicted_count: int = 0