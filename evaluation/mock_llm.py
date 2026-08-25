import re
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable

class MockLLM(Runnable):
    def __init__(self):
        self.call_count = 0

    def bind_tools(self, tools, **kwargs):
        return self
        
    def with_structured_output(self, schema, **kwargs):
        class StructuredMock(Runnable):
            def __init__(self, parent):
                self.parent = parent
                self.schema = schema
                
            def invoke(self, messages, **kwargs):
                self.parent.call_count += 1
                
                query = ""
                context = ""
                tool_results_count = 0
                for m in messages:
                    if m.type == "human":
                        if "User Query:" in m.content:
                            query = m.content.split("User Query: ")[-1].strip()
                        if "RETRIEVED CONTEXT:" in m.content:
                            context = m.content.split("RETRIEVED CONTEXT:")[1].split("User Query:")[0].strip()
                        if "PREVIOUS TOOL EXECUTIONS" in m.content:
                            tool_results_count = m.content.count("Step ")
                
                q_lower = query.lower()

                # --- 1. Pure Arithmetic / Math ---
                if "128 divided by 8" in q_lower or "128 / 8" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "128 / 8"})
                    return self.schema(action="final", answer="16.0")

                if "25 * 40" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "25 * 40"})
                    return self.schema(action="final", answer="1000")

                if "15% of 850" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "850 * 0.15"})
                    return self.schema(action="final", answer="127.5")

                if "1024 divided by 8" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1024 / 8"})
                    return self.schema(action="final", answer="128")

                if "square root of 144" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "144 ** 0.5"})
                    return self.schema(action="final", answer="12")

                if "subtract 45 from 200" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "200 - 45"})
                    return self.schema(action="final", answer="155")

                # --- 2. Pure Factual / Search ---
                if "ceo of microsoft" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "current CEO of Microsoft"})
                    return self.schema(action="final", answer="Satya Nadella is the CEO of Microsoft.")

                if "ceo of tesla" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "current CEO of Tesla"})
                    return self.schema(action="final", answer="Elon Musk is the CEO of Tesla.")

                if "stock price of apple" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Apple stock price"})
                    return self.schema(action="final", answer="Apple stock price is $220.")

                if "capital of france" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "capital of France"})
                    return self.schema(action="final", answer="The capital of France is Paris.")

                # --- 3. Pure RAG Lookups (No Math) ---
                if ("remote work policy" in q_lower or "health insurance" in q_lower or "database technology" in q_lower or "annual hardware reimbursement limit" in q_lower) and "calculate" not in q_lower and "multiply" not in q_lower and "divide" not in q_lower:
                    return self.schema(action="final", answer="Based on the documents, the requested policy info is confirmed.")

                # --- 4. Search -> Calculator Multi-Step ---
                if "population of japan and calculate" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "current population of Japan"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "125000000 * 0.005"})
                    return self.schema(action="final", answer="0.5% of Japan's population is 625,000.")

                if "india's population and calculate 5%" in q_lower or ("population of india" in q_lower and "calculate" in q_lower):
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "current population of India"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1400000000 * 0.05"})
                    return self.schema(action="final", answer="70 million.")

                if "speed of light" in q_lower and ("multiply" in q_lower or "60" in q_lower):
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "speed of light in km/s"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "300000 * 60"})
                    return self.schema(action="final", answer="Light travels 18,000,000 km in one minute.")

                if "gdp of germany" in q_lower and "1%" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "GDP of Germany"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "4500000000000 * 0.01"})
                    return self.schema(action="final", answer="1% of Germany's GDP is $45 billion.")

                if "price of 1 bitcoin" in q_lower and "multiply" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "1 Bitcoin price in USD"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "65000 * 3"})
                    return self.schema(action="final", answer="The price for 3 Bitcoin is $195,000.")

                if "population of tokyo" in q_lower and "divide" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Tokyo population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "14000000 / 10"})
                    return self.schema(action="final", answer="1,400,000.")

                if "height of mount everest" in q_lower and "divide" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Mount Everest height in meters"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "8848.86 / 2"})
                    return self.schema(action="final", answer="4424.43 meters.")

                # --- 5. RAG -> Calculator Multi-Step ---
                if "pto days" in q_lower and ("5 days off" in q_lower or "left" in q_lower or "divide" in q_lower):
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "20 - 5"})
                    return self.schema(action="final", answer="You will have 15 PTO days left.")

                if "training budget" in q_lower and ("multiply" in q_lower or "team of 5" in q_lower):
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1500 * 5"})
                    return self.schema(action="final", answer="Total budget for 5 employees is $7,500.")

                if "hardware reimbursement limit" in q_lower and ("3 employees" in q_lower or "total" in q_lower):
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1000 * 3"})
                    return self.schema(action="final", answer="Total reimbursement is $3,000.")

                if "wellness stipend" in q_lower and "25%" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "500 * 0.25"})
                    return self.schema(action="final", answer="25% of the wellness stipend is $125.")

                # --- 6. Multi-Search & Multi-Step Comparisons ---
                if "population of brazil and" in q_lower and "argentina" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Brazil population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Argentina population"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "214000000 - 46000000"})
                    return self.schema(action="final", answer="Brazil is larger by 168 million people.")

                if "price of gold" in q_lower and "price of silver" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "gold price per ounce"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "silver price per ounce"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "2400 / 30"})
                    return self.schema(action="final", answer="The gold-to-silver price ratio is 80:1.")

                if "gdp of india" in q_lower and "gdp of pakistan" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "India GDP"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Pakistan GDP"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "3750000000000 / 375000000000"})
                    return self.schema(action="final", answer="India's economy is approximately 10 times larger.")

                if "tallest building in new york" in q_lower and "dubai" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "tallest building in New York height"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "tallest building in Dubai height"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "828 - 541"})
                    return self.schema(action="final", answer="Burj Khalifa is taller by 287 meters.")

                if "populations of india and china" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "India population"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "China population"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1428000000 - 1425000000"})
                    if tool_results_count == 3:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "3000000 * 0.10"})
                    return self.schema(action="final", answer="10% of the difference is 300,000.")

                if "macbook pro" in q_lower and "laptop budget" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "MacBook Pro retail price"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1000 - 1299"})
                    return self.schema(action="final", answer="The MacBook Pro is $299 over budget.")

                if "aws solutions architect exam" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "AWS Solutions Architect exam cost"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1500 - 150"})
                    return self.schema(action="final", answer="Remaining budget is $1350.")

                if "frontend framework" in q_lower and "latest release" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "React latest release version"})
                    return self.schema(action="final", answer="The latest release is React 19.")

                if "ceo of our company" in q_lower and "latest news" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "CEO latest news"})
                    return self.schema(action="final", answer="The CEO recently announced new initiatives.")

                if "distance from earth to mars" in q_lower:
                    if tool_results_count == 0:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Earth to Mars distance in km"})
                    if tool_results_count == 1:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "Earth to Venus distance in km"})
                    if tool_results_count == 2:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "225000000 - 41000000"})
                    return self.schema(action="final", answer="The difference is 184,000,000 km.")

                # Fallback
                if tool_results_count == 0:
                    if "calculate" in q_lower or "divided" in q_lower or "multiply" in q_lower:
                        return self.schema(action="tool", tool="calculator", arguments={"expression": "1+1"})
                    elif "search" in q_lower or "who is" in q_lower:
                        return self.schema(action="tool", tool="web_search", arguments={"query": "search query"})
                    else:
                        return self.schema(action="final", answer="Task complete.")
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
            if "policy" in query or "document" in query or "budget" in query or "days" in query or "internal doc" in query or "benefits" in query or "stipend" in query:
                return AIMessage(content='```json\n{"rag": true, "profile": false, "semantic": false}\n```')
            if "my name" in query or "who am i" in query:
                return AIMessage(content='```json\n{"rag": false, "profile": true, "semantic": false}\n```')
            return AIMessage(content='```json\n{"rag": false, "profile": false, "semantic": false}\n```')
            
        return AIMessage(content="Final")
