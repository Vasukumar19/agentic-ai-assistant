"""
Intent Router Node
==================

Routes incoming question to one of three paths:
- chat: Direct response (greetings, small talk)
- memory_update: User sharing personal info
- research_query: Needs retrieval or tool use
"""

import json
import logging

from llm import llm

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """Classify the message route.

Return ONLY valid JSON:
{"route": "chat" | "memory_update" | "research_query"}

- chat: greetings or small talk only
- memory_update: user sharing personal facts to store
- research_query: everything else

Message: {message}"""

GREETINGS = {
    "hi",
    "hello",
    "thanks",
    "bye",
    "good morning",
    "good night",
}

QUESTION_PREFIXES = (
    "what",
    "why",
    "how",
    "who",
    "where",
    "when",
    "is",
    "are",
    "can",
    "could",
    "does",
    "do",
)


def _normalize_message(message: str) -> str:
    return " ".join(message.strip().lower().split())


def _is_greeting(message: str) -> bool:
    normalized = _normalize_message(message)
    if normalized in GREETINGS:
        return True
    return any(
        normalized == greeting or normalized.startswith(f"{greeting} ")
        for greeting in GREETINGS
    )


def _is_obvious_question(message: str) -> bool:
    stripped = message.strip()
    if stripped.endswith("?"):
        return True

    normalized = _normalize_message(message)
    return any(
        normalized == prefix or normalized.startswith(f"{prefix} ")
        for prefix in QUESTION_PREFIXES
    )


def _parse_route(content: str) -> str | None:
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None

    candidate = data.get("route", "research_query")
    if candidate in {"chat", "memory_update", "research_query"}:
        return candidate
    return "research_query"


def _classify_with_llm(question: str, state: dict | None = None) -> str:
    import time
    prompt = ROUTER_PROMPT.replace("{message}", question)
    # first attempt with usage capture
    t0 = time.perf_counter()
    response = llm.invoke(prompt)
    try:
        if state is not None:
            from observability.trace import extract_llm_usage
            from config import LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME
            if state.get("llm_usage") is None:
                state["llm_usage"] = []
            usage = extract_llm_usage(response, int((time.perf_counter()-t0)*1000))
            usage.update({"node": "intent_router", "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
            state["llm_usage"].append(usage)
    except Exception:
        pass
    route = _parse_route(response.content)
    if route is not None:
        return route
    # second attempt
    t0 = time.perf_counter()
    response = llm.invoke(prompt)
    try:
        if state is not None:
            from observability.trace import extract_llm_usage
            from config import LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME
            usage = extract_llm_usage(response, int((time.perf_counter()-t0)*1000))
            usage.update({"node": "intent_router", "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
            state["llm_usage"].append(usage)
    except Exception:
        pass
    route = _parse_route(response.content)
    if route is not None:
        return route
    logger.warning("Router LLM returned unparseable output twice; defaulting to research_query")
    return "research_query"


def intent_router(state: dict) -> dict:
    """Classify user intent and route to the appropriate path."""
    import time
    t0 = time.perf_counter()
    question = state.get("question", "")
    method = "heuristic"
    try:
        if _is_greeting(question):
            route = "chat"
        elif _is_obvious_question(question):
            route = "research_query"
        else:
            method = "llm"
            route = _classify_with_llm(question, state)

        logger.debug("Routed '%s...' -> %s", question[:50], route)
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            add_latency(state, "router", dur)
            ev = make_event(state, "ROUTER", "intent_router", duration_ms=dur, status="success",
                            metadata={"route": route, "method": method, "question_chars": len(question)})
            append_event(state, ev)
        except Exception:
            pass
        return {"route": route, "trace_events": state.get("trace_events"),
                "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}
    except Exception as exc:
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import classify_error, make_error_payload
            add_latency(state, "router", dur)
            err_type = classify_error(exc, component="intent_router")
            err = make_error_payload(err_type, "intent_router", str(exc), trace_id=state.get("trace_id"))
            ev = make_event(state, "ROUTER", "intent_router", duration_ms=dur, status="error",
                            metadata={"error": str(exc)[:300]}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        raise