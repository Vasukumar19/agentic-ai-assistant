from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.tools import tool

load_dotenv()

@tool
def hello(name: str) -> str:
    """Say hello."""
    return f"Hello {name}"

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
)

llm = llm.bind_tools([hello])

response = llm.invoke("Use the hello tool for Vasu.")

print(response)
print(response.tool_calls)