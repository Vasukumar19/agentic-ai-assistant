import json
import os

cases = []
base_id = 1

def add_case(category, query, expected_route, expected_answer="", expected_tools=None, expected_context_keywords=None):
    global base_id
    case = {
        "id": f"{category}_{base_id:03d}",
        "category": category,
        "query": query,
        "expected_route": expected_route,
    }
    if expected_answer:
        case["expected_answer"] = expected_answer
    if expected_tools is not None:
        case["expected_tools"] = expected_tools
    if expected_context_keywords is not None:
        case["expected_context_keywords"] = expected_context_keywords
    cases.append(case)
    base_id += 1

# Chat Cases (Greetings)
add_case("chat", "Hi there!", "chat")
add_case("chat", "Hello, how are you?", "chat")
add_case("chat", "Good morning agent.", "chat")
add_case("chat", "Hey!", "chat")
add_case("chat", "Thanks for your help.", "chat")
add_case("chat", "Goodbye!", "chat")
add_case("chat", "See ya later.", "chat")
add_case("chat", "Good night.", "chat")
add_case("chat", "hello there", "chat")
add_case("chat", "hi", "chat")

# Memory Update Cases
add_case("memory_update", "My name is John Doe and I am a software engineer.", "memory_update", expected_answer="")
add_case("memory_update", "I prefer using Python for all my backend projects.", "memory_update", expected_answer="")
add_case("memory_update", "My favorite technology is React.", "memory_update", expected_answer="")
add_case("memory_update", "I recently completed a course on machine learning.", "memory_update", expected_answer="")
add_case("memory_update", "I live in New York and I love pizza.", "memory_update", expected_answer="")

# Personal Query Cases (Semantic Memory retrieval)
add_case("personal_query", "What is my name?", "research_query", expected_context_keywords=["John Doe"])
add_case("personal_query", "What backend language do I prefer?", "research_query", expected_context_keywords=["Python"])
add_case("personal_query", "What is my favorite technology?", "research_query", expected_context_keywords=["React"])
add_case("personal_query", "Did I take any recent courses?", "research_query", expected_context_keywords=["machine learning"])
add_case("personal_query", "Where do I live?", "research_query", expected_context_keywords=["New York"])

# RAG Cases (Company Docs)
add_case("rag", "What is the company policy on remote work?", "research_query", expected_context_keywords=["hybrid schedule", "Tuesdays and Thursdays", "Remote-First"])
add_case("rag", "How many days of annual leave do I get?", "research_query", expected_context_keywords=["20 days", "annual leave"])
add_case("rag", "Is there a hardware stipend for home office?", "research_query", expected_context_keywords=["$1,000", "hardware stipend"])
add_case("rag", "How many days of sick leave are allowed?", "research_query", expected_context_keywords=["10 days", "sick leave", "doctor's note"])
add_case("rag", "What frontend technology stack is approved?", "research_query", expected_context_keywords=["React 18", "TypeScript", "TailwindCSS"])
add_case("rag", "What backend framework do we use?", "research_query", expected_context_keywords=["Python", "FastAPI", "Django"])
add_case("rag", "What database should I use for caching?", "research_query", expected_context_keywords=["Redis"])
add_case("rag", "How many approvals are needed for a pull request?", "research_query", expected_context_keywords=["two approvals", "senior engineers"])
add_case("rag", "What is the minimum test coverage required?", "research_query", expected_context_keywords=["80% coverage"])
add_case("rag", "What is the process for a Sev-1 incident?", "research_query", expected_context_keywords=["war room", "#incidents-war-room", "PagerDuty", "Post-mortems"])

# Calculator Cases
add_case("calculator", "What is 45 * 12?", "research_query", expected_tools=["calculator"], expected_answer="540")
add_case("calculator", "Calculate 1024 / 8", "research_query", expected_tools=["calculator"], expected_answer="128")
add_case("calculator", "What is the square root of 144?", "research_query", expected_tools=["calculator"], expected_answer="12")
add_case("calculator", "Add 50, 75, and 125 together.", "research_query", expected_tools=["calculator"], expected_answer="250")
add_case("calculator", "What is 15 percent of 200?", "research_query", expected_tools=["calculator"], expected_answer="30")
add_case("calculator", "2 to the power of 10", "research_query", expected_tools=["calculator"], expected_answer="1024")
add_case("calculator", "100 minus 37", "research_query", expected_tools=["calculator"], expected_answer="63")
add_case("calculator", "Calculate 5 * (4 + 6)", "research_query", expected_tools=["calculator"], expected_answer="50")

# Web Search Cases
add_case("web_search", "Who is the current CEO of Microsoft?", "research_query", expected_tools=["web_search"])
add_case("web_search", "What is the capital of France?", "research_query", expected_tools=["web_search"])
add_case("web_search", "When was the James Webb Space Telescope launched?", "research_query", expected_tools=["web_search"])
add_case("web_search", "What is the weather in Tokyo right now?", "research_query", expected_tools=["web_search"])
add_case("web_search", "Who won the World Series in 2023?", "research_query", expected_tools=["web_search"])
add_case("web_search", "What is the latest version of Python?", "research_query", expected_tools=["web_search"])
add_case("web_search", "Who directed the movie Inception?", "research_query", expected_tools=["web_search"])

# Multi-step (Search + Calc)
add_case("multi_step", "Find the population of California and multiply it by 2.", "research_query", expected_tools=["web_search", "calculator"])
add_case("multi_step", "What is the height of Mount Everest in feet divided by 10?", "research_query", expected_tools=["web_search", "calculator"])
add_case("multi_step", "Get the current stock price of Apple and add 50 to it.", "research_query", expected_tools=["web_search", "calculator"])
add_case("multi_step", "Find the distance from Earth to the Moon in miles and divide by 100.", "research_query", expected_tools=["web_search", "calculator"])
add_case("multi_step", "Find the release year of the first iPhone and add 10 to it.", "research_query", expected_tools=["web_search", "calculator"])

with open("evaluation/datasets/baseline.json", "w") as f:
    json.dump(cases, f, indent=2)
print(f"Created {len(cases)} cases in evaluation/datasets/baseline.json")
