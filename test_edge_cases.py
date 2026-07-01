import traceback
from agent_langgraph import ask

edge_cases = [
    ("Empty input", ""),
    ("Whitespace only", "   \n\t  "),
    ("Special characters", "!@#$%^&*()_+{}|:\"<>?~`-=[]\\;',./"),
    ("Very long input", "A" * 5000),
    ("Tool trigger: Calculator", "What is 250 multiplied by 14.5?"),
    ("Tool trigger: Web Search", "What are the latest news about Python 3.13?"),
    ("Memory update", "My name is testing_user_123 and I love writing code."),
    ("Memory retrieval", "What is my name and what do I love doing?"),
    ("Gibberish", "asdfasdfasdf zxcvzxcvzxcv qwerqwerqwer")
]

print("Starting Edge Case Tests...")

for name, query in edge_cases:
    print(f"\n--- Testing: {name} ---")
    try:
        response = ask(query)
        print(f"Response snippet: {response[:100]}...")
    except Exception as e:
        print(f"FAILED with exception: {e}")
        traceback.print_exc()

print("\nTests Complete!")
