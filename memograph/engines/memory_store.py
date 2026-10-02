"""
Memory Store: Persistence layer for memory shards.

Provides:
- Storage and retrieval of MemoryShard objects
- Index management (hash, domain, scope, content type)
- Transactional writes (atomic updates)
- Backup and restore capability
- Storage statistics

This is the persistence layer - separate from retrieval logic.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.types import ContentType
from memograph.core.events import MemoryEvent

logger = logging.getLogger(__name__)


class MemoryStore:
    """
    Persistent storage for memory shards.
    
    Stores shards as JSON files organized by domain/scope.
    Provides fast lookup by hash via index files.
    
    Design: Simple file-based persistence with index caching.
    In production, this could be backed by PostgreSQL, Redis, etc.
    """
    
    def __init__(self, root_path: str = "/tmp/memograph_storage"):
        self.root_path = root_path
        self.index_path = os.path.join(root_path, ".index")
        self.events_path = os.path.join(root_path, ".events")
        
        # Ensure directories exist
        os.makedirs(self.root_path, exist_ok=True)
        os.makedirs(self.index_path, exist_ok=True)
        os.makedirs(self.events_path, exist_ok=True)
        
        # Load index cache
        self.index_cache = self._load_index()
    
    def save_shard(self, shard: MemoryShard) -> bool:
        """Save a shard to persistent storage."""
        try:
            domain_dir = os.path.join(self.root_path, shard.domain.value)
            scope_dir = os.path.join(domain_dir, shard.scope.replace(":", "_"))
            os.makedirs(scope_dir, exist_ok=True)
            
            # Write shard file
            shard_path = os.path.join(scope_dir, f"{shard.shard_hash}.json")
            tmp_path = shard_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(shard.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, shard_path)
            
            # Update index
            self.index_cache[shard.shard_hash] = {
                "domain": shard.domain.value,
                "scope": shard.scope,
                "path": shard_path,
                "timestamp": shard.timestamp
            }
            self._save_index()
            
            return True
        except Exception:
            logger.exception("Failed to save memory shard %s", shard.shard_hash)
            return False
    
    def get_shard(self, shard_hash: str) -> Optional[MemoryShard]:
        """Retrieve a shard by hash."""
        if shard_hash not in self.index_cache:
            return None
        
        info = self.index_cache[shard_hash]
        try:
            with open(info["path"], "r") as f:
                data = json.load(f)
                shard = MemoryShard.from_dict(data)
                if shard.shard_hash != shard_hash:
                    raise ValueError(f"Shard index hash mismatch: expected {shard_hash}")
                return shard
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            logger.exception("Failed to load memory shard %s", shard_hash)
            return None
    
    def save_event(self, event: MemoryEvent) -> bool:
        """Append an event to the event log."""
        try:
            event_path = os.path.join(self.events_path, f"{event.id}.json")
            tmp_path = event_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(event.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, event_path)
            return True
        except Exception:
            logger.exception("Failed to save memory event %s", event.id)
            return False
    
    def list_shards(self, domain: Optional[str] = None, 
                    scope: Optional[str] = None) -> List[str]:
        """List shard hashes with optional filters."""
        results = []
        for shard_hash, info in self.index_cache.items():
            if domain and info["domain"] != domain:
                continue
            if scope and info["scope"] != scope:
                continue
            results.append(shard_hash)
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Return storage statistics."""
        total = len(self.index_cache)
        by_domain = {}
        for info in self.index_cache.values():
            d = info["domain"]
            by_domain[d] = by_domain.get(d, 0) + 1
        return {
            "total_shards": total,
            "by_domain": by_domain,
            "storage_path": self.root_path,
            "events_count": len(os.listdir(self.events_path)) if os.path.exists(self.events_path) else 0
        }
    
    def _load_index(self) -> Dict[str, Any]:
        index_file = os.path.join(self.index_path, "index.json")
        if os.path.exists(index_file):
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    index = json.load(f)
                if not isinstance(index, dict):
                    raise ValueError("index root must be an object")
                return index
            except (OSError, json.JSONDecodeError, ValueError):
                logger.exception("Memory index is unreadable; starting with an empty index cache: %s", index_file)
        return {}
    
    def _save_index(self) -> None:
        index_file = os.path.join(self.index_path, "index.json")
        tmp_path = index_file + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.index_cache, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, index_file)
    
    def clear(self) -> int:
        """Clear all stored data."""
        count = len(self.index_cache)
        self.index_cache.clear()
        for root, dirs, files in os.walk(self.root_path):
            for f in files:
                if f.endswith(".json") and f != "index.json":
                    os.remove(os.path.join(root, f))
        self._save_index()
        return count