"""
Chat Node — with observability.
"""

import logging
import time
from llm import llm
from langchain_core.messages import SystemMessage, HumanMessage
from config import TIMEOUT_LLM_S, LLM_PROVIDER, LLM_MODEL_OVERRIDE, MODEL_NAME

logger = logging.getLogger(__name__)


def chat_node(state: dict) -> dict:
    t0 = time.perf_counter()
    question = state.get("question", "")
    messages = state.get("messages", [])
    system_prompt = "You are a friendly and helpful AI assistant."
    llm_input = [SystemMessage(content=system_prompt)]
    llm_input.extend(messages)
    has_current_question = False
    if messages and isinstance(messages[-1], HumanMessage) and messages[-1].content == question:
        has_current_question = True
    if not has_current_question:
        llm_input.append(HumanMessage(content=question))
    try:
        from observability.timeout import run_with_timeout, TimeoutError as ObsTimeout
        def _call():
            return llm.invoke(llm_input)
        try:
            response = run_with_timeout(_call, TIMEOUT_LLM_S)
        except ObsTimeout as te:
            dur = int((time.perf_counter() - t0) * 1000)
            try:
                from observability.trace import make_event, append_event, add_latency
                from observability.errors import make_error_payload, ErrorType
                add_latency(state, "chat", dur)
                err = make_error_payload(ErrorType.TIMEOUT_ERROR.value, "chat", str(te), trace_id=state.get("trace_id"))
                ev = make_event(state, "TIMEOUT", "chat", duration_ms=dur, status="timeout",
                                metadata={"timeout_s": TIMEOUT_LLM_S}, error=err)
                append_event(state, ev)
            except Exception:
                pass
            return {"answer": "I'm sorry, the chat timed out. Please try again.",
                    "trace_events": state.get("trace_events"), "trace_step": state.get("trace_step"),
                    "latency_breakdown": state.get("latency_breakdown")}
        answer = response.content
        logger.debug("Chat response for: %s...", question[:50])
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency, extract_llm_usage
            add_latency(state, "chat", dur)
            if state.get("llm_usage") is None:
                state["llm_usage"] = []
            usage = extract_llm_usage(response, dur)
            usage.update({"node": "chat", "provider": LLM_PROVIDER or "unknown", "model": LLM_MODEL_OVERRIDE or MODEL_NAME})
            state["llm_usage"].append(usage)
            ev = make_event(state, "FINAL_ANSWER", "chat", duration_ms=dur, status="success",
                            metadata={"answer_chars": len(answer), "answer_preview": answer[:400]})
            append_event(state, ev)
        except Exception:
            pass
        return {"answer": answer, "trace_events": state.get("trace_events"),
                "trace_step": state.get("trace_step"), "latency_breakdown": state.get("latency_breakdown"),
                "llm_usage": state.get("llm_usage")}
    except Exception as exc:
        dur = int((time.perf_counter() - t0) * 1000)
        try:
            from observability.trace import make_event, append_event, add_latency
            from observability.errors import classify_error, make_error_payload
            add_latency(state, "chat", dur)
            err_type = classify_error(exc, component="chat")
            err = make_error_payload(err_type, "chat", str(exc), trace_id=state.get("trace_id"))
            ev = make_event(state, "ERROR", "chat", duration_ms=dur, status="error",
                            metadata={"error": str(exc)[:300]}, error=err)
            append_event(state, ev)
        except Exception:
            pass
        raise
