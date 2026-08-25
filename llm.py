import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

# Load .env BEFORE importing config, which reads provider env vars at import time.
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

from config import MODEL_NAME, TEMPERATURE, LLM_MODEL_OVERRIDE, OLLAMA_BASE_URL

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


# Provider selection
if os.getenv("MOCK_LLM") == "1":
    from evaluation.mock_llm import MockLLM
    llm = MockLLM()
else:
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("google_api_key")
    openrouter_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("open_router_api")
    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("groq_api_key")
    provider = os.getenv("LLM_PROVIDER", "").lower()

    if provider == "ollama":
        # Local provider (e.g. Ollama + Qwen3) — no API key required.
        # OLLAMA_REASONING=0 (default) disables the Qwen3 <think> block;
        # set to 1 to enable native thinking mode.
        from langchain_ollama import ChatOllama
        llm = ChatOllama(
            model=LLM_MODEL_OVERRIDE or MODEL_NAME,
            base_url=OLLAMA_BASE_URL,
            temperature=TEMPERATURE,
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "8192")),
            reasoning=os.getenv("OLLAMA_REASONING", "0").lower() not in ("0", "false", "no"),
        )
    elif (provider == "google" or not provider) and google_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        raw_llm = ChatGoogleGenerativeAI(
            model=MODEL_NAME if "gemini" in MODEL_NAME else "gemini-3.6-flash",
            google_api_key=google_key,
            temperature=TEMPERATURE,
        )
        llm = NormalizedGoogleGenAI(raw_llm)
    elif (provider == "openrouter" or not provider) and openrouter_key:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=MODEL_NAME if "gemini" not in MODEL_NAME and ":" in MODEL_NAME else "nvidia/nemotron-3-super-120b-a12b:free",
            api_key=openrouter_key,
            base_url="https://openrouter.ai/api/v1",
            temperature=TEMPERATURE,
        )
    elif groq_key:
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=MODEL_NAME if "gemini" not in MODEL_NAME else "llama-3.1-8b-instant",
            temperature=TEMPERATURE,
            groq_api_key=groq_key,
        )
    else:
        raise ValueError("No valid LLM API key configured in .env")
