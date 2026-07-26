# Hybrid RAG Pipeline

The RAG retrieval system uses a **3-stage hybrid pipeline** combining semantic search (FAISS), keyword search (BM25), and cross-encoder reranking for maximum precision and recall.

```
                   User Question
                         │
                  Query Rewriter
             (LLM rewrites query)
                         │
               Hybrid Retrieval
             ┌────────┴────────┐
             │                 │
          FAISS              BM25
     (semantic search)   (keyword search)
      k=20, score<=0.8     k=20 always
             │                 │
             └────────┬────────┘
                      │
                Merge by chunk_id
                      │
             Similarity Filtering
            (drop FAISS score > 0.8)
                      │
             Top 20 Candidates
                      │
          Cross-Encoder Reranker
    (cross-encoder/ms-marco-MiniLM-L6-v2)
                      │
               Top 5 Documents
                      │
              Context Builder
                      │
                     LLM Agent
```

## Pipeline Stages

### 1. Query Rewriting
The user's raw question is rewritten into a concise, optimized search query using a `ChatPromptTemplate` + LLM. This improves retrieval quality by expanding synonyms and removing unnecessary words.

### 2. Dual Retrieval
- **FAISS** — Performs semantic similarity search using HuggingFace `all-MiniLM-L6-v2` embeddings. Returns top 20 results with cosine distance scores. Results with score > 0.8 are filtered out.
- **BM25** — Performs keyword-based search using `rank-bm25` library. Returns top 20 results. BM25 results are always included regardless of score.

Both result sets are merged by `chunk_id` to eliminate duplicates.

### 3. Cross-Encoder Reranking
Up to 20 merged candidates are re-ranked using the `cross-encoder/ms-marco-MiniLM-L6-v2` model. This cross-attention model computes more accurate relevance scores than embedding similarity alone. The top 5 most relevant documents are returned to the agent.

## Key Files

| File | Purpose |
|------|---------|
| `nodes/rag_retriever.py` | Main RAG retriever node orchestrating the pipeline |
| `nodes/bm25.py` | BM25 keyword search (lazy-loaded from `bm25_chunks.pkl`) |
| `reranker.py` | Cross-encoder reranking model wrapper |
| `ingest.py` | Document ingestion: .txt → chunks → FAISS index + BM25 pickle |

## Usage

1. Place `.txt` documents in `documents/` directory
2. Run `python ingest.py` to build the indices
3. Ask questions referencing company policies or documents
