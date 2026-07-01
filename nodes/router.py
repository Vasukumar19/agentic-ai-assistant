"""
Intent Router Node
==================

Routes incoming question to one of three paths:
- chat: Direct response (greetings, small talk)
- memory_update: User sharing personal info
- research_query: Needs retrieval or tool use
"""

import json

from llm import llm

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


def _classify_with_llm(question: str) -> str:
    prompt = ROUTER_PROMPT.replace("{message}", question)
    response = llm.invoke(prompt)
    route = _parse_route(response.content)
    if route is not None:
        return route

    response = llm.invoke(prompt)
    route = _parse_route(response.content)
    if route is not None:
        return route

    return "research_query"


def intent_router(state: dict) -> dict:
    """Classify user intent and route to the appropriate path."""
    question = state.get("question", "")

    if _is_greeting(question):
        route = "chat"
    elif _is_obvious_question(question):
        route = "research_query"
    else:
        route = _classify_with_llm(question)

    print(f"  [Router] Question: '{question[:50]}...'")
    print(f"  [Router] Route: {route}")

    return {"route": route}
