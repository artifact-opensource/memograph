"""
Memograph core module.
"""

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.events import MemoryEvent, EventType
from memograph.core.router import ContextRouter, ContextQuery
from memograph.core.memograph import MemoGraph, ContextEnvelope, SCHEMA_VERSION
from memograph.core.types import ContentType, RetrievalEngine, AccessLevel, ModelInfo
from memograph.lifecycle.pipeline import LifecyclePipeline, LifecycleResult
from memograph.lifecycle.apply import apply_context
from memograph.lifecycle.evictor import MemoryEvictor, EvictionResult
from memograph.auth import is_authorized, identity, AGENT_IDENTITY, USER_ALI

__all__ = [
    "MemoryShard", "ShardDomain", "MemoryEvent", "EventType",
    "ContextRouter", "ContextQuery", "MemoGraph", "ContextEnvelope",
    "ContentType", "RetrievalEngine", "AccessLevel", "ModelInfo",
    "LifecyclePipeline", "LifecycleResult",
    "apply_context",
    "MemoryEvictor", "EvictionResult",
    "is_authorized", "identity", "AGENT_IDENTITY", "USER_ALI",
    "SCHEMA_VERSION",
]
