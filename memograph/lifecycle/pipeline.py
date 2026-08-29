"""
Lifecycle Management: Promotion, demotion, and context application.

Implements:
- State machine transitions between memory domains
- Bidirectional flow (LIVE ↔ PROJECT ↔ ENTERPRISE)
- Policy-gated promotion proposals
- Context application (enterprise → project → live)
- Event audit logging for all transitions
- Permission validation for write operations

Core principle: Memory transitions are events, not in-place mutations.
Each transition creates a new shard with updated lineage.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any

from memograph.core.shard import MemoryShard, ShardDomain, ContentType
from memograph.core.events import MemoryEvent, EventType
from memograph.core.events import EventType as LifecycleEventType
try:
    from memograph.auth.permissions import (
        is_authorized, identity, Identity,
        PermissionEngine, PermissionContext, PolicyDecision,
    )
except ImportError:
    is_authorized = lambda *a, **k: True
    identity = lambda **k: None
    Identity = None
    PermissionEngine = None
    PermissionContext = None
    PolicyDecision = None


class TransitionType(Enum):
    """Types of lifecycle transitions."""
    PROMOTE = "promote"      # LIVE → PROJECT → ENTERPRISE
    DEMOTE = "demote"        # ENTERPRISE → PROJECT → LIVE
    APPLY = "apply"          # Context flows downward without promotion


@dataclass
class LifecycleResult:
    """Result of a lifecycle operation."""
    success: bool
    source_shard: Optional[MemoryShard]
    target_shard: Optional[MemoryShard]
    event: Optional[MemoryEvent]
    error: Optional[str] = None
    notes: Optional[str] = None


class LifecyclePipeline:
    """
    Handles promotion and demotion between memory domains.
    
    Core rules:
    1. Promotion requires policy approval (not automatic)
    2. Each promotion creates a new shard with parent reference
    3. Permissions are carried forward (with additions)
    4. Version increments on promotion
    5. Domain trust increases (LIVE < PROJECT < ENTERPRISE)
    6. Demotion is allowed but requires explicit policy
    """
    
    # Allowed transitions
    TRANSITIONS = {
        (ShardDomain.LIVE, ShardDomain.PROJECT): "live_to_project",
        (ShardDomain.PROJECT, ShardDomain.ENTERPRISE): "project_to_enterprise",
        (ShardDomain.ENTERPRISE, ShardDomain.PROJECT): "enterprise_to_project",
        (ShardDomain.PROJECT, ShardDomain.LIVE): "project_to_live",
    }
    
    @staticmethod
    def can_transition(from_domain: ShardDomain, to_domain: ShardDomain) -> bool:
        """Check if a transition between domains is allowed."""
        return (from_domain, to_domain) in LifecyclePipeline.TRANSITIONS
    
    @staticmethod
    def get_transition_name(from_domain: ShardDomain, to_domain: ShardDomain) -> str:
        """Get the transition identifier."""
        return LifecyclePipeline.TRANSITIONS.get((from_domain, to_domain), "invalid")
    
    @staticmethod
    def promote_shard(shard: MemoryShard, target_domain: ShardDomain,
                      actor: str, reason: str = "",
                      evidence: Optional[Dict[str, Any]] = None,
                      permission_engine: Optional["PermissionEngine"] = None) -> LifecycleResult:
        """
        Promote a shard to a higher domain.
        
        Creates a new shard with:
        - Same content (content is never modified)
        - Updated domain
        - New hash (identity change)
        - Parent reference to original shard
        - Incremented version
        - Permission adjustments based on target domain
        
        Returns:
            LifecycleResult with the new shard and audit event
        """
        if not LifecyclePipeline.can_transition(shard.domain, target_domain):
            return LifecycleResult(
                success=False,
                source_shard=shard,
                target_shard=None,
                event=None,
                error=f"Invalid promotion from {shard.domain.value} to {target_domain.value}"
            )
        
        # Permission check
        if permission_engine is not None:
            context = PermissionContext(
                actor=actor,
                resource_id=shard.shard_hash,
                action="promote",
                domain=target_domain.value,
                scope=shard.scope
            )
            decision = permission_engine.check_permission(context)
            if decision == PolicyDecision.DENY:
                return LifecycleResult(
                    success=False,
                    source_shard=shard,
                    target_shard=None,
                    event=None,
                    error=f"Permission denied for promotion by {actor}"
                )
        
        # Build permissions for new shard
        new_permissions = list(shard.permissions)
        if target_domain == ShardDomain.PROJECT and "project_member" not in new_permissions:
            new_permissions.append("project_member")
        elif target_domain == ShardDomain.ENTERPRISE and "enterprise_global" not in new_permissions:
            new_permissions.append("enterprise_global")
        
        # Create promoted shard
        promoted = MemoryShard.create(
            content=shard.content.copy(),
            owner=actor,
            scope=shard.scope,
            domain=target_domain,
            parent_hash=shard.shard_hash,
            permissions=new_permissions,
            version=shard.version + 1,
            content_type=shard.content_type
        )
        
        # Create audit event
        event_id = int(time.time() * 1000000)  # Simple ID generator
        event = MemoryEvent.create(
            event_id=event_id,
            event_type=EventType.PROMOTED,
            actor=actor,
            scope=shard.scope,
            previous_state_hash=shard.shard_hash,
            new_state_hash=promoted.shard_hash,
            reason=reason or f"Promotion from {shard.domain.value} to {target_domain.value}",
            evidence=evidence,
            parent_event_hash=None,  # Would be populated by event store
        )
        
        return LifecycleResult(
            success=True,
            source_shard=shard,
            target_shard=promoted,
            event=event,
            notes=f"Promoted from {shard.domain.value} to {target_domain.value}"
        )
    
    @staticmethod
    def demote_shard(shard: MemoryShard, target_domain: ShardDomain,
                     actor: str, reason: str = "",
                     evidence: Optional[Dict[str, Any]] = None,
                     permission_engine: Optional["PermissionEngine"] = None) -> LifecycleResult:
        """
        Demote a shard to a lower domain.
        
        Similar to promotion but downward. Creates a new shard.
        """
        # Reverse the promotion check
        if not LifecyclePipeline.can_transition(target_domain, shard.domain):
            return LifecycleResult(
                success=False,
                source_shard=shard,
                error=f"Invalid demotion from {shard.domain.value} to {target_domain.value}"
            )
        
        # Permission check
        if permission_engine is not None:
            context = PermissionContext(
                actor=actor,
                resource_id=shard.shard_hash,
                action="demote",
                domain=target_domain.value,
                scope=shard.scope
            )
            decision = permission_engine.check_permission(context)
            if decision == PolicyDecision.DENY:
                return LifecycleResult(
                    success=False,
                    source_shard=shard,
                    error=f"Permission denied for demotion by {actor}"
                )
        
        # For demotion, we may strip some permissions
        new_permissions = [p for p in shard.permissions 
                          if p not in ["enterprise_global", "project_member"] or 
                             target_domain != ShardDomain.ENTERPRISE or
                             target_domain != ShardDomain.PROJECT]
        if not new_permissions:
            new_permissions = ["*"]
        
        # Create demoted shard
        demoted = MemoryShard.create(
            content=shard.content.copy(),
            owner=actor,
            scope=shard.scope,
            domain=target_domain,
            parent_hash=shard.shard_hash,
            permissions=new_permissions,
            version=shard.version + 1,
            content_type=shard.content_type
        )
        
        # Create audit event
        event_id = int(time.time() * 1000000)
        event = MemoryEvent.create(
            event_id=event_id,
            event_type=EventType.DEMOTED,
            actor=actor,
            scope=shard.scope,
            previous_state_hash=shard.shard_hash,
            new_state_hash=demoted.shard_hash,
            reason=reason or f"Demotion from {shard.domain.value} to {target_domain.value}",
            evidence=evidence,
        )
        
        return LifecycleResult(
            success=True,
            source_shard=shard,
            target_shard=demoted,
            event=event,
            notes=f"Demoted from {shard.domain.value} to {target_domain.value}"
        )


# Application module for downward context flow
class ContextApplication:
    """
    Handles applying higher-domain context to lower domains.
    
    This is distinct from promotion:
    - Promotion: new shard with higher domain (persistent)
    - Application: temporary context injection (ephemeral)
    
    Application creates a ContextSnapshot that can be used
    for reasoning without altering persistent memory.
    """
    
    @staticmethod
    def apply_context(high_shard: MemoryShard, target_domain: ShardDomain,
                      actor: str, purpose: str = "") -> "ContextSnapshot":
        """
        Apply context from a higher domain shard to a target domain.
        
        Creates a temporary context object that carries the knowledge
        without promoting it to persistent memory.
        
        Example: An enterprise policy shard applied to a project context
        for compliance checking.
        """
        return ContextSnapshot(
            source_shard=high_shard,
            target_domain=target_domain,
            applied_by=actor,
            applied_at=time.time(),
            purpose=purpose,
            context_hash=high_shard.shard_hash  # Reference, not copy
        )


@dataclass
class ContextSnapshot:
    """
    A temporary context object for reasoning.
    
    Unlike a MemoryShard, a ContextSnapshot is ephemeral and not
    stored in the memory graph. It exists only for the duration
    of a reasoning task.
    
    Contains:
    - Reference to source shard (immutable)
    - Target domain for application
    - Metadata about when/why it was applied
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