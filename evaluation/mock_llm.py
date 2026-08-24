from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
import json

class MockLLM(Runnable):
    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools, **kwargs):
        return self

    def invoke(self, messages, **kwargs):
        self.call_count += 1
        
        # Determine if it's a planner prompt or agent prompt
        if isinstance(messages, str) or (isinstance(messages, list) and isinstance(messages[0].content, str) and "You are a retrieval planner" in messages[0].content):
            # Planner prompt
            query = messages if isinstance(messages, str) else messages[-1].content
            # Extract just the question part
            if "Question: " in query:
                query = query.split("Question: ")[-1]
            query = query.lower()
            if "policy" in query or "document" in query or "budget" in query or "days" in query:
                return AIMessage(content='```json\n{"rag": true, "profile": false, "semantic": false}\n```')
            if "my name" in query or "who am i" in query:
                return AIMessage(content='```json\n{"rag": false, "profile": true, "semantic": false}\n```')
            return AIMessage(content='```json\n{"rag": false, "profile": false, "semantic": false}\n```')
            
        # Extract the user query from the messages
        query = ""
        tool_results_count = 0
        for m in messages:
            if m.type == "human" and "User Query:" in m.content:
                query = m.content.split("User Query: ")[-1].strip()
            elif m.type == "tool":
                tool_results_count += 1
                
        # Baseline Failure Simulation:
        # We want ~50% tool selection accuracy.
        
        # Single tool: Calculator
        if "What is 25 * 40?" in query:
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "25 * 40"}, "id": "call_1"}])
            return AIMessage(content="The answer is 1000.")
            
        if "Calculate 15% of 850." in query:
            if tool_results_count == 0:
                # Simulate WRONG TOOL (uses web search instead of calculator)
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "15% of 850"}, "id": "call_2"}])
            return AIMessage(content="It is 127.5.")
            
        if "What is 1024 divided by 8?" in query:
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "1024 / 8"}, "id": "call_3"}])
            return AIMessage(content="The answer is 128.")

        # Search -> Calculator
        if "Find India's population and calculate 5% of it." in query:
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "India population"}, "id": "call_4"}])
            if tool_results_count == 1:
                # Simulate PREMATURE STOP
                return AIMessage(content="India's population is 1.4 billion. 5% would be 70 million.")
                
        if "Search for the price of 1 Bitcoin in USD and multiply it by 3." in query:
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "1 Bitcoin in USD price"}, "id": "call_5"}])
            if tool_results_count == 1:
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "60000 * 3"}, "id": "call_6"}])
            return AIMessage(content="The answer is 180000.")
            
        if "Find the population of Tokyo and divide it by 10." in query:
            if tool_results_count == 0:
                # Simulate MISSING TOOL (Tries to calculate without searching)
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "14000000 / 10"}, "id": "call_7"}])
            return AIMessage(content="The answer is 1400000.")

        # Search -> Search -> Compare
        if "Find the populations of India and China and compare them." in query:
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "India population"}, "id": "call_8"}])
            if tool_results_count == 1:
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "China population"}, "id": "call_9"}])
            return AIMessage(content="India has slightly more people than China.")

        # RAG -> Calculator
        if "According to the company policy, what is the hardware reimbursement limit and what would 3 employees receive in total?" in query:
            # RAG is a pre-node. tool_results_count refers only to agent tools.
            if tool_results_count == 0:
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "1000 * 3"}, "id": "call_10"}])
            return AIMessage(content="3 employees would receive 3000.")

        if "How many PTO days do we get, and what is that divided by 12?" in query:
            if tool_results_count == 0:
                # UNNECESSARY TOOL call
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "PTO days"}, "id": "call_11"}])
            if tool_results_count == 1:
                return AIMessage(content="", tool_calls=[{"name": "calculator", "args": {"expression": "20 / 12"}, "id": "call_12"}])
            return AIMessage(content="1.66 days per month.")

        # Fallback for all other queries: just stop immediately to simulate failure or success
        if tool_results_count == 0:
            if hash(query) % 2 == 0:
                return AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "search"}, "id": "call_x"}])
            else:
                return AIMessage(content="I'm done without using tools.")
                
        return AIMessage(content="Task complete.")
