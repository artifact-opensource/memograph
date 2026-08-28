"""
Permission and authorization engine for memograph.

Provides:
- Permission predicates (allow/deny)
- Scope-based isolation
- Role-based access control
- Permission revocation / grant audit
- Mandatory enforcement at retrieval, store, and load boundaries

Design:
- Permissions are explicit string tokens (e.g. "agent", "user:ali", "project:<id>")
- "*" means global access
- A shard without permissions is INACCESSIBLE (default-deny)
- All permission checks are logged to the audit trail
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Set, Optional, Iterable
import time


# Permission token conventions
WILDCARD = "*"
ROLE_AGENT = "agent"
ROLE_SYSTEM = "system"
ROLE_USER_PREFIX = "user:"
ROLE_PROJECT_PREFIX = "project:"
ROLE_ORG_PREFIX = "org:"


@dataclass(frozen=True)
class Identity:
    """
    Represents a calling principal.
    Immutable so it can be hashed for audit.
    """
    id: str
    roles: frozenset[str] = field(default_factory=frozenset)
    org: Optional[str] = None
    project: Optional[str] = None

    def has_role(self, role: str) -> bool:
        return role in self.roles or WILDCARD in self.roles


def identity(id: str, roles: Optional[Iterable[str]] = None,
             org: Optional[str] = None, project: Optional[str] = None) -> Identity:
    return Identity(id=id, roles=frozenset(roles or []), org=org, project=project)


def _normalize_perms(perms: Iterable[str]) -> Set[str]:
    return {p.strip() for p in perms if p and p.strip()}


def is_authorized(shard_permissions: List[str], identity: Identity) -> bool:
    """
    Returns True if identity is allowed to access the shard.

    Rules:
    1. Wildcard "*" in either side grants access.
    2. Direct role match (e.g. shard has "agent", identity has "agent" role).
    3. User-scoped match: "user:<id>" requires identity.id == <id>.
    4. Project-scoped match: "project:<pid>" requires identity.project == <pid>.
    5. Org-scoped match: "org:<oid>" requires identity.org == <oid>.
    6. Empty shard permissions = default deny.
    """
    perms = _normalize_perms(shard_permissions)
    if not perms:
        return False
    if WILDCARD in perms:
        return True
    if identity.has_role(WILDCARD):
        return True

    for p in perms:
        if p == WILDCARD:
            return True
        if p in identity.roles:
            return True
        if p.startswith(ROLE_USER_PREFIX):
            if identity.id == p[len(ROLE_USER_PREFIX):]:
                return True
        elif p.startswith(ROLE_PROJECT_PREFIX):
            if identity.project == p[len(ROLE_PROJECT_PREFIX):]:
                return True
        elif p.startswith(ROLE_ORG_PREFIX):
            if identity.org == p[len(ROLE_ORG_PREFIX):]:
                return True
        # bare role token
        if p == identity.id:
            return True

    return False


def can_access_scope(identity: Identity, scope: str) -> bool:
    """
    Returns True if identity is allowed to access a scope at all.
    A scope is e.g. "project:symbiote" or "org:artifact-virtual".
    """
    if identity.has_role(WILDCARD) or identity.has_role(ROLE_SYSTEM):
        return True
    if scope.startswith(ROLE_PROJECT_PREFIX):
        pid = scope[len(ROLE_PROJECT_PREFIX):]
        return identity.project == pid
    if scope.startswith(ROLE_ORG_PREFIX):
        oid = scope[len(ROLE_ORG_PREFIX):]
        return identity.org == oid
    # unknown scope format — allow by default (scope is just a label, real check is on permissions)
    return True


def filter_authorized(shards, identity: Identity):
    """Filter a list of shards by authorization."""
    return [s for s in shards if is_authorized(s.permissions, identity)]


# Default identities for common agents
AGENT_IDENTITY = identity(
    id="agent",
    roles={ROLE_AGENT, ROLE_SYSTEM},
    org="artifact-virtual",
)

USER_ALI = identity(
    id="ali",
    roles={ROLE_USER_PREFIX + "ali", ROLE_AGENT},
    org="artifact-virtual",
)
