"""
Memograph: Topological Memory Management Framework for AI Agents
"""
from memograph.__version__ import __version__

# Core
from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.events import MemoryEvent, EventType
from memograph.core.router import ContextRouter, ContextQuery
from memograph.core.memograph import MemoGraph, ContextEnvelope
from memograph.core.types import ContentType, RetrievalEngine, AccessLevel, ModelInfo

# Lifecycle
from memograph.lifecycle.pipeline import LifecyclePipeline, LifecycleResult
from memograph.lifecycle.apply import apply_context
from memograph.lifecycle.evictor import MemoryEvictor, EvictionResult

# Engines
from memograph.engines.base import RetrievalAdapter, AdapterRegistry, RetrievalResult
from memograph.engines.semantic_adapter import SemanticAdapter, HektorAdapter
from memograph.engines.structured_adapter import StructuredAdapter
from memograph.engines.graph_adapter import GraphAdapter
from memograph.engines.temporal_adapter import TemporalAdapter
from memograph.engines.lexical_adapter import LexicalAdapter
from memograph.engines.kv_adapter import KVAdapter
from memograph.engines.memory_store import MemoryStore

# Auth
from memograph.auth import is_authorized, identity, AGENT_IDENTITY, USER_ALI

# Tool integration (last because it depends on lifecycle)
from memograph.tools import (
    MemographTool, MemographAgentSession, ToolRequest, ToolResponse,
    ToolAction, memograph_tool, MEMOGRAPH_TOOL_MANIFEST,
)

# Aliases for backward compat
PromotionResult = LifecycleResult
ContextApplication = apply_context

__all__ = [
    "__version__",
    # Core
    "MemoryShard", "ShardDomain", "MemoryEvent", "EventType",
    "ContextRouter", "ContextQuery", "MemoGraph", "ContextEnvelope",
    "ContentType", "RetrievalEngine", "AccessLevel", "ModelInfo",
    # Lifecycle
    "LifecyclePipeline", "LifecycleResult", "PromotionResult",
    "apply_context", "ContextApplication",
    "MemoryEvictor", "EvictionResult",
    # Engines
    "RetrievalAdapter", "AdapterRegistry", "RetrievalResult",
    "SemanticAdapter", "HektorAdapter", "StructuredAdapter", "GraphAdapter",
    "TemporalAdapter", "LexicalAdapter", "KVAdapter", "MemoryStore",
    # Auth
    "PermissionEngine", "PermissionContext", "PolicyDecision",
    # Tool integration
    "MemographTool", "MemographAgentSession", "ToolRequest", "ToolResponse",
    "ToolAction", "memograph_tool", "MEMOGRAPH_TOOL_MANIFEST",
]
