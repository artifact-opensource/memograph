"""
Memory Eviction: TTL-based forgetting for ephemeral live memory.

The "forgetting" requirement is critical — live memory should not
accumulate indefinitely. Shards can have TTLs that trigger eviction.

Eviction strategies:
1. Time-based (TTL expires)
2. Usage-based (LRU)
3. Size-based (pressure)
4. Explicit cleanup

Evicted memories become history only — they can be recovered via
event log if needed, but are no longer available for context assembly.
"""

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.events import MemoryEvent, EventType


@dataclass
class EvictionResult:
    """Result of an eviction operation."""
    evicted_shards: List[str]  # Shard hashes
    evicted_tokens: int
    reason: str
    timestamp: float = field(default_factory=time.time)
    recovery_info: Optional[Dict[str, Any]] = None  # For debugging/audit


class EvictionStrategy(Enum):
    """Strategies for choosing which shards to evict."""
    TTL = "ttl"          # Evict based on time-to-live
    LRU = "lru"          # Evict least-recently-used
    SIZE = "size"        # Evict oldest to meet size target
    BATCH = "batch"      # Evict oldest N items


class MemoryEvictor:
    """
    Handles eviction of expired or excess memory shards.
    
    Key feature: Eviction is not deletion. Evicted shards remain in
    the event log and can be reconstructed if necessary.
    
    The evictor maintains:
    - TTL per shard
    - Last access timestamps
    - Eviction queue (sorted by eviction priority)
    """
    
    def __init__(self, default_ttl_seconds: int = 3600):  # 1 hour default
        self.default_ttl = default_ttl_seconds
        self.ttls: Dict[str, float] = {}  # shard_hash -> eviction_time
        self.last_access: Dict[str, float] = {}  # shard_hash -> timestamp
        self.evicted: Set[str] = set()  # Already-evicted shards
        self.strategy = EvictionStrategy.TTL
    
    def set_ttl(self, shard: MemoryShard, ttl_seconds: int):
        """Set a time-to-live for a shard."""
        eviction_time = time.time() + ttl_seconds
        self.ttls[shard.shard_hash] = eviction_time
        if shard.shard_hash not in self.last_access:
            self.last_access[shard.shard_hash] = time.time()
    
    def touch(self, shard: MemoryShard) -> None:
        """Update last access time for a shard."""
        self.last_access[shard.shard_hash] = time.time()
        # Reset TTL on access
        if shard.shard_hash in self.ttls:
            self.ttls[shard.shard_hash] = time.time() + self.default_ttl
    
    def get_lifetime(self, shard: MemoryShard) -> Optional[timedelta]:
        """Get the remaining lifetime of a shard."""
        if shard.shard_hash not in self.ttls:
            return None
        remaining = self.ttls[shard.shard_hash] - time.time()
        return timedelta(seconds=max(0, remaining))
    
    def ready_eviction(self, shard: MemoryShard) -> bool:
        """Check if a shard is ready to be evicted."""
        if shard.shard_hash in self.evicted:
            return False
        if shard.shard_hash not in self.ttls:
            return shard.domain != ShardDomain.LIVE  # Non-live shards keep TTLs
        return time.time() >= self.ttls[shard.shard_hash]
    
    def evict_ready(self, shards: List[MemoryShard]) -> EvictionResult:
        """Evict all shards that are ready to be evicted."""
        to_evict = []
        for shard in shards:
            if self.ready_eviction(shard):
                to_evict.append(shard)
        
        return self._do_eviction(to_evict, reason="TTL expired")
    
    def _do_eviction(self, shards: List[MemoryShard], reason: str = "eviction") -> EvictionResult:
        """Perform actual eviction."""
        evicted_hashes = []
        evicted_tokens = 0
        
        for shard in shards:
            evicted_hashes.append(shard.shard_hash)
            evicted_tokens += len(str(shard.content)) // 4
            self.evicted.add(shard.shard_hash)
        
        return EvictionResult(
            evicted_shards=evicted_hashes,
            evicted_tokens=evicted_tokens,
            reason=reason
        )
    
    def evict_by_size(self, shards: List[MemoryShard], 
                      max_tokens: int, strategy: EvictionStrategy = EvictionStrategy.TTL) -> EvictionResult:
        """Evict shards to meet a token budget."""
        # Sort by eviction priority
        if strategy == EvictionStrategy.TTL:
            candidate_shards = [s for s in shards if s.domain == ShardDomain.LIVE]
            candidate_shards.sort(key=lambda s: self.ttls.get(s.shard_hash, float('inf')))
        elif strategy == EvictionStrategy.LRU:
            candidate_shards = [s for s in shards if s.domain == ShardDomain.LIVE]
            candidate_shards.sort(key=lambda s: self.last_access.get(s.shard_hash, float('inf')))
        else:
            candidate_shards = shards
        
        # Evict until we're under budget
        to_evict = []
        total_tokens = sum(len(str(s.content)) // 4 for s in shards)
        
        for shard in candidate_shards:
            if total_tokens <= max_tokens:
                break
            to_evict.append(shard)
            total_tokens -= len(str(shard.content)) // 4
        
        return self._do_eviction(to_evict, reason=f"size pressure: {strategy.value}")
    
    def get_eviction_candidates(self, shards: List[MemoryShard], 
                                max_count: int = 100) -> List[MemoryShard]:
        """Get shards that are candidates for eviction."""
        candidates = []
        for shard in shards:
            if shard.shard_hash in self.evicted:
                continue
            if self.ready_eviction(shard):
                candidates.append(shard)
        
        # Sort by age
        candidates.sort(key=lambda s: s.timestamp)
        return candidates[:max_count]
    
    def is_evicted(self, shard_hash: str) -> bool:
        """Check if a shard has been evicted."""
        return shard_hash in self.evicted
    
    def clear(self) -> int:
        """Clear all eviction tracking (useful for testing)."""
        count = len(self.evicted)
        self.evicted.clear()
        return count
from typing import Dict, Any