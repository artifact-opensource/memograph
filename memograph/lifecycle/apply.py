"""
Context Application: Downward context flow.

Implements the inverse of promotion:
- Enterprise policies applied to project context
- Project state influencing live agent behavior
- This is NOT a promotion - it's a context injection

Creates ContextSnapshot objects that are ephemeral and
do not modify persistent memory.
"""

import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from memograph.core.shard import MemoryShard, ShardDomain


@dataclass
class ContextSnapshot:
    """
    A temporary context object for reasoning.
    
    Unlike a MemoryShard, a ContextSnapshot is ephemeral and not
    stored in the memory graph. It exists only for the duration
    of a reasoning task.
    """
    source_shard: MemoryShard
    target_domain: ShardDomain
    applied_by: str
    applied_at: float
    purpose: str = ""
    context_hash: str = field(init=False)
    
    def __post_init__(self):
        self.context_hash = self.source_shard.shard_hash
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_shard_hash": self.source_shard.shard_hash,
            "target_domain": self.target_domain.value,
            "applied_by": self.applied_by,
            "applied_at": self.applied_at,
            "purpose": self.purpose,
            "context_hash": self.context_hash,
        }


def apply_context(source_shard: MemoryShard, target_domain: ShardDomain,
                  actor: str, purpose: str = "") -> ContextSnapshot:
    """
    Apply context from a higher-domain shard to a target domain.
    
    Creates a temporary context object that carries the knowledge
    without promoting it to persistent memory.
    
    Args:
        source_shard: The shard providing context (must be higher domain)
        target_domain: The domain receiving the context
        actor: Who is performing the application
        purpose: Why this application is happening
    
    Returns:
        ContextSnapshot for use in reasoning
    """
    # Verify source is higher than target
    domain_hierarchy = {
        ShardDomain.LIVE: 0,
        ShardDomain.PROJECT: 1,
        ShardDomain.ENTERPRISE: 2
    }
    
    if domain_hierarchy.get(source_shard.domain, 0) < domain_hierarchy.get(target_domain, 0):
        raise ValueError(
            f"Cannot apply {source_shard.domain.value} context to {target_domain.value} "
            "(source must be higher or equal domain)"
        )
    
    return ContextSnapshot(
        source_shard=source_shard,
        target_domain=target_domain,
        applied_by=actor,
        applied_at=time.time(),
        purpose=purpose
    )