"""Unified LLM Provider Factory — Seamless Local ($0 Ollama) ↔ Cloud (Claude/GPT) Switching."""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

# Load .env
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from config import MODEL_NAME, TEMPERATURE, LLM_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)


def normalize_message(msg):
    if isinstance(msg, AIMessage) and isinstance(msg.content, list):
        texts = []
        for item in msg.content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
        new_content = "".join(texts)
        return AIMessage(
            content=new_content,
            additional_kwargs=msg.additional_kwargs,
            response_metadata=msg.response_metadata,
            id=msg.id,
            tool_calls=getattr(msg, "tool_calls", []),
        )
    return msg


class NormalizedGoogleGenAI(Runnable):
    """Wraps ChatGoogleGenerativeAI to guarantee string contents on AIMessage."""
    def __init__(self, raw_llm):
        self.raw_llm = raw_llm

    def invoke(self, input, config=None, **kwargs):
        res = self.raw_llm.invoke(input, config=config, **kwargs)
        return normalize_message(res)

    def with_structured_output(self, schema, **kwargs):
        return self.raw_llm.with_structured_output(schema, **kwargs)

    def bind_tools(self, tools, **kwargs):
        return self.raw_llm.bind_tools(tools, **kwargs)

    def __or__(self, other):
        return Runnable.from_runnable(self) | other

    def __ror__(self, other):
        return other | Runnable.from_runnable(self)


def get_llm():
    """Instantiate the active LLM based on environment configuration."""
    if os.getenv("MOCK_LLM") == "1":
        from evaluation.mock_llm import MockLLM
        return MockLLM()

    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    model_override = os.getenv("LLM_MODEL", LLM_MODEL)

    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_override or "qwen3:8b",
            base_url=OLLAMA_BASE_URL,
            temperature=TEMPERATURE,
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
            reasoning=os.getenv("OLLAMA_REASONING", "0").lower() not in ("0", "false", "no"),
        )
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_override or "claude-3-5-sonnet-latest",
            temperature=TEMPERATURE,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model_override or "gpt-4o",
            temperature=TEMPERATURE,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        raw_llm = ChatGoogleGenerativeAI(
            model=model_override or "gemini-1.5-pro",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=TEMPERATURE,
        )
        return NormalizedGoogleGenAI(raw_llm)
    elif provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model_override or "llama-3.1-8b-instant",
            temperature=TEMPERATURE,
            groq_api_key=os.getenv("GROQ_API_KEY"),
        )
    else:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=model_override or "qwen3:8b",
            base_url=OLLAMA_BASE_URL,
            temperature=TEMPERATURE,
        )


llm = get_llm()
