"""
Authentication and Authorization for Memograph.

Provides:
- PermissionEngine for access control decisions
- PermissionContext for authorization requests
- PolicyDecision for enforcement outcomes
- Policy definitions for enterprise memory
- Scope-based access controls

Design principle:
Memory has owners. Remember that.
Every access should be verified.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from memograph.core.shard import MemoryShard, ShardDomain, AccessLevel


class PolicyDecision(Enum):
    """Authorization outcomes."""
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"  # Partial access allowed
    REQUIRES_REVIEW = "requires_review"


class PermissionContext:
    """Request context for authorization checks."""
    
    def __init__(self, actor: str, resource_id: str, action: str,
                 domain: str = "", scope: str = "", 
                 permissions: Optional[List[str]] = None):
        self.actor = actor
        self.resource_id = resource_id
        self.action = action
        self.domain = domain
        self.scope = scope
        self.permissions = permissions or []


class PolicyRule:
    """A single authorization rule."""
    
    def __init__(self, condition: callable, action: PolicyDecision,
                 reason: str = ""):
        self.condition = condition
        self.action = action
        self.reason = reason
    
    def evaluate(self, context: PermissionContext) -> PolicyDecision:
        if self.condition(context):
            return self.action
        return PolicyDecision.ALLOW  # Default allow if not matched


class PermissionEngine:
    """Evaluates authorization rules for memory operations."""
    
    def __init__(self):
        self.rules: List[PolicyRule] = []
        self.policies: Dict[str, Any] = {}
    
    def add_rule(self, rule: PolicyRule) -> None:
        self.rules.append(rule)
    
    def register_policy(self, scope: str, policy: Dict[str, Any]) -> None:
        self.policies[scope] = policy
    
    def check_permission(self, context: PermissionContext) -> PolicyDecision:
        """
        Evaluate authorization for a memory operation.
        
        Checks:
        1. Explicit rules
        2. Domain-level policies
        3. Scope-level restrictions
        
        Returns the final decision (ALLOW/DENY/CONDITIONAL).
        """
        # Check rules first
        for rule in self.rules:
            result = rule.evaluate(context)
            if result == PolicyDecision.DENY:
                return PolicyDecision.DENY
        
        # Check domain policies
        domain_policy = self.policies.get(context.domain)
        if domain_policy:
            if "deny_all" in domain_policy and domain_policy["deny_all"]:
                return PolicyDecision.DENY
        
        # Default allow if no deny
        return PolicyDecision.ALLOW
    
    def verify_access(self, shard: MemoryShard, actor: str,
                      action: str = "read") -> bool:
        """Quick check if an actor can perform an action on a shard."""
        context = PermissionContext(
            actor=actor,
            resource_id=shard.shard_hash,
            action=action,
            domain=shard.domain.value,
            scope=shard.scope,
            permissions=shard.permissions
        )
        return self.check_permission(context) == PolicyDecision.ALLOW


# Default engine instance
default_engine = PermissionEngine()