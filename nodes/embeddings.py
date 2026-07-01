"""
Embeddings Singleton
====================

Singleton module for HuggingFace embeddings to prevent reloading the model on every call.
"""

from langchain_huggingface import HuggingFaceEmbeddings

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={"device": "cpu"},
)
