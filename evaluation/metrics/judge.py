"""
Phase 4: LLM-as-a-judge with STRICT structured output
=====================================================

Used ONLY where deterministic comparison is insufficient (natural-language
answers, RAG faithfulness). The agent LLM is untouched: the judge is a
separate ChatOllama instance at temperature 0 for determinism.

Every verdict records: judge model, prompt version, raw decision. Raw
decisions are returned to the caller (never silently dropped) so the
original agent result can never be overwritten.
"""

import re

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage

JUDGE_PROMPT_VERSION = "phase4-v1"


class AnswerVerdict(BaseModel):
    correct: bool = Field(description="True only if the actual answer fully satisfies the expected answer.")
    score: float = Field(description="0.0-1.0; 1.0 fully correct, >=0.5 partially correct, <0.5 wrong.")
    reason: str = Field(description="One-sentence justification citing the deciding facts.")
    missing_information: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


class FaithfulnessVerdict(BaseModel):
    faithfulness_score: float = Field(description="0.0-1.0 fraction of the answer supported by the context.")
    supported_claims: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)


ANSWER_JUDGE_PROMPT = """You are a strict, skeptical grader of AI assistant answers.

QUESTION:
{question}

EXPECTED ANSWER / GROUND TRUTH:
{expected}

ADDITIONAL REQUIRED INFORMATION (each item must be satisfied):
{required}

EVIDENCE AVAILABLE TO THE AGENT (tool outputs / retrieved context):
{evidence}

ACTUAL ANSWER:
{actual}

RULES:
- Judge ONLY whether the ACTUAL ANSWER conveys the EXPECTED ANSWER's information and satisfies every required-information item.
- A numerically equivalent value (different formatting or rounding within ~2%) is correct.
- Extra harmless context in the answer is acceptable; MISSING required information is not.
- Any statement in the actual answer that CONTRADICTS the expected answer or evidence must be listed in 'contradictions' and lowers the score below 0.5.
- Do not reward plausible-sounding text that does not answer the question.
"""

FAITHFULNESS_PROMPT = """You are auditing a RAG answer for faithfulness.

QUESTION:
{question}

RETRIEVED CONTEXT (the only admissible evidence):
---
{context}
---

FINAL ANSWER:
---
{answer}
---

TASK:
1. Split the final answer into individual factual claims.
2. Mark each claim supported ONLY if the retrieved context explicitly entails it.
3. Claims requiring outside knowledge not in the context go to unsupported_claims.
4. Claims contradicting the context go to contradictions.
faithfulness_score = supported_claims / total_claims (0 if no claims supported).
"""


def _fmt_expected(expected) -> str:
    if expected is None:
        return "(not provided)"
    if isinstance(expected, list):
        return "\n".join(f"- {e}" for e in expected)
    return str(expected)


class AnswerJudge:
    """Structured-output judge bound to a dedicated low-temperature LLM."""

    def __init__(self, llm_instance=None):
        if llm_instance is None:
            from llm import llm as default_llm
            # Dedicated judge instance: temperature 0 for determinism.
            try:
                base = type(default_llm)
                params = {"temperature": 0}
                if hasattr(default_llm, "model"):
                    params["model"] = default_llm.model
                if getattr(default_llm, "base_url", None):
                    params["base_url"] = default_llm.base_url
                if hasattr(default_llm, "num_ctx") and default_llm.num_ctx:
                    params["num_ctx"] = default_llm.num_ctx
                self.llm = base(**params)
            except Exception:
                self.llm = default_llm
        else:
            self.llm = llm_instance
        self.model_name = getattr(self.llm, "model", type(self.llm).__name__)

    # -- answer correctness ------------------------------------------------
    def judge_answer(self, question, expected, actual,
                     required_information=None, evidence=None) -> dict:
        sllm = self.llm.with_structured_output(AnswerVerdict)
        prompt = ANSWER_JUDGE_PROMPT.format(
            question=question,
            expected=_fmt_expected(expected),
            required="\n".join(f"- {r}" for r in (required_information or ["(none declared)"])),
            evidence=(evidence or "(none captured)")[:4000],
            actual=(actual or "(empty)")[:3000],
        )
        raw = sllm.invoke([SystemMessage(content=prompt),
                           HumanMessage(content="Return the structured verdict.")])
        return {
            "verdict": raw.model_dump(),
            "meta": {"judge_model": self.model_name,
                     "judge_prompt_version": JUDGE_PROMPT_VERSION},
        }

    # -- RAG faithfulness (claim-level) ------------------------------------
    def judge_faithfulness(self, question, context, answer) -> dict:
        sllm = self.llm.with_structured_output(FaithfulnessVerdict)
        prompt = FAITHFULNESS_PROMPT.format(
            question=question, context=(context or "")[:6000],
            answer=(answer or "")[:2000])
        raw = sllm.invoke([SystemMessage(content=prompt),
                           HumanMessage(content="Return the structured verdict.")])
        return {
            "verdict": raw.model_dump(),
            "meta": {"judge_model": self.model_name,
                     "judge_prompt_version": JUDGE_PROMPT_VERSION},
        }


# ---------------------------------------------------------------------------
# Deterministic claim-splitting cross-check (used alongside the judge)
# ---------------------------------------------------------------------------

_CLAIM_SPLIT_RE = re.compile(r"(?<=[.!?:;])\s+|\n+")


def split_claims(answer: str) -> list[str]:
    """Practical claim segmentation: sentences/clauses."""
    parts = [p.strip(" .;,") for p in _CLAIM_SPLIT_RE.split(answer or "") if p.strip()]
    claims = []
    for p in parts:
        # split coordinate clauses on ' and ' only when both halves look factual
        if len(p.split()) > 14 and " and " in p:
            claims.extend(seg.strip() for seg in p.split(" and ") if seg.strip())
        else:
            claims.append(p)
    return claims


def deterministic_faithfulness(context: str, answer: str,
                               support_threshold: float = 0.6) -> dict:
    """Word-overlap support check per claim. Cheap cross-check of the judge;
    deliberately conservative (context words must appear in the claim)."""
    ctx_words = set(content_words_local(context))
    claims = split_claims(answer)
    supported, unsupported = [], []
    for c in claims:
        words = content_words_local(c)
        if not words:
            continue
        hit = sum(1 for w in words[:30] if w in ctx_words)
        (supported if hit / min(len(words), 30) >= support_threshold else unsupported).append(c)
    total = len(supported) + len(unsupported)
    return {
        "claims_total": total,
        "supported": supported,
        "unsupported": unsupported,
        "score": round(len(supported) / total, 3) if total else None,
    }


def content_words_local(text: str) -> list[str]:
    from .quality import content_words
    return content_words(text)
