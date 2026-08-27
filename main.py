"""
Agentic AI Assistant — Production Entry Point (V1 Freeze)
=========================================================

Starts the production agent with:
1. Environment & configuration verification
2. Local Ollama & model connectivity check
3. MCP server discovery & registry initialization
4. Graph compilation & interactive CLI interface
"""

import sys
import json
import urllib.request
from pathlib import Path

from config import (
    LLM_PROVIDER, LLM_MODEL, PLANNING_STRATEGY,
    MAX_EXECUTION_STEPS, RESULT_AWARE_REPLANNING,
    PLANNER_COMPLETION_CONTEXT, GOAL_FULFILLMENT_GUARD,
    MCP_ARGUMENT_REPAIR
)


def verify_ollama_connectivity(model_name: str = "qwen3:8b", host: str = "http://localhost:11434") -> bool:
    """Verify local Ollama server is running and model is available."""
    try:
        req = urllib.request.Request(f"{host}/api/tags", headers={"User-Agent": "agentic-ai-assistant"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            installed_models = [m.get("name", "") for m in data.get("models", [])]
            match = any(model_name in m for m in installed_models)
            if not match:
                print(f"[WARN] Model '{model_name}' not found in Ollama models: {installed_models}")
                print(f"[INFO] You can pull it using: ollama pull {model_name}")
                return False
            return True
    except Exception as e:
        print(f"[ERROR] Could not connect to Ollama at {host}: {e}")
        print("[INFO] Ensure Ollama is running (`ollama serve`)")
        return False


def main():
    print("\n=======================================================")
    print("        AGENTIC AI ASSISTANT — V1 PRODUCTION           ")
    print("=======================================================")
    print(f" LLM Provider:       {LLM_PROVIDER}")
    print(f" LLM Model:          {LLM_MODEL}")
    print(f" Planning Strategy:  {PLANNING_STRATEGY}")
    print(f" Max Budget Steps:   {MAX_EXECUTION_STEPS}")
    print(f" Result-Aware:       {RESULT_AWARE_REPLANNING}")
    print(f" Completion Context: {PLANNER_COMPLETION_CONTEXT}")
    print(f" Goal Guard:         {GOAL_FULFILLMENT_GUARD}")
    print(f" Argument Repair:    {MCP_ARGUMENT_REPAIR}")
    print("=======================================================\n")

    # 1. Check Ollama
    print("[1/4] Checking Ollama connectivity...")
    ollama_ok = verify_ollama_connectivity(LLM_MODEL)
    if ollama_ok:
        print(f"  [OK] Ollama is active and model '{LLM_MODEL}' is ready.")
    else:
        print("  [WARN] Proceeding with initialized graph (verify Ollama before executing queries).")

    # 2. Discover MCP Tools
    print("\n[2/4] Initializing Model Context Protocol (MCP) Registry...")
    from mcp_layer.registry import registry
    registry.load_servers_from_config()
    count = registry.discover(force=True)
    tools = registry.valid_names()
    print(f"  [OK] Discovered {len(tools)} tools across {len(registry._servers)} servers:")
    for t in tools:
        print(f"    - {t}")

    # 3. Compile Graph
    print("\n[3/4] Compiling LangGraph Agent Graph...")
    from graph import create_runnable_graph
    app = create_runnable_graph()
    print("  [OK] Agent graph compiled successfully.")

    # 4. Interactive loop or single run
    print("\n[4/4] Agentic AI Assistant is READY.")
    print("Type your query below or 'exit' / 'quit' to end.\n")

    if len(sys.argv) > 1 and sys.argv[1] != "-i":
        # Single query mode
        query = " ".join(sys.argv[1:])
        print(f"Query: {query}\n")
        out = app.invoke({"question": query})
        print("\n--- Response ---")
        print(out.get("answer", "No response generated."))
        return 0

    while True:
        try:
            user_input = input("User > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break

            print("\nThinking and coordinating tools...")
            out = app.invoke({"question": user_input})
            print("\nAssistant >", out.get("answer", "No response generated."))
            print("-" * 55)
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        except Exception as e:
            print(f"\n[ERROR] Execution failed: {e}\n")


if __name__ == "__main__":
    main()
