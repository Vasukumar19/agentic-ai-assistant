import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

CHUNKS_FILE = Path("bm25_chunks.pkl")

documents = None
bm25 = None


def tokenize(text: str):
    return re.findall(r"\w+", text.lower())


def load_bm25():
    global documents, bm25

    # Already loaded
    if bm25 is not None:
        return

    if not CHUNKS_FILE.exists():
        raise FileNotFoundError(
            f"{CHUNKS_FILE} not found. Run 'python ingest.py' first."
        )

    with open(CHUNKS_FILE, "rb") as f:
        documents = pickle.load(f)

    tokenized_docs = [
        tokenize(doc.page_content)
        for doc in documents
    ]

    bm25 = BM25Okapi(tokenized_docs)


def bm25_search(query: str, k: int = 5):
    load_bm25()

    tokens = tokenize(query)

    scores = bm25.get_scores(tokens)

    ranked = sorted(
        enumerate(scores),
        key=lambda x: x[1],
        reverse=True
    )[:k]

    return [documents[idx] for idx, _ in ranked]