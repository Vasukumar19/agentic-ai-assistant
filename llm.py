import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from config import MODEL_NAME, TEMPERATURE

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

llm = ChatGroq(
    model=MODEL_NAME,
    temperature=TEMPERATURE,
    groq_api_key=GROQ_API_KEY,
)
