"""
Memory Extraction & Storage Nodes — with observability.
"""

import json
import logging
import time
from llm import llm
from config import MEMORY_FILE, SEMANTIC_MEMORY_DIR, TIMEOUT_LLM_S, LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME

logger = logging.getLogger(__name__)

MEMORY_EXTRACTOR_PROMPT = """You are a memory extractor.

Return ONLY valid JSON with no explanation.

Schema:
{
  "extracted_profile": {
    "name": "",
    "goal": "",
    "profession": "",
    "education": "",
    "interests": [],
    "favorite_technologies": [],
    "preferences": []
  },
  "extracted_semantic": []
}

Rules:
- extracted_profile should contain stable personal facts only.
- extracted_semantic should contain long-term memories, projects, courses, or experiences.
- Do not include conversational filler or questions.
- If nothing relevant is found, return empty values.

Message: {message}"""


def memory_extractor_node(state: dict) -> dict:
    """Extract memory facts from the user's message and return structured memory updates."""
    t0 = time.perf_counter()
    question = state.get("question", "")
    prompt = MEMORY_EXTRACTOR_PROMPT.replace("{message}", question)
    try:
        from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
        def _call():
            return llm.invoke(prompt)
        try:
            response = run_with_timeout(_call, TIMEOUT_LLM_S)
        except ObsTimeout as te:
            dur = int((time.perf_counter() - t0) * 1000)
            try:
                from observability.trace import make_event, append_event, add_latency
                from observability.errors import make_error_payload, ErrorType
                add_latency(state, "memory_extractor", dur)
                err = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "memory_extractor", str(te), trace_id=state.get("trace_id"))
                ev = make_event(state, "TIMEOUT", "memory_extractor", duration_ms=dur, status="timeout",
                                metadata={"timeout_s": TIMEOUT_LLM_S}, error=err)
                append_event(state, ev)
            except Exception:
                pass
            return {"extracted_profile": {}, "extracted_semantic": [],
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
        content = response.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        default_profile = {}
        default_semantic = []
        try:
            data = json.loads(content)
            extracted_profile = data.get("extracted_profile", default_profile) or default_profile
            extracted_semantic = data.get("extracted_semantic", default_semantic) or default_semantic
        except json.JSONDecodeError as e:
            logger.warning("Memory extraction JSON parse failed: %s", e)
            extracted_profile = default_profile
            extracted_semantic = default_semantic

        # llm usage
        try:
            from observability.trace import extract_llm_usage
            if state.get("llm_usage") is None:
                state["llm_usage"] = []
            dur_ms = int((time.perf_counter() - t0) * 1000)
            usage = extract_llm_usage(response, dur_ms)
            usage.update({"node": "memory_extractor", "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
            state["llm_usage"].append(usage)
        except Exception:
            pass

        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            add_latency(state, "memory_extractor", dur)
            ev = make_event(state, "MEMORY_WRITE", "memory_extractor", duration_ms=dur, status="success",
                            metadata={"operation": "extract", "fields": list((extracted_profile or {}).keys()),
                                      "semantic_count": len(extracted_semantic or []), "phase": "extract"})
            append_event(state, ev)
        except Exception:
            pass
        return {"extracted_profile": extracted_profile, "extracted_semantic": extracted_semantic,
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown"), "llm_usage": state.get("llm_usage")}
    except Exception as exc:
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import classify_error, make_error_payload
            add_latency(state, "memory_extractor", dur)
            err_type = classify_error(exc, component="memory_extractor")
            err = make_error_payload(err_type, "memory_extractor", str(exc), trace_id=state.get("trace_id"))
            ev = make_event(state, "MEMORY_WRITE", "memory_extractor", duration_ms=dur, status="error",
                            metadata={"error": str(exc)[:300]}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        return {"extracted_profile": {}, "extracted_semantic": [],
                "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                "latency_breakdown": state.get("latency_breakdown")}


def memory_saver_node(state: dict) -> dict:
    import time
    t0 = time.perf_counter()
    from datetime import datetime
    from langchain_core.documents import Document
    from langchain_community.vectorstores import FAISS
    from .embeddings import embeddings

    extracted_profile = state.get("extracted_profile", {})
    extracted_semantic = state.get("extracted_semantic", [])

    clean_profile = {k: v for k, v in extracted_profile.items() if v not in (None, "", [], {})}

    saved_fields = []
    saved_sem = 0
    try:
        if clean_profile:
            MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            if MEMORY_FILE.exists():
                try:
                    with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                        memory = json.load(f)
                except json.JSONDecodeError as e:
                    logger.warning("Profile JSON parse failed: %s", e)
                    memory = {}
            else:
                memory = {}
            memory.update(clean_profile)
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=4)
            logger.info("Saved profile memory")
            saved_fields = list(clean_profile.keys())

        if extracted_semantic:
            SEMANTIC_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            if SEMANTIC_MEMORY_DIR.exists():
                try:
                    vector_store = FAISS.load_local(str(SEMANTIC_MEMORY_DIR), embeddings, allow_dangerous_deserialization=True)
                except Exception as e:
                    logger.warning("Error loading semantic memory FAISS index: %s", e)
                    vector_store = None
            else:
                vector_store = None
            for memory_text in extracted_semantic:
                doc = Document(page_content=memory_text, metadata={"timestamp": datetime.utcnow().isoformat()})
                if vector_store is None:
                    vector_store = FAISS.from_documents([doc], embeddings)
                else:
                    vector_store.add_documents([doc])
            if vector_store is not None:
                vector_store.save_local(str(SEMANTIC_MEMORY_DIR))
                logger.info("Saved %d semantic memories", len(extracted_semantic))
                saved_sem = len(extracted_semantic)
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            add_latency(state, "memory_saver", dur)
            ev = make_event(state, "MEMORY_WRITE", "memory_saver", duration_ms=dur, status="success",
                            metadata={"operation": "save", "fields": saved_fields, "semantic_count": saved_sem})
            append_event(state, ev)
        except Exception:
            pass
        return {"trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}
    except Exception as exc:
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import classify_error, make_error_payload
            add_latency(state, "memory_saver", dur)
            err_type = classify_error(exc, component="memory_saver")
            err = make_error_payload(err_type, "memory_saver", str(exc), trace_id=state.get("trace_id"))
            ev = make_event(state, "MEMORY_WRITE", "memory_saver", duration_ms=dur, status="error",
                            metadata={"error": str(exc)[:300]}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        return {"trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}


def memory_response_node(state: dict) -> dict:
    import time
    t0 = time.perf_counter()
    extracted_profile = state.get("extracted_profile", {})
    extracted_semantic = state.get("extracted_semantic", [])
    parts = ["Got it! I'll remember that"]
    name = str(extracted_profile.get("name") or "").strip()
    if name:
        parts.append(f"your name is {name}")
    goal = str(extracted_profile.get("goal") or "").strip()
    if goal:
        if goal.lower().startswith("to "):
            parts.append(f"your goal is {goal}")
        else:
            parts.append(f"your goal is to become an {goal}")
    interests = extracted_profile.get("interests") or []
    if interests:
        parts.append(f"you are interested in {', '.join(map(str, interests))}")
    if extracted_semantic:
        parts.append(f"you {extracted_semantic[0].lower()}")
        for mem in extracted_semantic[1:]:
            parts.append(f"and you {mem.lower()}")
    answer = ", ".join(parts) + "." if parts else "I've updated my memory."
    logger.debug("Memory update confirmation: %s...", answer[:60])
    dur = int((time.perf_counter() - t0) * 1000)
    try:
        from observability.trace import make_event, append_event, add_latency
        add_latency(state, "memory_response", dur)
        ev = make_event(state, "MEMORY_WRITE", "memory_response", duration_ms=dur, status="success",
                        metadata={"operation": "confirm", "answer_chars": len(answer)})
        append_event(state, ev)
    except Exception:
        pass
    return {"answer": answer, "trace_events": state.get("trace_events"),
            "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown")}
