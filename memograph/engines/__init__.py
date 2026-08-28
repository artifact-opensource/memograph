"""
Retrieval adapters for heterogeneous memory retrieval.

Each memory shard can have a different content type, requiring
different retrieval strategies. This module provides adapters for:
- Semantic search (HEKTOR/embedding-based)
- Structured data (AST/symbol-based for code)
- Lexical search (full-text)
- Temporal indexing (time-series)
- Graph traversal (relationship queries)
- Hybrid retrieval (multi-engine composition)

The router delegates to the appropriate adapter based on the
shard and content type.
"""

from memograph.engines.base import RetrievalAdapter
from memograph.engines.semantic_adapter import SemanticAdapter, HektorAdapter
from memograph.engines.structured_adapter import StructuredAdapter
from memograph.engines.graph_adapter import GraphAdapter
from memograph.engines.temporal_adapter import TemporalAdapter
from memograph.engines.lexical_adapter import LexicalAdapter
from memograph.engines.kv_adapter import KVAdapter

__all__ = [
    "RetrievalAdapter",
    "SemanticAdapter",
    "StructuredAdapter",
    "GraphAdapter",
    "TemporalAdapter",
    "LexicalAdapter",
    "HektorAdapter",
    "KVAdapter",
]