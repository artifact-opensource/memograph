"""
Context Router: Multi-dimensional context scoring and memory assembly.

Routes queries to the most relevant memory shards across domains.
Uses a weighted scoring system across:
- Semantic similarity (embedding-based)
- Recency (exponential decay)
- Authority (domain-level trust)
- Affinity (project/organization proximity)
- Temporal validity (freshness)
- Provenance (audit trail strength)
- Access policy (permission alignment)

The router's job is NOT to decide what to retrieve, but to rank
which shards are most relevant for a given query.

After ranking, the context assembler selects a token-capped subset
that fits within the LLM context window while preserving the minimal
sufficient context for the answer.
"""

import math
import time
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Set

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.events import MemoryEvent, EventType
from memograph.core.types import ContentType, AccessLevel


@dataclass
class ContextQuery:
    """A user query that drives context assembly."""
    text: str
    project_id: Optional[str] = None
    entity_ids: List[str] = field(default_factory=list)
    scope: str = ""  # "live", "project", "enterprise"
    min_tokens: int = 50
    max_tokens: int = 4096
    
    def __hash__(self):
        return hash((self.text, tuple(self.project_id), tuple(self.entity_ids), self.scope))
    
    def __eq__(self, other):
        if not isinstance(other, ContextQuery):
            return False
        return (self.text == other.text and
                self.project_id == other.project_id and
                set(self.entity_ids) == set(other.entity_ids) and
                self.scope == other.scope)


class ContextRouter:
    """
    Multi-dimensional context router.
    
    Responsibilities:
    1. Score all shards against a query using composite scoring
    2. Rank shards by score
    3. Assemble a token-capped context subset
    4. Handle permission filtering
    
    The router is intentionally lightweight — it delegates heavy lifting
    to the retrieval adapters (semantic, graph, temporal, etc.).
    """
    
    # Default weights for scoring (can be tuned per deployment)
    WEIGHTS = {
        "semantic": 0.40,
        "recency": 0.25,
        "authority": 0.20,
        "affinity": 0.15,
    }
    
    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or self.WEIGHTS
        self._pipeline = None  # Will be set by LifecyclePipeline
    
    def score_shard(self, shard: MemoryShard, query: ContextQuery) -> float:
        """
        Compute a contextual score for a shard given a query.
        
        Score components:
        - Semantic similarity (requires embedding adapter)
        - Recency (exponential decay based on age)
        - Authority (domain-level trust)
        - Affinity (project/organization proximity)
        - Temporal validity (freshness)
        - Provenance (audit trail completeness)
        - Access policy alignment
        
        Returns a normalized score 0-1.
        """
        # Placeholder for actual scoring logic — integrates with adapters
        # In a real implementation, this would call:
        #   - SemanticAdapter: cosine similarity between query and shard content
        #   - TemporalAdapter: recency penalty based on age
        #   - AuthorityEngine: domain trust multiplier
        #   - AffinityEngine: project/organization overlap
        #   - ProvenanceEngine: event chain completeness
        #   - PolicyEngine: permission alignment
        
        # For now, return a synthetic score based on domain and affinity
        domain_weight = self.weights.get("authority", 0.2)
        affinity = 1.0 if query.scope else 0.3
        return affinity * 0.5 + domain_weight * 0.5
    
    def route(self, shards: List[MemoryShard], query: ContextQuery,
              allowed_scopes: Optional[Set[str]] = None,
              allowed_orgs: Optional[Set[str]] = None) -> List[Tuple[MemoryShard, float]]:
        """
        Given a list of shards and a query, return ranked (shard, score) pairs.
        
        Args:
            shards: Candidate memory shards (already filtered by scope/permissions)
            query: The user query driving the context assembly
            
        Returns:
            List of (MemoryShard, score) tuples sorted by score descending
        """
        # 1. Blast-radius filter FIRST
        candidates = self.scope_filter(shards,
                                       allowed_scopes=allowed_scopes,
                                       allowed_orgs=allowed_orgs)
        allowed = [s for s in candidates if self._is_allowed(s, query)]
        scored = [(s, self.score_shard(s, query)) for s in allowed]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def scope_filter(self, shards, allowed_scopes=None, allowed_orgs=None):
        result = []
        for s in shards:
            if allowed_orgs:
                ok = any(
                    s.scope.startswith(f"org:{org}") or f"org:{org}" in s.scope
                    for org in allowed_orgs
                )
                if not ok:
                    continue
            if allowed_scopes and s.scope not in allowed_scopes:
                if not any(s.scope.startswith(sc) or sc in s.scope for sc in allowed_scopes):
                    continue
            result.append(s)
        return result
    
    def _is_allowed(self, shard: MemoryShard, query: ContextQuery) -> bool:
        """Check if a shard is permitted for this query."""
        # Basic permission check
        if not shard.permissions:
            return False
        
        # Query scope filter
        if query.scope and shard.scope != query.scope:
            return False
        
        # Project affinity (optional)
        if query.project_id and shard.scope != query.project_id:
            return False
        
        # Authorization check (could involve policy engine)
        return True
    
    def assemble_context(self, candidates: List[MemoryShard], 
                         query: ContextQuery,
                         max_tokens: int = 4096) -> List[MemoryShard]:
        """
        Select a token-capped subset of shards for context assembly.
        
        Strategy:
        1. Sort candidates by score (highest first)
        2. Greedily accumulate until reaching max_tokens
        3. Stop when adding another shard would exceed token budget
        
        This ensures the most relevant shards are prioritized while
        respecting the LLM context window constraint.
        """
        # Filter by permissions first
        allowed = [s for s in candidates if self._is_allowed(s, query)]
        
        # Sort by score
        scored = [(s, self.score_shard(s, query)) for s in allowed]
        scored.sort(key=lambda x: x[1], reverse=True)
        
        selected = []
        accumulated_tokens = 0
        
        for shard, score in scored:
            # Estimate token cost (rough heuristic)
            token_cost = len(str(shard.content)) // 4  # conservative
            if accumulated_tokens + token_cost <= max_tokens:
                selected.append(shard)
                accumulated_tokens += token_cost
                if accumulated_tokens >= max_tokens:
                    break
        
        return selected


# Convenience factory
router = ContextRouter()
