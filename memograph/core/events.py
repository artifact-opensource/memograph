"""
MemoryEvent: Append-only audit log for memory mutations.

Every meaningful memory operation is recorded as an event.
Events form a chain — each event references the previous state
via its hash. This enables:
- Machine-verifiable provenance
- Temporal reconstruction of agent decision context
- Tamper-evident audit trails
- Forensic analysis of how memory evolved

Design:
- Immutable, append-only records
- Self-referential via parent_event_hash
- No overwrites, ever
- Serialized as JSON for storage

Example event:
    MemoryEvent #12831
    Parent: A7F9...
    Previous State: 19AC...
    New State: 8D21...
    Actor: Agent / User / System
    Scope: Project X
    Timestamp: 1718323232.123
    Reason: Architecture Decision
    Evidence: "v2.0 migration plan approved"
    Hash: 9f2c...

This event proves: "at time T, actor A,
transitioned memory from state X to state Y,
because of reason R, with evidence E."
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class EventType(Enum):
    """Classification of memory operations."""
    CREATED = "created"          # New shard created
    PROMOTED = "promoted"        # Shard moved to higher domain
    DEMOTED = "demoted"          # Shard moved to lower domain
    APPLIED = "applied"          # Context applied to target
    UPDATED = "updated"          # Content modified (new version)
    EVICTED = "evicted"          # Removed due to TTL/pressure
    LINKED = "linked"            # New edge created in graph
    POLICY_GATE = "policy_gate"  # Policy decision recorded


@dataclass(frozen=True)
class MemoryEvent:
    """
    An immutable record of a memory state transition.
    
    All events are append-only. The event_hash is computed over
    all fields including parent_event_hash, creating a chain
    that can be verified end-to-end.
    
    Attributes:
        id: Unique event identifier (sequential or UUID)
        event_type: What kind of operation occurred
        actor: Who performed it (agent, user, system)
        scope: Project/organization context
        previous_state_hash: Hash of previous shard state
        new_state_hash: Hash of new shard state
        reason: Why this change occurred (human-readable)
        evidence: Supporting data or context
        model_version: Which AI model made this decision (if applicable)
        parent_event_hash: Previous event in the chain
        timestamp: When this event occurred
        event_hash: Cryptographic identity of this event
    """
    # Identity
    id: int
    event_type: EventType
    actor: str
    scope: str
    
    # State transition
    previous_state_hash: Optional[str]
    new_state_hash: str
    
    # Context
    reason: str
    evidence: Optional[Dict[str, Any]] = None
    model_version: Optional[str] = None
    
    # Chain continuity
    parent_event_hash: Optional[str] = None
    
    # Temporal
    timestamp: float = field(default_factory=time.time)
    
    # Cryptographic identity (computed after all fields set)
    event_hash: str = field(init=False, default="")

    def __post_init__(self):
        if not self.event_hash:
            self.event_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute hash over all fields including parent event hash."""
        payload = {
            "id": self.id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "scope": self.scope,
            "previous_state_hash": self.previous_state_hash,
            "new_state_hash": self.new_state_hash,
            "reason": self.reason,
            "evidence": self.evidence,
            "model_version": self.model_version,
            "parent_event_hash": self.parent_event_hash,
            "timestamp": self.timestamp,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "scope": self.scope,
            "previous_state_hash": self.previous_state_hash,
            "new_state_hash": self.new_state_hash,
            "reason": self.reason,
            "evidence": self.evidence,
            "model_version": self.model_version,
            "parent_event_hash": self.parent_event_hash,
            "timestamp": self.timestamp,
            "event_hash": self.event_hash,
        }
    
    @classmethod
    def create(cls, event_id: int, event_type: EventType, actor: str,
               scope: str, new_state_hash: str, reason: str,
               previous_state_hash: Optional[str] = None,
               evidence: Optional[Dict[str, Any]] = None,
               model_version: Optional[str] = None,
               parent_event_hash: Optional[str] = None,
               timestamp: Optional[float] = None) -> "MemoryEvent":
        """Factory method for creating new events."""
        return cls(
            id=event_id,
            event_type=event_type,
            actor=actor,
            scope=scope,
            previous_state_hash=previous_state_hash,
            new_state_hash=new_state_hash,
            reason=reason,
            evidence=evidence,
            model_version=model_version,
            parent_event_hash=parent_event_hash,
            timestamp=timestamp or time.time(),
        )
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryEvent":
        """Reconstruct an event from serialized data."""
        return cls(
            id=data["id"],
            event_type=EventType(data["event_type"]),
            actor=data["actor"],
            scope=data["scope"],
            previous_state_hash=data.get("previous_state_hash"),
            new_state_hash=data["new_state_hash"],
            reason=data["reason"],
            evidence=data.get("evidence"),
            model_version=data.get("model_version"),
            parent_event_hash=data.get("parent_event_hash"),
            timestamp=data["timestamp"],
        )
    
    def verify_chain(self, previous_event: Optional["MemoryEvent"] = None) -> bool:
        """
        Verify this event is properly chained.
        
        Checks:
        1. Parent event hash matches (if provided)
        2. Event hash matches computed hash
        """
        # Recompute hash
        payload = {
            "id": self.id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "scope": self.scope,
            "previous_state_hash": self.previous_state_hash,
            "new_state_hash": self.new_state_hash,
            "reason": self.reason,
            "evidence": self.evidence,
            "model_version": self.model_version,
            "parent_event_hash": self.parent_event_hash,
            "timestamp": self.timestamp,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        if expected_hash != self.event_hash:
            return False
        
        # Check parent chain
        if previous_event is not None and self.parent_event_hash:
            if self.parent_event_hash != previous_event.event_hash:
                return False
        
        return True