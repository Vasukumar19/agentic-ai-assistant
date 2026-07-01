"""
Retrieval Planner Node
======================

Creates a retrieval plan for research queries by deciding which memory sources
are relevant for the current question.
"""

import json

from llm import llm

PLANNER_PROMPT = """You are a retrieval planner.

Your job is to decide which retrieval sources are needed to answer the user's question.
Return ONLY valid JSON with no explanation.

Schema:
{
  "profile": false,
  "semantic": false,
  "rag": false
}

Rules:
- profile: true if the user is asking about their own personal details, preferences, or identity.
- semantic: true if the user is asking about their past experiences, projects, courses, or long-term memories.
- rag: true if the user is asking about company documents, policies, procedures, or internal knowledge.
- If the user asks a general question that does not need personal context or documents, return all false.

Question: {question}"""

DEFAULT_PLAN = {"profile": False, "semantic": False, "rag": False}

PROFILE_HINTS = (
    "my name",
    "what's my name",
    "what is my name",
    "who am i",
    "my goal",
    "my profession",
    "my education",
    "my interests",
    "my preferences",
)

SEMANTIC_HINTS = (
    "projects",
    "project have i",
    "built",
    "courses",
    "experiences",
    "remember when",
    "what did i",
)

RAG_HINTS = (
    "company policy",
    "company policies",
    "policy",
    "policies",
    "procedure",
    "procedures",
    "company document",
    "company documents",
    "internal knowledge",
)


def _normalize_question(question: str) -> str:
    return " ".join(question.strip().lower().split())


def _heuristic_retrieval_plan(question: str) -> dict | None:
    normalized = _normalize_question(question)

    profile = any(hint in normalized for hint in PROFILE_HINTS)
    semantic = any(hint in normalized for hint in SEMANTIC_HINTS)
    rag = any(hint in normalized for hint in RAG_HINTS)

    if profile or semantic or rag:
        return {
            "profile": profile,
            "semantic": semantic,
            "rag": rag,
        }

    return None


def _parse_retrieval_plan(content: str) -> dict | None:
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

    return {
        "profile": bool(data.get("profile", False)),
        "semantic": bool(data.get("semantic", False)),
        "rag": bool(data.get("rag", False)),
    }


def retrieval_planner_node(state: dict) -> dict:
    """Create a retrieval plan from the current question."""
    question = state.get("question", "")

    heuristic_plan = _heuristic_retrieval_plan(question)
    if heuristic_plan is not None:
        return {"retrieval_plan": heuristic_plan}

    prompt = PLANNER_PROMPT.replace("{question}", question)
    response = llm.invoke(prompt)
    retrieval_plan = _parse_retrieval_plan(response.content)
    if retrieval_plan is None:
        retrieval_plan = DEFAULT_PLAN

    return {"retrieval_plan": retrieval_plan}
