from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
import json

class MockLLM(Runnable):
    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools, **kwargs):
        return self
        
    def with_structured_output(self, schema, **kwargs):
        # We know schema is PlannerDecision.
        # LangChain's with_structured_output typically returns a runnable that outputs the parsed Pydantic object.
        # So we can just return a custom runnable that returns the Pydantic object directly!
        class StructuredMock(Runnable):
            def __init__(self, parent):
                self.parent = parent
                self.schema = schema
                
            def invoke(self, messages, **kwargs):
                self.parent.call_count += 1
                
                query = ""
                # Summarized tool results count
                tool_results_count = 0
                for m in messages:
                    if m.type == "human" and "User Query:" in m.content:
                        query = m.content.split("User Query: ")[-1].strip()
                    if m.type == "human" and "PREVIOUS TOOL EXECUTIONS" in m.content:
                        # Count "Step X" in the text
                        tool_results_count = m.content.count("Step ")
                
                # We return an instance of PlannerDecision directly!
                
                if "What is 25 * 40?" in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "25 * 40"})
                    return self.schema(action="final", answer="The answer is 1000.")
                    
                if "Calculate 15% of 850." in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "850 * 0.15"})
                    return self.schema(action="final", answer="It is 127.5.")
                    
                if "What is 1024 divided by 8?" in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1024 / 8"})
                    return self.schema(action="final", answer="The answer is 128.")

                # Search -> Calculator
                if "Find India's population and calculate 5% of it." in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "India population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1400000000 * 0.05"})
                    return self.schema(action="final", answer="70 million.")
                        
                if "Search for the price of 1 Bitcoin in USD and multiply it by 3." in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "1 Bitcoin in USD price"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "60000 * 3"})
                    return self.schema(action="final", answer="The answer is 180000.")
                    
                if "Find the population of Tokyo and divide it by 10." in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Tokyo population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "14000000 / 10"})
                    return self.schema(action="final", answer="1400000.")

                # Search -> Search -> Compare
                if "Find the populations of India and China and compare them." in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "India population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "China population"})
                    return self.schema(action="final", answer="India has slightly more people.")

                # RAG -> Calculator
                if "According to the company policy, what is the hardware reimbursement limit and what would 3 employees receive in total?" in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1000 * 3"})
                    return self.schema(action="final", answer="3000.")

                if "How many PTO days do we get, and what is that divided by 12?" in query:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "20 / 12"})
                    return self.schema(action="final", answer="1.66")

                # Fallback
                if tool_results_count == 0:
                    if hash(query) % 2 == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "search"})
                    else:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1+1"})
                else:
                    return self.schema(action="final", answer="Task complete.")

        return StructuredMock(self)


    def invoke(self, messages, **kwargs):
        self.call_count += 1
        
        # Planner prompt (for retrieval planner)
        if isinstance(messages, str) or (isinstance(messages, list) and isinstance(messages[0].content, str) and "You are a retrieval planner" in messages[0].content):
            query = messages if isinstance(messages, str) else messages[-1].content
            if "Question: " in query:
                query = query.split("Question: ")[-1]
            query = query.lower()
            if "policy" in query or "document" in query or "budget" in query or "days" in query:
                return AIMessage(content='```json\n{"rag": true, "profile": false, "semantic": false}\n```')
            if "my name" in query or "who am i" in query:
                return AIMessage(content='```json\n{"rag": false, "profile": true, "semantic": false}\n```')
            return AIMessage(content='```json\n{"rag": false, "profile": false, "semantic": false}\n```')
            
        return AIMessage(content="Final")
