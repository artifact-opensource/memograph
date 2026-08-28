"""
Test suite for Memograph core primitives.
"""

import pytest
import time

from memograph.core.shard import MemoryShard, ShardDomain, ContentType
from memograph.core.events import MemoryEvent, EventType
from memograph.core.router import ContextRouter, ContextQuery
from memograph.core.memograph import MemoGraph, ContextEnvelope


class TestMemoryShard:
    """Tests for MemoryShard functionality."""
    
    def test_create_shard(self):
        """Test basic shard creation."""
        shard = MemoryShard.create(
            content={"intent": "deploy to production"},
            owner="agent-001",
            scope="project:test",
            domain=ShardDomain.LIVE
        )
        
        assert shard.content == {"intent": "deploy to production"}
        assert shard.owner == "agent-001"
        assert shard.scope == "project:test"
        assert shard.domain == ShardDomain.LIVE
        assert shard.shard_hash is not None
        assert len(shard.shard_hash) == 64  # SHA256 hex digest
    
    def test_hash_changes_on_content_change(self):
        """Hash must change when content changes."""
        shard1 = MemoryShard.create(
            content={"decision": "use postgresql"},
            owner="user-1", scope="proj:a", domain=ShardDomain.LIVE
        )
        shard2 = MemoryShard.create(
            content={"decision": "use sqlite"},  # Different content
            owner="user-1", scope="proj:a", domain=ShardDomain.LIVE
        )
        
        assert shard1.shard_hash != shard2.shard_hash
    
    def test_hash_changes_on_metadata_change(self):
        """Hash must change when any metadata changes."""
        shard1 = MemoryShard.create(
            content={"x": 1}, owner="a", scope="p", domain=ShardDomain.LIVE
        )
        shard2 = MemoryShard.create(
            content={"x": 1}, owner="b", scope="p", domain=ShardDomain.LIVE  # Different owner
        )
        
        assert shard1.shard_hash != shard2.shard_hash
    
    def test_with_version(self):
        """Test version increment."""
        shard = MemoryShard.create(
            content={"a": 1}, owner="o", scope="s", domain=ShardDomain.LIVE
        )
        new_shard = shard.with_version(2)
        
        assert new_shard.version == 2
        assert new_shard.parent_hash == shard.shard_hash
        assert new_shard.shard_hash != shard.shard_hash
    
    def test_with_content(self):
        """Test content update creates new hash."""
        shard = MemoryShard.create(
            content={"x": 1}, owner="o", scope="s", domain=ShardDomain.LIVE
        )
        updated = shard.with_content({"x": 2})
        
        assert updated.content == {"x": 2}
        assert updated.shard_hash != shard.shard_hash
        assert updated.parent_hash == shard.shard_hash
    
    def test_to_dict(self):
        """Test serialization."""
        shard = MemoryShard.create(
            content={"test": True},
            owner="agent-1",
            scope="project:alpha",
            domain=ShardDomain.PROJECT,
            content_type=ContentType.DECISION
        )
        data = shard.to_dict()
        
        assert data["owner"] == "agent-1"
        assert data["domain"] == "project"
        assert data["content_type"] == "DECISION"


class TestContextRouter:
    """Tests for context routing."""
    
    def test_route_fetches_candidates(self):
        """Router should route query to candidate shards."""
        router = ContextRouter()
        graph = MemoGraph()
        
        shard1 = MemoryShard.create(
            content={"context": "production deployment"},
            owner="agent-1", scope="proj:a", domain=ShardDomain.LIVE
        )
        shard2 = MemoryShard.create(
            content={"context": "testing deployment"},
            owner="agent-1", scope="proj:b", domain=ShardDomain.LIVE
        )
        
        graph.add_shard(shard1)
        graph.add_shard(shard2)
        
        query = ContextQuery(text="deployment")
        candidates = router.route([shard1, shard2], query)
        
        # Both shards should be candidates
        assert len(candidates) == 2


class TestMemoGraph:
    """Tests for MemoGraph topology."""
    
    def test_add_shard(self):
        """Graph should store shards by hash."""
        graph = MemoGraph()
        shard = MemoryShard.create(
            content={"test": True}, owner="o", scope="s"
        )
        
        hash_result = graph.add_shard(shard)
        assert hash_result == shard.shard_hash
        assert graph.get_shard(shard.shard_hash) == shard
    
    def test_lineage_tracing(self):
        """Should trace parent chain."""
        graph = MemoGraph()
        
        shard1 = MemoryShard.create(
            content={"level": 1}, owner="o", scope="s"
        )
        shard2 = shard1.with_version(2)
        
        graph.add_shard(shard1)
        graph.add_shard(shard2)
        
        lineage = graph.get_lineage(shard2.shard_hash)
        assert len(lineage) == 2
        assert lineage[0].shard_hash == shard2.shard_hash
        assert lineage[1].shard_hash == shard1.shard_hash
    
    def test_assemble_context_token_budget(self):
        """Context should respect token budget."""
        graph = MemoGraph()
        
        shard1 = MemoryShard.create(
            content={"decision": "use postgresql"}, owner="o", scope="s"
        )
        shard2 = MemoryShard.create(
            content={"reasoning": "high throughput", "more": "data"}, owner="o", scope="s"
        )
        
        graph.add_shard(shard1)
        graph.add_shard(shard2)
        
        candidates = [(shard1, 1.0), (shard2, 0.9)]
        envelope = graph.assemble_context(candidates, max_tokens=50)
        
        # Should produce a valid envelope
        assert isinstance(envelope, ContextEnvelope)


class TestMemoryEvent:
    """Tests for audit event system."""
    
    def test_event_creation(self):
        """Event should record transition."""
        shard = MemoryShard.create(
            content={"x": 1}, owner="o", scope="s"
        )
        
        event = MemoryEvent.create(
            event_id=1,
            event_type=EventType.CREATED,
            actor="user-1",
            scope="project:test",
            previous_state_hash=None,
            new_state_hash=shard.shard_hash,
            reason="Initial creation"
        )
        
        assert event.id == 1
        assert event.event_type == EventType.CREATED
        assert event.new_state_hash == shard.shard_hash
        assert event.event_hash is not None
    
    def test_event_hash_verification(self):
        """Event hash should be verifiable."""
        event = MemoryEvent.create(
            event_id=1, event_type=EventType.CREATED,
            actor="test", scope="s", new_state_hash="abc",
            reason="test"
        )
        
        assert event.verify_chain() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])