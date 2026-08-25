"""
Document Ingestion Pipeline
===========================

Loads documents, splits them into chunks, enriches metadata,
builds a FAISS index, and stores chunks for BM25 retrieval.
"""

import pickle
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent / "nodes"))

from embeddings import embeddings


from config import FAISS_INDEX_DIR


# -------------------------
# Configuration
# -------------------------

DOCS_DIR = Path("documents")
CHUNKS_FILE = Path("bm25_chunks.pkl")

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def ingest_documents():

    print(f"Starting ingestion from {DOCS_DIR}...\n")

    if not DOCS_DIR.exists():
        print(f"Directory not found: {DOCS_DIR}")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        length_function=len,
    )

    all_chunks = []

    # -------------------------
    # Process each document independently
    # -------------------------

    for file_path in sorted(DOCS_DIR.glob("*.txt")):

        print(f"Loading {file_path.name}")

        loader = TextLoader(
            str(file_path),
            encoding="utf-8",
        )

        docs = loader.load()

        chunks = splitter.split_documents(docs)

        total_chunks = len(chunks)

        for idx, chunk in enumerate(chunks):

            chunk.metadata.update(
                {
                    "document_id": file_path.stem,
                    "source": str(file_path),
                    "chunk_id": f"{file_path.stem}_chunk_{idx:03d}", # deterministic id
                    "chunk_number": idx,                # within document
                    "total_chunks": total_chunks,
                    "prev_chunk": idx - 1 if idx > 0 else None,
                    "next_chunk": idx + 1 if idx < total_chunks - 1 else None,
                    "length": len(chunk.page_content),
                    "embedding_model": EMBEDDING_MODEL,
                }
            )

            all_chunks.append(chunk)

        print(f"  -> {total_chunks} chunks created")

    if not all_chunks:
        print("\nNo documents found.")
        return

    # -------------------------
    # Statistics
    # -------------------------

    avg_length = (
        sum(len(chunk.page_content) for chunk in all_chunks)
        / len(all_chunks)
    )

    print("\n========== Ingestion Summary ==========")
    print(f"Documents       : {len(list(DOCS_DIR.glob('*.txt')))}")
    print(f"Total Chunks    : {len(all_chunks)}")
    print(f"Average Length  : {avg_length:.0f} characters")
    print("=======================================\n")

    # -------------------------
    # Build FAISS
    # -------------------------

    print("Building FAISS index...")

    vectorstore = FAISS.from_documents(
        all_chunks,
        embeddings,
    )

    FAISS_INDEX_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    vectorstore.save_local(str(FAISS_INDEX_DIR))

    print("FAISS index saved.")

    # -------------------------
    # Save chunks for BM25
    # -------------------------

    with open(CHUNKS_FILE, "wb") as f:
        pickle.dump(all_chunks, f)

    print(f"BM25 chunks saved -> {CHUNKS_FILE}")

    print("\nIngestion completed successfully.")


if __name__ == "__main__":
    ingest_documents()