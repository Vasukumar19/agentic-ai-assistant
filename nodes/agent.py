"""
Agent Node
==========

The core reasoning node for research queries.

Uses llm.bind_tools() with only web_search and calculator.
Memory and RAG retrieval are NOT tools - they're graph nodes.
"""
import re
import json
import logging
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from llm import llm

try:
    from groq import BadRequestError as GroqBadRequestError
except ImportError:
    GroqBadRequestError = None

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """You are an intelligent AI assistant capable of reasoning and using tools when necessary.

Your objective is to answer the user's question accurately, efficiently, and with the minimum number of tool calls required.

GUIDELINES:

1. First understand the user's request.

2. Determine whether a tool is actually required.

3. If no tool is required, immediately provide your Final Answer.

4. Use tools only when they provide information that is missing, external, or computational.

5. Use the minimum number of tool calls necessary.
5a. When calling web_search, never pass the user's raw vague phrasing directly.
    Rewrite the query to be specific — add a topic, country, or category.
    Examples: "today news" -> "India news today"; "latest news" -> "world news headlines today".
    If you genuinely can't tell what topic the user means, ask a clarifying
    question instead of searching with a vague query.

6. After receiving a tool result, evaluate whether the information is sufficient to answer the question.

7. If insufficient, you MAY perform another tool call with a better query.

8. Never invent tool outputs.

9. Never claim to have searched, calculated, or retrieved something unless the tool was actually used.

10. IMPORTANT: You must NEVER write a tool call as plain text (e.g. "<function>web_search {...}</function>"
    or "<function=web_search {...}</function>"). Tool calls must ONLY be made through the actual
    tool-calling mechanism provided to you. Writing a function call as text is a critical error.

AVAILABLE TOOLS:

1. web_search
   Purpose: Search the web for current information
   Use for: recent events, news, current facts, external knowledge
   Examples: "Latest AI news", "Current gold price"

2. calculator
   Purpose: Perform arithmetic and math operations
   Use for: mathematical calculations, expressions, numerical results
   Examples: "2 + 2", "sqrt(144)", "100 * 3.14"

DECISION PROCESS:

- For questions about company docs, policies, or internal data → NO tool needed (already retrieved above)
- For questions about user's personal info → NO tool needed (already retrieved above)
- For current external information → web_search
- For math/calculations → calculator
- For everything else → reason without tools

When answering, use the retrieved context (if any) combined with your knowledge.
"""

# Matches hallucinated pseudo tool-call text, capturing tool name + JSON args, e.g.:
# <function\web_search {"query": "..."}</function>
# <function>calculator {"expression": "..."}</function>
# <function=web_search{"query": "..."}</function>
FAKE_TOOL_CALL_RE = re.compile(r"<function[\\=>]?\s*(\w+)\s*(\{.*?\})\s*>?\s*</function>", re.DOTALL)

MAX_HISTORY_MESSAGES = 8        # how many messages we feed to the LLM
MAX_STORED_MESSAGES = 40        # cap on what we keep in state at all

FALLBACK_ANSWER = (
    "I had trouble using a tool for that request. Could you rephrase your question, "
    "or ask it more directly (e.g. 'search for today's news')?"
)


def _looks_like_fake_tool_call(content: str) -> bool:
    if not content:
        return False
    return bool(FAKE_TOOL_CALL_RE.search(content))


def _parse_intended_tool_call(text: str):
    """
    Extract (tool_name, args_dict) from a hallucinated <function=...>{...}</function>
    string, if present. Returns None if nothing parseable is found.
    """
    if not text:
        return None
    m = FAKE_TOOL_CALL_RE.search(text)
    if not m:
        return None
    tool_name, args_str = m.group(1), m.group(2)
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        return None
    return tool_name, args


def _extract_failed_generation(exc: Exception) -> str:
    """
    Groq's SDK typically attaches the parsed error body to `.body`.
    Fall back to regex-parsing str(exc) if that's not available.
    """
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        try:
            return body["error"]["failed_generation"]
        except (KeyError, TypeError):
            pass
    match = re.search(r"'failed_generation':\s*'(.*?)'\s*\}", str(exc))
    if match:
        try:
            return match.group(1).encode().decode("unicode_escape")
        except Exception:
            return match.group(1)
    return ""


def _is_tool_use_failed_error(exc: Exception) -> bool:
    if GroqBadRequestError is not None and isinstance(exc, GroqBadRequestError):
        return True
    msg = str(exc)
    return "tool_use_failed" in msg or "Failed to call a function" in msg


def _sanitize_history(messages: list) -> list:
    """
    Strip any prior AIMessage whose content is a hallucinated pseudo tool-call.
    Prevents the model from imitating its own past mistakes.
    """
    cleaned = []
    for msg in messages:
        if isinstance(msg, AIMessage) and _looks_like_fake_tool_call(msg.content):
            cleaned.append(AIMessage(content="[tool call executed]"))
        else:
            cleaned.append(msg)
    return cleaned


def _run_tool_by_name(tools, tool_name: str, args: dict):
    """
    Look up a bound tool by name and execute it directly with the given args.
    Returns (result_str, error_str). Exactly one of the two will be non-None.
    """
    tool_map = {t.name: t for t in tools}
    tool = tool_map.get(tool_name)
    if tool is None:
        return None, f"No tool named '{tool_name}' is available."
    try:
        result = tool.invoke(args)
        return str(result), None
    except Exception as exc:
        return None, f"Tool '{tool_name}' raised an error: {exc}"


def agent_node(state: dict) -> dict:
    """
    Main reasoning node. Decides when to use tools and generates answer.
    """
    from .tools import tools

    question = state.get("question", "")
    messages = state.get("messages", [])
    context = state.get("_combined_context", "")

    if context:
        user_prompt = f"RETRIEVED CONTEXT:\n{context}\n\nUser Query: {question}"
    else:
        user_prompt = f"User Query: {question}"

    llm_with_tools = llm.bind_tools(tools, tool_choice="auto")

    if len(messages) > MAX_STORED_MESSAGES:
        messages = messages[-MAX_STORED_MESSAGES:]

    recent_messages = _sanitize_history(messages[-MAX_HISTORY_MESSAGES:])

    def _invoke(extra_system_note: str = ""):
        system_content = AGENT_SYSTEM_PROMPT + extra_system_note
        return llm_with_tools.invoke([
            SystemMessage(content=system_content),
            *recent_messages,
            HumanMessage(content=user_prompt),
        ])

    tool_result_text = None  # populated if we self-heal a failed tool call
    healed_tool_name = None
    response = None

    try:
        response = _invoke()
    except Exception as exc:
        if not _is_tool_use_failed_error(exc):
            raise
        logger.warning("Native tool call rejected (tool_use_failed): %s", exc)

        # Try to recover the tool call the model actually intended, and run it ourselves.
        failed_gen = _extract_failed_generation(exc)
        parsed = _parse_intended_tool_call(failed_gen)

        if parsed:
            tool_name, args = parsed
            result, err = _run_tool_by_name(tools, tool_name, args)
            if result is not None:
                tool_result_text = result
                healed_tool_name = tool_name
                logger.info("Self-healed tool call: %s(%s)", tool_name, args)
            else:
                logger.warning("Manual tool execution failed: %s", err)
        else:
            logger.warning("Could not parse an intended tool call from failed_generation")

    if tool_result_text is not None:
        # We recovered the tool output ourselves — ask the model to synthesize
        # a final answer using it, without needing tools this time.
        try:
            response = llm.invoke([
                SystemMessage(
                    content=AGENT_SYSTEM_PROMPT
                    + f"\n\nA '{healed_tool_name}' tool call was already executed on your behalf. "
                      "Use its result below to answer the user directly. Do not attempt another tool call."
                ),
                *recent_messages,
                HumanMessage(content=f"{user_prompt}\n\nTOOL RESULT ({healed_tool_name}):\n{tool_result_text}"),
            ])
        except Exception as exc:
            logger.error("Synthesis call after manual tool execution failed: %s", exc)
            new_messages = messages + [
                HumanMessage(content=user_prompt),
                AIMessage(content=FALLBACK_ANSWER),
            ]
            return {"messages": new_messages, "answer": FALLBACK_ANSWER}

    elif response is None:
        # Groq failed AND we couldn't recover/parse/execute the intended tool call.
        # Last resort: answer without tools, but be honest this may be limited.
        logger.warning("Falling back to plain reasoning — no tool result recovered")
        try:
            response = llm.invoke([
                SystemMessage(
                    content=AGENT_SYSTEM_PROMPT
                    + "\n\nNOTE: Tool calling is temporarily unavailable and no tool result could be recovered. "
                      "Answer as best you can, and if you truly cannot answer without a tool, say so plainly."
                ),
                *recent_messages,
                HumanMessage(content=user_prompt),
            ])
        except Exception as exc:
            logger.error("Fallback plain call also failed: %s", exc)
            new_messages = messages + [
                HumanMessage(content=user_prompt),
                AIMessage(content=FALLBACK_ANSWER),
            ]
            return {"messages": new_messages, "answer": FALLBACK_ANSWER}

    # If the model hallucinated a tool call as plain text (but didn't trigger
    # Groq's hard error), retry once with a stricter nudge.
    if not (hasattr(response, "tool_calls") and response.tool_calls) and _looks_like_fake_tool_call(response.content):
        logger.warning("Detected pseudo tool-call text in output, retrying once")
        try:
            response = _invoke(
                extra_system_note="\n\nREMINDER: Do not write tool calls as text under any circumstances. "
                                   "Either use the real tool-calling mechanism, or answer directly without a tool."
            )
        except Exception as exc:
            if not _is_tool_use_failed_error(exc):
                raise
            logger.warning("Retry also hit tool_use_failed: %s", exc)

    if hasattr(response, 'tool_calls') and response.tool_calls:
        new_messages = messages + [
            HumanMessage(content=user_prompt),
            AIMessage(content=response.content, tool_calls=response.tool_calls)
        ]
        return {"messages": new_messages}

    answer = response.content

    if _looks_like_fake_tool_call(answer) or not answer:
        logger.warning("Still no usable answer after retries — using fallback message")
        answer = FALLBACK_ANSWER

    new_messages = messages + [
        HumanMessage(content=user_prompt),
        AIMessage(content=answer)
    ]

    return {
        "messages": new_messages,
        "answer": answer,
    }