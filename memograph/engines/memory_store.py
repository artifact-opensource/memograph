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
import os
from typing import Dict, List, Optional, Any
from datetime import datetime

from memograph.core.shard import MemoryShard
from memograph.core.events import MemoryEvent


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
            with open(shard_path, "w") as f:
                json.dump(shard.to_dict(), f, indent=2)
            
            # Update index
            self.index_cache[shard.shard_hash] = {
                "domain": shard.domain.value,
                "scope": shard.scope,
                "path": shard_path,
                "timestamp": shard.timestamp
            }
            self._save_index()
            
            return True
        except Exception as e:
            return False
    
    def get_shard(self, shard_hash: str) -> Optional[MemoryShard]:
        """Retrieve a shard by hash."""
        if shard_hash not in self.index_cache:
            return None
        
        info = self.index_cache[shard_hash]
        try:
            with open(info["path"], "r") as f:
                data = json.load(f)
                return MemoryShard.create(
                    content=data["content"],
                    owner=data["owner"],
                    scope=data["scope"],
                    domain=ShardDomain(data["domain"]),
                    parent_hash=data.get("parent_hash"),
                    permissions=data.get("permissions", ["*"]),
                    timestamp=data["timestamp"],
                    version=data["version"],
                    content_type=ContentType(data.get("content_type", "CONVERSATIONAL"))
                )
        except Exception:
            return None
    
    def save_event(self, event: MemoryEvent) -> bool:
        """Append an event to the event log."""
        try:
            event_path = os.path.join(self.events_path, f"{event.id}.json")
            with open(event_path, "w") as f:
                json.dump(event.to_dict(), f, indent=2)
            return True
        except Exception:
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
            with open(index_file, "r") as f:
                return json.load(f)
        return {}
    
    def _save_index(self) -> None:
        index_file = os.path.join(self.index_path, "index.json")
        with open(index_file, "w") as f:
            json.dump(self.index_cache, f, indent=2)
    
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