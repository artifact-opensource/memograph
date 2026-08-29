"""
Memograph Agent Tool Integration.

Provides Memograph as a callable tool for AI agents, enabling:
- Seamless memory injection into agent context
- Native tool interface (Hermes MCP / tool protocol compatible)
- Session-persistent memory scope
- Tool-callable CRUD operations

Usage as a Hermes tool:
    from memograph.tools import memograph_tool, MemographAgentSession

    # In agent setup:
    tool = memograph_tool(session_id="agent-001")
    # Register with agent's tool registry
    # Now agent can call: memograph_tool(query="...", action="retrieve")

    # In agent reasoning loop:
    result = memograph_tool(query="project architecture", action="retrieve")
    # result.injects into agent context automatically
"""

import time
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List, Callable
from enum import Enum

from memograph.core.shard import MemoryShard, ShardDomain
from memograph.core.events import MemoryEvent, EventType
from memograph.core.memograph import MemoGraph, ContextEnvelope
from memograph.core.router import ContextRouter, ContextQuery
from memograph.lifecycle.pipeline import LifecyclePipeline


# ---------------------------------------------------------------------------
# Tool Protocol Types
# ---------------------------------------------------------------------------

class ToolAction(str, Enum):
    """Supported tool actions."""
    RETRIEVE = "retrieve"       # Query memory, get context for reasoning
    STORE = "store"            # Store a new memory shard
    PROMOTE = "promote"        # Promote shard to higher domain
    EVICT = "evict"            # Mark shard for eviction/forgetting
    AUDIT = "audit"            # Get audit trail for a shard
    STATUS = "status"          # Get memory system status
    QUERY_TRAITS = "query_traits"  # Query agent/persona traits from memory


@dataclass
class ToolRequest:
    """A request to the Memograph tool."""
    action: ToolAction
    query: str = ""
    shard_hash: str = ""
    content: Optional[Dict[str, Any]] = None
    domain: str = "live"
    scope: str = ""
    owner: str = ""
    max_tokens: int = 4096
    max_results: int = 10
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolRequest":
        action = ToolAction(d.get("action", "retrieve"))
        return cls(
            action=action,
            query=d.get("query", ""),
            shard_hash=d.get("shard_hash", ""),
            content=d.get("content"),
            domain=d.get("domain", "live"),
            scope=d.get("scope", ""),
            owner=d.get("owner", ""),
            max_tokens=int(d.get("max_tokens", 4096)),
            max_results=int(d.get("max_results", 10)),
            session_id=d.get("session_id", ""),
            metadata=d.get("metadata", {}),
        )


@dataclass
class ToolResponse:
    """A response from the Memograph tool, ready for context injection."""
    success: bool
    action: str
    message: str = ""
    context: Optional[Dict[str, Any]] = None   # Inject this into agent context
    shard_hash: str = ""
    shard_count: int = 0
    domains: List[str] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    injected_tokens: int = 0
    error: str = ""

    def to_context_string(self) -> str:
        """
        Serialize the response as a context string for agent injection.
        This is what gets injected into the agent's context window.
        """
        if not self.success or not self.context:
            return ""

        lines = [f"\n{'='*60}", "[MEMOGRAPH CONTEXT]", f"{'='*60}\n"]

        if self.action == "retrieve":
            lines.append(f"Query: {self.context.get('query', '')}")
            lines.append(f"Domains: {', '.join(self.domains)}")
            lines.append(f"Shards returned: {self.shard_count}\n")

            by_domain = self.context.get("by_domain", {})
            for domain, shards in by_domain.items():
                lines.append(f"\n--- {domain.upper()} MEMORY ---")
                for shard in shards:
                    lines.append(f"  [{shard.get('shard_hash','')[:8]}]")
                    content = shard.get("content", {})
                    if isinstance(content, dict):
                        for k, v in content.items():
                            lines.append(f"    {k}: {v}")
                    else:
                        lines.append(f"    {content}")
                lines.append("")

        elif self.action == "status":
            lines.append(f"Session: {self.context.get('session_id', '')}")
            lines.append(f"Total shards: {self.context.get('total_shards', 0)}")
            lines.append(f"By domain: {self.context.get('by_domain', {})}")
            lines.append(f"Events logged: {self.context.get('event_count', 0)}")

        elif self.action == "store":
            lines.append(f"Stored shard: {self.shard_hash[:16]}")
            lines.append(f"Domain: {self.context.get('domain', '')}")

        elif self.action == "audit":
            for event in self.audit_trail:
                lines.append(f"\nEvent: {event.get('event_type','')}")
                for k, v in event.items():
                    lines.append(f"  {k}: {v}")

        lines.append(f"\n{'='*60}\n")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Include context string for easy injection
        d["context_string"] = self.to_context_string()
        return d


# ---------------------------------------------------------------------------
# Per-Session Memory Graph
# ---------------------------------------------------------------------------

class MemographAgentSession:
    """
    A Memograph session bound to an agent identity.

    Each agent gets its own MemoGraph instance with:
    - Persistent storage across agent runs
    - Automatic LIVE shard management
    - Scope limited to the agent's authorized domains
    """

    def __init__(self, session_id: str, storage_dir: str = ".memograph_storage",
                 default_owner: str = ""):
        self.session_id = session_id
        self.storage_dir = storage_dir
        self.default_owner = default_owner or session_id
        self.graph = MemoGraph()
        self.router = ContextRouter()
        self.lifecycle = LifecyclePipeline()
        self._event_log: List[MemoryEvent] = []
        self._load_or_init()

    def _load_or_init(self):
        """Load existing session or initialize fresh."""
        import os
        session_file = os.path.join(self.storage_dir, f"{self.session_id}.json")
        if os.path.exists(session_file):
            # Restore session
            self.graph = MemoGraph.load(session_file)
            # Reconstruct events from shards
            for shard in self.graph.nodes.values():
                if shard.content.get("_is_event"):
                    self._event_log.append(MemoryEvent(
                        event_id=shard.content.get("event_id", 0),
                        event_type=EventType(shard.content.get("event_type", "created")),
                        actor=shard.owner,
                        scope=shard.scope,
                        parent_hash=shard.parent_hash or "",
                        previous_state_hash=shard.content.get("prev_hash", ""),
                        new_state_hash=shard.shard_hash,
                        reason=shard.content.get("reason", ""),
                        evidence=shard.content.get("evidence", {}),
                        model_version=shard.content.get("model_version", "")
                    ))
        # Ensure storage dir exists
        os.makedirs(self.storage_dir, exist_ok=True)

    def save(self):
        """Persist session to disk."""
        session_file = f"{self.storage_dir}/{self.session_id}.json"
        self.graph.save(session_file)

    def execute(self, request: ToolRequest) -> ToolResponse:
        """Execute a tool request and return an injection-ready response."""
        domain_map = {
            "live": ShardDomain.LIVE,
            "project": ShardDomain.PROJECT,
            "enterprise": ShardDomain.ENTERPRISE,
        }
        shard_domain = domain_map.get(request.domain, ShardDomain.LIVE)

        try:
            if request.action == ToolAction.RETRIEVE:
                return self._do_retrieve(request, shard_domain)
            elif request.action == ToolAction.STORE:
                return self._do_store(request, shard_domain)
            elif request.action == ToolAction.PROMOTE:
                return self._do_promote(request)
            elif request.action == ToolAction.EVICT:
                return self._do_evict(request)
            elif request.action == ToolAction.AUDIT:
                return self._do_audit(request)
            elif request.action == ToolAction.STATUS:
                return self._do_status(request)
            elif request.action == ToolAction.QUERY_TRAITS:
                return self._do_query_traits(request)
            else:
                return ToolResponse(
                    success=False,
                    action=request.action.value,
                    error=f"Unknown action: {request.action}"
                )
        except Exception as e:
            return ToolResponse(
                success=False,
                action=request.action.value,
                error=str(e)
            )

    def _do_retrieve(self, req: ToolRequest, domain: ShardDomain) -> ToolResponse:
        # Only constrain by scope if the caller explicitly provided one.
        # Do NOT fall back to the domain name — that would filter out every
        # shard whose scope is a project id (e.g. "payments") rather than the
        # literal domain string ("project").
        query = ContextQuery(
            text=req.query,
            scope=req.scope,
            max_tokens=req.max_tokens
        )
        candidates = self.graph.query_by_domain(domain)
        result = self.router.retrieve(query, candidates=candidates,
                                     max_results=req.max_results)
        scored = [(s, sc) for s, sc in zip(result.shards, result.scores)]
        selected = self.graph.assemble_context(
            [(s, score) for s, score in scored],
            max_tokens=req.max_tokens
        )

        # Build context preserving stream boundaries
        by_domain: Dict[str, List[Dict]] = {domain.value: []}
        for shard in selected.shards:
            d = shard.to_dict()
            d["content"] = shard.content
            by_domain[domain.value].append(d)

        context_str = json.dumps({"by_domain": by_domain, "query": req.query})
        # Rough token estimate
        injected_tokens = len(context_str) // 4

        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Retrieved {len(selected)} shards",
            context={"by_domain": by_domain, "query": req.query},
            shard_count=len(selected),
            domains=[domain.value],
            injected_tokens=injected_tokens,
        )

    def _do_store(self, req: ToolRequest, domain: ShardDomain) -> ToolResponse:
        shard = MemoryShard.create(
            content=req.content or {"text": req.query},
            owner=req.owner or self.default_owner,
            scope=req.scope or self.session_id,
            domain=domain
        )
        self.graph.add_shard(shard)

        # Log as event
        event = MemoryEvent.create(
            event_id=int(time.time() * 1000000),
            event_type=EventType.CREATED,
            actor=self.default_owner,
            scope=req.scope or self.session_id,
            previous_state_hash="",
            new_state_hash=shard.shard_hash,
            reason=f"Agent stored: {req.query[:100]}",
        )
        self._event_log.append(event)

        self.save()
        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Stored shard {shard.shard_hash[:16]}",
            shard_hash=shard.shard_hash,
            context={"domain": domain.value, "shard_hash": shard.shard_hash}
        )

    def _do_promote(self, req: ToolRequest) -> ToolResponse:
        shard = self.graph.get_shard(req.shard_hash)
        if not shard:
            return ToolResponse(success=False, action=req.action.value,
                               error=f"Shard not found: {req.shard_hash}")

        target_map = {"live": ShardDomain.LIVE, "project": ShardDomain.PROJECT,
                      "enterprise": ShardDomain.ENTERPRISE}
        target = target_map.get(req.domain, ShardDomain.PROJECT)

        result = self.lifecycle.promote(
            shard=shard,
            target_domain=target,
            actor=self.default_owner,
            reason=req.metadata.get("reason", "Agent promotion request")
        )
        if result.success and result.target_shard:
            self.graph.add_shard(result.target_shard)
            self.save()

        return ToolResponse(
            success=result.success,
            action=req.action.value,
            message=result.notes or "",
            shard_hash=result.target_shard.shard_hash if result.target_shard else "",
            context={"promoted_to": target.value}
        )

    def _do_evict(self, req: ToolRequest) -> ToolResponse:
        self.graph.remove_shard(req.shard_hash)
        self.save()
        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Shard evicted: {req.shard_hash[:16]}",
        )

    def _do_audit(self, req: ToolRequest) -> ToolResponse:
        shard = self.graph.get_shard(req.shard_hash)
        if not shard:
            return ToolResponse(success=False, action=req.action.value,
                               error=f"Shard not found: {req.shard_hash}")

        # Build trail by walking parent chain
        trail = []
        current = shard
        while current:
            trail.append({
                "hash": current.shard_hash[:16],
                "version": current.version,
                "timestamp": current.timestamp,
                "content_preview": str(current.content)[:200],
            })
            if current.parent_hash:
                current = self.graph.get_shard(current.parent_hash)
            else:
                break

        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Audit trail: {len(trail)} versions",
            audit_trail=trail,
            context={"versions": len(trail)}
        )

    def _do_status(self, req: ToolRequest) -> ToolResponse:
        total = len(self.graph.nodes)
        by_domain: Dict[str, int] = {}
        for shard in self.graph.nodes.values():
            d = shard.domain.value
            by_domain[d] = by_domain.get(d, 0) + 1

        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Session {self.session_id} status",
            context={
                "session_id": self.session_id,
                "total_shards": total,
                "by_domain": by_domain,
                "event_count": len(self._event_log),
            },
            shard_count=total,
            domains=list(by_domain.keys()),
        )

    def _do_query_traits(self, req: ToolRequest) -> ToolResponse:
        """Query agent persona/traits stored in memory."""
        query = ContextQuery(text=f"persona traits preferences {req.query}", scope="traits")
        candidates = list(self.graph.nodes.values())
        scored = [(s, self.router.score_shard(s, query)) for s in candidates]
        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:5]

        traits = {k: v for shard, _ in top for k, v in shard.content.items()
                  if isinstance(shard.content, dict)}

        return ToolResponse(
            success=True,
            action=req.action.value,
            message=f"Retrieved {len(traits)} trait entries",
            context={"traits": traits},
            shard_count=len(top),
        )


# ---------------------------------------------------------------------------
# Callable Tool Interface (Hermes MCP compatible)
# ---------------------------------------------------------------------------

class MemographTool:
    """
    The Memograph tool — callable like any other agent tool.

    Provides a clean interface for agents to interact with memory
    without needing to understand the underlying architecture.

    Agent integration example:
        tool = MemographTool(session_id="agent-001")
        
        # Agent calls this as a tool:
        result = tool(
            action="retrieve",
            query="current project decisions about auth"
        )
        
        # The context string is ready for injection:
        injected = result.to_context_string()
    """

    def __init__(self, session_id: str = "default",
                 storage_dir: str = ".memograph_storage",
                 default_owner: str = ""):
        self.session = MemographAgentSession(
            session_id=session_id,
            storage_dir=storage_dir,
            default_owner=default_owner
        )

    def __call__(self, action: str = "retrieve",
                 query: str = "",
                 shard_hash: str = "",
                 content: Optional[Dict[str, Any]] = None,
                 domain: str = "live",
                 scope: str = "",
                 owner: str = "",
                 max_tokens: int = 4096,
                 max_results: int = 10,
                 metadata: Optional[Dict[str, Any]] = None,
                 **kwargs) -> ToolResponse:
        """
        Call the Memograph tool.

        Args:
            action: retrieve | store | promote | evict | audit | status | query_traits
            query: Natural language query for retrieve / query_traits
            shard_hash: Shard hash for promote / evict / audit
            content: Memory content for store action
            domain: live | project | enterprise
            scope: Memory scope / project identifier
            owner: Memory owner (defaults to session_id)
            max_tokens: Token budget for context assembly
            max_results: Max shards to return
            metadata: Additional action metadata

        Returns:
            ToolResponse with context_string ready for agent injection
        """
        request = ToolRequest(
            action=ToolAction(action),
            query=query,
            shard_hash=shard_hash,
            content=content,
            domain=domain,
            scope=scope,
            owner=owner,
            max_tokens=max_tokens,
            max_results=max_results,
            session_id=self.session.session_id,
            metadata=metadata or kwargs,
        )
        return self.session.execute(request)

    def inject_into_context(self, action: str = "retrieve",
                            query: str = "", **kwargs) -> str:
        """
        Retrieve and return context string for direct injection.

        This is the simplest integration path:
            context_str = memograph.inject_into_context(
                query="why did we choose this architecture"
            )
            # Now pass context_str to your LLM as part of the prompt
        """
        result = self(action=action, query=query, **kwargs)
        return result.to_context_string()

    def store_decision(self, decision: str, scope: str = "",
                       domain: str = "live", **kwargs) -> str:
        """Convenience: store a decision, return the shard hash."""
        result = self(
            action="store",
            query=decision,
            content={"decision": decision, "type": "agent_decision"},
            scope=scope or self.session.session_id,
            domain=domain,
            **kwargs
        )
        return result.shard_hash

    def retrieve_for_decision(self, question: str,
                              max_tokens: int = 2048) -> ToolResponse:
        """
        Retrieve memory relevant to making a decision.

        The returned response carries all the context the agent needs
        to answer the question with full provenance.
        """
        return self(
            action="retrieve",
            query=question,
            domain="all",
            max_tokens=max_tokens,
        )


# ---------------------------------------------------------------------------
# Singleton tool instances (per-agent-session)
# ---------------------------------------------------------------------------

_tool_instances: Dict[str, MemographTool] = {}


def memograph_tool(session_id: str = "agent",
                   storage_dir: str = ".memograph_storage",
                   default_owner: str = "") -> MemographTool:
    """
    Get or create a Memograph tool instance for a session.

    Usage in agent setup:
        tool = memograph_tool(session_id="agent-001")
        # Register tool with your agent's tool registry
    """
    if session_id not in _tool_instances:
        _tool_instances[session_id] = MemographTool(
            session_id=session_id,
            storage_dir=storage_dir,
            default_owner=default_owner or session_id,
        )
    return _tool_instances[session_id]


def reset_session(session_id: str = "agent"):
    """Reset a session (clears in-memory graph, preserves storage)."""
    if session_id in _tool_instances:
        del _tool_instances[session_id]


# ---------------------------------------------------------------------------
# Hermes MCP Tool Manifest
# ---------------------------------------------------------------------------

MEMOGRAPH_TOOL_MANIFEST = {
    "name": "memograph",
    "description": "Topological memory management. Store, retrieve, and reason over multi-domain memory with full provenance.",
    "actions": [
        {
            "name": "retrieve",
            "description": "Query memory across live/project/enterprise domains. Returns context ready for injection.",
            "parameters": {
                "query": {"type": "string", "description": "Natural language query"},
                "domain": {"type": "string", "enum": ["live", "project", "enterprise"], "description": "Memory domain to search"},
                "max_tokens": {"type": "integer", "description": "Token budget for context assembly"},
            }
        },
        {
            "name": "store",
            "description": "Store a new memory shard.",
            "parameters": {
                "query": {"type": "string", "description": "Human-readable summary"},
                "content": {"type": "object", "description": "Structured memory content"},
                "domain": {"type": "string", "enum": ["live", "project", "enterprise"]},
                "scope": {"type": "string", "description": "Project or context scope"},
            }
        },
        {
            "name": "promote",
            "description": "Promote a memory shard to a higher domain (live→project→enterprise).",
            "parameters": {
                "shard_hash": {"type": "string", "description": "Hash of shard to promote"},
                "domain": {"type": "string", "enum": ["project", "enterprise"], "description": "Target domain"},
            }
        },
        {
            "name": "audit",
            "description": "Get the full version lineage and provenance trail of a memory shard.",
            "parameters": {
                "shard_hash": {"type": "string", "description": "Hash of shard to audit"},
            }
        },
        {
            "name": "status",
            "description": "Get current session memory statistics.",
            "parameters": {}
        },
        {
            "name": "query_traits",
            "description": "Query agent persona and preference memory.",
            "parameters": {
                "query": {"type": "string", "description": "Traits to query"},
            }
        },
    ]
}
