"""
Default permission engine for Memograph.

Provides reasonable defaults:
- Public shards: anyone can read
- Project shards: only project members
- Enterprise shards: only enterprise users
- Restricted shards: requires explicit permission

Usage:
    engine = default_engine
    if engine.verify_access(shard, actor="user-123", action="read"):
        # allowed
"""

from memograph.auth.permissions import PermissionEngine, PolicyDecision

# Use the same default engine instance
default_engine = PermissionEngine()
default_engine.default_policy = "allow"
default_engine.strict_mode = False

__all__ = ["default_engine", "PermissionEngine", "PolicyDecision"]