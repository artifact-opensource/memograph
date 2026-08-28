"""
MemoryShard: The fundamental content-addressed memory unit.

Every shard carries:
- Cryptographic identity (SHA256 hash over content + metadata)
- Ownership (who created it)
- Scope (where it belongs - project/organization identifier)
- Domain (Live/Project/Enterprise lifecycle stage)
- Parent reference (for lineage tracking)
- Permissions (access control list)
- Timestamp (creation time)
- Version (monotonic increment)
- Content (the actual data)

Permissions are enforced at write-time and at routing time.
The hash changes if ANY part changes — this is the tamper-evidence mechanism.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum, auto
from typing import Dict, Any, Optional, List


class ShardDomain(Enum):
    """
    The three fundamental memory domains.
    
    Each domain has a distinct lifecycle and authority level:
    - LIVE: Ephemeral, task-specific. Autority 0.5 (lowest).
    - PROJECT: Persistent, project-scoped. Authority 0.8.
    - ENTERPRISE: Institutional, policy-level. Authority 1.0 (highest).
    
    Promotion is not automatic — it requires policy approval.
    """
    LIVE = "live"
    PROJECT = "project"
    ENTERPRISE = "enterprise"


class ContentType(Enum):
    """Content classification for heterogeneous retrieval."""
    CONVERSATIONAL = auto()
    SOURCE_CODE = auto()
    DOCUMENT = auto()
    DATASET = auto()
    GRAPH = auto()
    DECISION = auto()
    POLICY = auto()
    EPISTEMIC = auto()  # Meta-knowledge, reasoning traces


class AccessLevel(Enum):
    """Access levels for permission checks."""
    PUBLIC = "public"
    PROJECT = "project"
    ENTERPRISE = "enterprise"
    RESTRICTED = "restricted"


@dataclass(frozen=False)
class MemoryShard:
    """
    A content-addressed, auditable memory object.
    
    A MemoryShard is immutable in content but can be promoted
    (creating a new shard with updated domain/parent reference).
    
    The compute_hash method produces a SHA256 digest of the full
    payload including content, metadata, and parent reference.
    Any modification of ANY field results in a new hash.
    
    Usage:
        shard = MemoryShard.create(
            content={"decision": "use postgresql"},
            owner="agent-001",
            scope="project:payment-service",
            domain=ShardDomain.PROJECT,
            parent_hash="a7f9...",
            permissions=["project_member"]
        )
    """
    # Content payload
    content: Dict[str, Any]
    
    # Identity / ownership
    owner: str  # Actor or agent identifier
    scope: str  # Project/organization identifier (e.g., "project:fintech")
    
    # Lifecycle domain
    domain: ShardDomain = ShardDomain.LIVE
    
    # Lineage
    parent_hash: Optional[str] = None  # Previous shard in chain
    
    # Access control
    permissions: List[str] = field(default_factory=lambda: ["*"])
    
    # Metadata
    timestamp: float = field(default_factory=time.time)
    version: int = 1
    
    # Content classification (for engine selection)
    content_type: ContentType = ContentType.CONVERSATIONAL
    
    # Cryptographic identity (computed at init)
    shard_hash: str = field(init=False, default="")
    
    def __post_init__(self):
        # Compute hash after all fields are set
        if not self.shard_hash:
            self.shard_hash = self.compute_hash()
    
    def compute_hash(self) -> str:
        """
        Compute the cryptographic identity of this shard.
        
        Includes ALL fields to ensure tamper-evidence.
        Changing content, metadata, permissions, or even timestamp
        produces a different hash.
        
        Returns:
            Hex-encoded SHA256 digest of serialized payload
        """
        payload = {
            "content": self.content,
            "owner": self.owner,
            "scope": self.scope,
            "domain": self.domain.value,
            "parent_hash": self.parent_hash,
            "permissions": sorted(self.permissions),
            "timestamp": self.timestamp,
            "version": self.version,
            "content_type": self.content_type.name,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary (for storage, logging, transmission)."""
        data = {
            "shard_hash": self.shard_hash,
            "content": self.content,
            "owner": self.owner,
            "scope": self.scope,
            "domain": self.domain.value,
            "parent_hash": self.parent_hash,
            "permissions": sorted(self.permissions),
            "timestamp": self.timestamp,
            "version": self.version,
            "content_type": self.content_type.name,
        }
        return data
    
    @classmethod
    def create(cls, content: Dict[str, Any], owner: str, scope: str,
               domain: ShardDomain = ShardDomain.LIVE,
               parent_hash: Optional[str] = None,
               permissions: Optional[List[str]] = None,
               content_type: ContentType = ContentType.CONVERSATIONAL,
               timestamp: Optional[float] = None) -> "MemoryShard":
        """Factory method for creating new shards."""
        return cls(
            content=content,
            owner=owner,
            scope=scope,
            domain=domain,
            parent_hash=parent_hash,
            permissions=permissions or ["*"],
            timestamp=timestamp or time.time(),
            version=1,
            content_type=content_type
        )
    
    def with_version(self, new_version: int) -> "MemoryShard":
        """Create a new version of this shard (same content, new identity)."""
        new_shard = MemoryShard(
            content=self.content.copy(),
            owner=self.owner,
            scope=self.scope,
            domain=self.domain,
            parent_hash=self.shard_hash,
            permissions=self.permissions.copy(),
            timestamp=time.time(),
            version=new_version,
            content_type=self.content_type,
        )
        return new_shard
    
    def with_content(self, new_content: Dict[str, Any]) -> "MemoryShard":
        """Create a new shard with updated content (new identity, same parent)."""
        return MemoryShard.create(
            content=new_content,
            owner=self.owner,
            scope=self.scope,
            domain=self.domain,
            parent_hash=self.shard_hash,
            permissions=self.permissions.copy(),
            content_type=self.content_type,
        )
    
    def __repr__(self) -> str:
        return (f"MemoryShard(hash={self.shard_hash[:16]}..., "
                f"domain={self.domain.value}, owner={self.owner}, "
                f"scope={self.scope}, version={self.version})")
