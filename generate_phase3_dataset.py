import json
import os

queries = [
    # Single-tool (Calculator)
    {"id": "multi_001", "query": "What is 25 * 40?", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False},
    {"id": "multi_002", "query": "Calculate 15% of 850.", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False},
    {"id": "multi_003", "query": "What is 1024 divided by 8?", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False},
    {"id": "multi_004", "query": "Subtract 45 from 200.", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False},
    {"id": "multi_005", "query": "Find the square root of 144.", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False},

    # Single-tool (Web Search)
    {"id": "multi_006", "query": "Find the current population of India.", "expected_tools": ["web_search"], "expected_sequence": ["web_search"], "requires_multi_step": False},
    {"id": "multi_007", "query": "Who is the CEO of Microsoft?", "expected_tools": ["web_search"], "expected_sequence": ["web_search"], "requires_multi_step": False},
    {"id": "multi_008", "query": "What is the capital of France?", "expected_tools": ["web_search"], "expected_sequence": ["web_search"], "requires_multi_step": False},
    {"id": "multi_009", "query": "When was Python 3.0 released?", "expected_tools": ["web_search"], "expected_sequence": ["web_search"], "requires_multi_step": False},
    {"id": "multi_010", "query": "What is the distance to the Moon?", "expected_tools": ["web_search"], "expected_sequence": ["web_search"], "requires_multi_step": False},

    # Search -> Calculator
    {"id": "multi_011", "query": "Find India's population and calculate 5% of it.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_012", "query": "Search for the price of 1 Bitcoin in USD and multiply it by 3.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_013", "query": "Find the population of Tokyo and divide it by 10.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_014", "query": "What is the height of Mount Everest in meters, and what is that divided by 2?", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_015", "query": "Find the GDP of Germany and calculate 1% of it.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "calculator"], "requires_multi_step": True},
    
    # Search -> Search -> Compare
    {"id": "multi_016", "query": "Find the populations of India and China and compare them.", "expected_tools": ["web_search"], "expected_sequence": ["web_search", "web_search"], "requires_multi_step": True},
    {"id": "multi_017", "query": "Compare the GDP of USA and Japan.", "expected_tools": ["web_search"], "expected_sequence": ["web_search", "web_search"], "requires_multi_step": True},
    {"id": "multi_018", "query": "Who is older: Joe Biden or Donald Trump?", "expected_tools": ["web_search"], "expected_sequence": ["web_search", "web_search"], "requires_multi_step": True},
    {"id": "multi_019", "query": "Find the tallest building in New York and the tallest building in Dubai, and tell me the difference in height.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_020", "query": "Compare the current stock price of Apple and Microsoft.", "expected_tools": ["web_search"], "expected_sequence": ["web_search", "web_search"], "requires_multi_step": True},

    # RAG -> Calculator
    {"id": "multi_021", "query": "According to the company policy, what is the hardware reimbursement limit and what would 3 employees receive in total?", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},
    {"id": "multi_022", "query": "How many PTO days do we get, and what is that divided by 12?", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},
    {"id": "multi_023", "query": "What is the training budget per employee? Multiply it by 5.", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},
    {"id": "multi_024", "query": "Find the wellness stipend amount in our policies and calculate 10% of it.", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},
    {"id": "multi_025", "query": "Look up our remote work days limit and multiply it by 2.", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},

    # RAG -> Web Search
    {"id": "multi_026", "query": "According to our internal document, what frontend framework do we use, and what is the latest version of it on the web?", "expected_tools": ["rag", "web_search"], "expected_sequence": ["rag", "web_search"], "requires_multi_step": True},
    {"id": "multi_027", "query": "What cloud provider is listed in our engineering stack, and what is their current stock price?", "expected_tools": ["rag", "web_search"], "expected_sequence": ["rag", "web_search"], "requires_multi_step": True},
    {"id": "multi_028", "query": "Which laptop do engineers get according to policy, and what is its retail price online?", "expected_tools": ["rag", "web_search"], "expected_sequence": ["rag", "web_search"], "requires_multi_step": True},
    {"id": "multi_029", "query": "Find the CEO of the company in our internal docs, and search the web for their latest news.", "expected_tools": ["rag", "web_search"], "expected_sequence": ["rag", "web_search"], "requires_multi_step": True},
    {"id": "multi_030", "query": "What is our primary database technology internally, and what is its latest release date?", "expected_tools": ["rag", "web_search"], "expected_sequence": ["rag", "web_search"], "requires_multi_step": True},

    # Complex multi-step / Mix
    {"id": "multi_031", "query": "Find India's population, China's population, subtract them, and find 10% of the difference.", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "web_search", "calculator", "calculator"], "requires_multi_step": True},
    {"id": "multi_032", "query": "Check the hardware policy for the laptop budget, search for a MacBook Pro price, and calculate if it is within budget.", "expected_tools": ["rag", "web_search", "calculator"], "expected_sequence": ["rag", "web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_033", "query": "What is the training budget? Find the cost of an AWS Certified Solutions Architect exam, and tell me how much budget would be left.", "expected_tools": ["rag", "web_search", "calculator"], "expected_sequence": ["rag", "web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_034", "query": "Find the distance from Earth to Mars, and from Earth to Venus. Which is closer?", "expected_tools": ["web_search", "calculator"], "expected_sequence": ["web_search", "web_search", "calculator"], "requires_multi_step": True},
    {"id": "multi_035", "query": "According to the leave policy, how many sick days do we get? If I used 3, how many are left?", "expected_tools": ["rag", "calculator"], "expected_sequence": ["rag", "calculator"], "requires_multi_step": True},
    
    # Simple Single Tool (Memory)
    {"id": "multi_036", "query": "Remember that my name is Alice.", "expected_tools": ["memory_update"], "expected_sequence": ["memory_update"], "requires_multi_step": False},
    {"id": "multi_037", "query": "What did I say my name was?", "expected_tools": ["memory_search"], "expected_sequence": ["memory_search"], "requires_multi_step": False},
    
    # Add more to reach 50...
    *[
        {"id": f"multi_{str(i).zfill(3)}", "query": f"Calculate {i} + {i*2}", "expected_tools": ["calculator"], "expected_sequence": ["calculator"], "requires_multi_step": False} for i in range(38, 51)
    ]
]

os.makedirs("evaluation/datasets", exist_ok=True)
with open("evaluation/datasets/phase3_multistep.json", "w") as f:
    json.dump(queries, f, indent=2)
print("Generated Phase 3 Multi-Step Dataset.")
