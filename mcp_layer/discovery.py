"""
Generic MCP Capability Discovery & Tool Filtering Module (Phase 10).

Provides two-stage generic tool discovery:
  Stage 1: Server Selection (matches query against server names & descriptions)
  Stage 2: Tool Selection (matches query against tool descriptions, input schemas, risk policy)

Supports two experimental discovery variants:
  - Variant A: Metadata Similarity (TF-IDF / term overlap / metadata vector similarity, zero LLM latency)
  - Variant B: LLM-Assisted Structured Discovery (small Qwen3 call via with_structured_output)

Includes safety fallback (broadening set if confidence is low), confirmation preservation,
and observability trace events (DISCOVERY_START, DISCOVERY_RESULT).
"""

import json
import logging
import re
import time
from typing import Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---- Pydantic Schemas for Variant B (LLM Discovery) ----
class ServerSelectionDecision(BaseModel):
    selected_servers: List[str] = Field(
        description="List of relevant MCP server names (e.g. ['calendar', 'notes']) required for the query."
    )
    confidence: float = Field(
        default=1.0,
        description="Confidence score from 0.0 to 1.0 in this server selection."
    )


class ToolSelectionDecision(BaseModel):
    selected_tools: List[str] = Field(
        description="List of exact tool names (e.g. ['calendar.list_events', 'calculator']) needed to fulfill the query."
    )
    reasoning: str = Field(
        default="",
        description="Brief concise justification for tool selection."
    )


def _tokenize(text: str) -> set[str]:
    """Extract clean lowercased tokens from query or description."""
    return set(re.findall(r"\b[a-zA-Z0-9_\.]+\b", text.lower()))


def score_text_similarity(query_tokens: set[str], doc: str, doc_name: str = "") -> float:
    """Generic term overlap & similarity score between query tokens and metadata doc."""
    if not query_tokens or not doc:
        return 0.0
    doc_tokens = _tokenize(doc)
    name_tokens = _tokenize(doc_name)
    all_doc_tokens = doc_tokens.union(name_tokens)
    
    overlap = query_tokens.intersection(all_doc_tokens)
    if not overlap:
        # Require both q and d to be > 3 characters to avoid matching single-letter words like 'a'
        sub_matches = sum(
            1 for q in query_tokens if len(q) > 3 and any((q in d or d in q) for d in all_doc_tokens if len(d) > 3)
        )
        if sub_matches:
            return 0.2 * sub_matches
        return 0.0

    score = len(overlap) / (len(query_tokens) ** 0.5)
    if query_tokens.intersection(name_tokens):
        score *= 1.5
    return score


class CapabilityDiscoverer:
    """Generic capability discoverer operating over ToolRegistry metadata."""

    def __init__(self, registry=None):
        self._registry = registry

    def _get_registry(self):
        if self._registry is not None:
            return self._registry
        from mcp_layer.registry import registry
        return registry

    # ---- Variant A: Metadata Similarity Discovery ----
    def discover_metadata(
        self, query: str, threshold: float = 0.15, min_tools: int = 1
    ) -> tuple[list[str], list[str], float, bool]:
        """Stage 1 + Stage 2 Metadata Similarity filtering.
        Returns: (selected_servers, selected_tools, confidence, fallback_used)
        """
        reg = self._get_registry()
        reg.discover()
        
        q_lower = query.lower()
        q_tokens = _tokenize(query)
        tool_map = reg.tool_map()
        normalized_map = reg._normalized
        
        native_names = [name for name, tool in reg._native.items()]
        
        # Stage 1: Server Relevance
        server_scores = {}
        for srv_name, srv_cfg in reg._servers.items():
            srv_doc = f"{srv_name} " + " ".join(srv_cfg.tool_policy.keys()) if srv_cfg.tool_policy else srv_name
            srv_tools = [norm for norm in normalized_map.values() if norm.server == srv_name]
            srv_doc += " " + " ".join(f"{t.name} {t.description}" for t in srv_tools)
            server_scores[srv_name] = score_text_similarity(q_tokens, srv_doc, srv_name)

        selected_servers = [srv for srv, score in server_scores.items() if score >= threshold]
        
        # Stage 2: Tool Relevance
        tool_scores = {}
        for tool_name, tool_obj in tool_map.items():
            norm = reg.get_normalized(tool_name)
            doc = f"{tool_name} {getattr(tool_obj, 'description', '')}"
            if norm:
                doc += f" {norm.operation} {norm.risk_level}"
            score = score_text_similarity(q_tokens, doc, tool_name)
            tool_scores[tool_name] = score

        # Native tool word-boundary heuristics
        if "calculator" in native_names:
            calc_keywords = [r"%", r"\bcalculate\b", r"\bsum\b", r"\bmultiply\b", r"\bdivide\b", r"\bratio\b", r"\badd\b", r"\bsubtract\b", r"\bcount\b", r"\bamount\b", r"\bstipend\b", r"\btotal\b", r"\blines\b", r"\bhow many\b", r"\bhow much\b", r"\*", r"/", r"\+", r"-"]
            if any(re.search(pat, q_lower) for pat in calc_keywords) or re.search(r"\b\d+\s*[\+\-\*\/]\s*\d+\b", q_lower):
                tool_scores["calculator"] = max(tool_scores.get("calculator", 0.0), 0.5)

        if "web_search" in native_names:
            search_keywords = [r"\bpopulation\b", r"\bwho is\b", r"\blatest\b", r"\bnews\b", r"\bcurrent\b", r"\bweather\b", r"\bgdp\b", r"\bprice\b", r"\bstock\b", r"\bsearch\b"]
            if any(re.search(pat, q_lower) for pat in search_keywords):
                tool_scores["web_search"] = max(tool_scores.get("web_search", 0.0), 0.5)

        selected_tools = [t for t, score in tool_scores.items() if score >= threshold]
        
        # Preserve canonical/alias pairs
        all_selected = set(selected_tools)
        for t in list(all_selected):
            if "." in t:
                alias = t.replace(".", "_")
                if alias in tool_map:
                    all_selected.add(alias)
            elif "_" in t:
                canon = t.replace("_", ".", 1)
                if canon in tool_map:
                    all_selected.add(canon)
        selected_tools = sorted(list(all_selected))

        max_score = max(tool_scores.values()) if tool_scores else 0.0
        fallback = False

        # Controlled Fallback: If no MCP/native tools selected or confidence too low, fallback to full toolset
        if len(selected_tools) < min_tools or max_score < threshold:
            fallback = True
            selected_tools = reg.valid_names()
            selected_servers = list(reg._servers.keys())
            confidence = 0.2
        else:
            confidence = min(1.0, max_score)

        return selected_servers, selected_tools, confidence, fallback

    # ---- Variant B: LLM-Assisted Discovery ----
    def discover_llm(
        self, query: str, timeout_s: float = 10.0
    ) -> tuple[list[str], list[str], float, bool]:
        """Stage 1 + Stage 2 LLM-Assisted Discovery using Qwen3:8b."""
        from llm import llm
        from langchain_core.messages import SystemMessage, HumanMessage
        from observability.timeout import run_with_timeout

        reg = self._get_registry()
        reg.discover()

        server_names = list(reg._servers.keys())
        all_tools = reg.valid_names()

        sys_prompt = """You are a capability discovery assistant.
Given a user query and available MCP servers / tools, select ONLY the relevant servers and tools needed.
Do not select unnecessary tools."""

        user_prompt = f"""Available MCP Servers: {server_names}
Available Native & MCP Tools: {reg.tool_info()[:2000]}

User Query: {query}"""

        fallback = False
        try:
            structured_llm = llm.with_structured_output(ToolSelectionDecision)
            decision = run_with_timeout(
                lambda: structured_llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=user_prompt)]),
                timeout_s=timeout_s,
            )
            selected_tools = [t for t in decision.selected_tools if t in all_tools]
            selected_servers = list({t.split(".")[0] for t in selected_tools if "." in t})
            confidence = 0.9

            if not selected_tools:
                fallback = True
                selected_tools = all_tools
                selected_servers = server_names
                confidence = 0.3
        except Exception as exc:
            logger.warning(f"LLM discovery failed: {exc}; triggering fallback.")
            fallback = True
            selected_tools = all_tools
            selected_servers = server_names
            confidence = 0.1

        return selected_servers, selected_tools, confidence, fallback


discoverer = CapabilityDiscoverer()


def discover_tools(
    state: dict, query: str, strategy: str = "metadata"
) -> tuple[list[str], list[str], float, bool, int]:
    """Execute dynamic tool discovery, log trace events, and return filtered tools."""
    from observability.trace import make_event, append_event, add_latency

    reg = discoverer._get_registry()
    all_tools = reg.valid_names()
    candidate_count = len(all_tools)

    if strategy == "none":
        return list(reg._servers.keys()), all_tools, 1.0, False, 0

    t0 = time.perf_counter()
    ev_start = make_event(
        state,
        "DISCOVERY_START",
        "discovery",
        status="running",
        metadata={"strategy": strategy, "query": query, "candidate_count": candidate_count},
    )
    append_event(state, ev_start)

    if strategy == "llm":
        servers, tools, conf, fallback = discoverer.discover_llm(query)
    else:  # 'metadata' default
        servers, tools, conf, fallback = discoverer.discover_metadata(query)

    dur_ms = int((time.perf_counter() - t0) * 1000)
    add_latency(state, "discovery", dur_ms)

    ev_result = make_event(
        state,
        "DISCOVERY_RESULT",
        "discovery",
        duration_ms=dur_ms,
        status="success" if not fallback else "warning",
        metadata={
            "strategy": strategy,
            "selected_servers": servers,
            "selected_tools": tools,
            "candidate_count": candidate_count,
            "selected_count": len(tools),
            "confidence": round(conf, 2),
            "fallback": fallback,
            "latency_ms": dur_ms,
        },
    )
    append_event(state, ev_result)

    return servers, tools, conf, fallback, dur_ms
