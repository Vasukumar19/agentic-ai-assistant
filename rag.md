                   User Question
                         │
                  Query Rewriter
                         │
               Hybrid Retrieval
             ┌────────┴────────┐
             │                 │
          FAISS              BM25
             │                 │
             └────────┬────────┘
                      │
                Merge by chunk_id
                      │
             Similarity Filtering
                      │
             Top 20 Candidates
                      │
          Cross-Encoder Reranker
                      │
               Top 5 Documents
                      │
              Context Builder
                      │
                     LLM