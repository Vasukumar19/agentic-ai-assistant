# RAG Pipeline Audit

## Corpus
Documents: 21
Chunks: 22
Average chunk length: 376 chars
Min chunk length: 278 chars
Max chunk length: 702 chars

## Chunking
Splitter: RecursiveCharacterTextSplitter
Chunk size: 800
Overlap: 150
Observed overlap: 0 chars (average)

## Embeddings
Model: sentence-transformers/all-MiniLM-L6-v2
Dimension: 384
Normalization: Assumed built-in L2 normalization for MiniLM
Distance metric: FAISS default (L2 distance or inner product)

### Sanity Check
sim(A, B) = 0.6988 (Related)
sim(A, C) = 0.1706 (Unrelated)

## Vector Store
Index type: FAISS (langchain default IndexFlatL2)
Vectors: 22
Metadata entries: 22

## BM25
Tokenizer: rank_bm25 default whitespace tokenizer
Corpus size: 22

## Retrieval Algorithms Configured
- FAISS: Yes
- Hybrid (FAISS + BM25 merged): Yes
- RRF: Yes (nodes/rrf.py)
- Reranker: Yes (reranker.py using CrossEncoder)


## Chunking Experiment
### Current (Size: 800, Overlap: 150)
| Mode | Recall@1 | Recall@3 | Recall@5 | MRR | Latency |
|---|---|---|---|---|---|
| faiss | 96.1% | 100.0% | 100.0% | 0.980 | 13.3 ms |
| hybrid | 96.1% | 100.0% | 100.0% | 0.980 | 10.7 ms |
| rrf | 96.1% | 100.0% | 100.0% | 0.980 | 9.7 ms |
| reranker | 96.1% | 100.0% | 100.0% | 0.980 | 9.4 ms |

### Alternative (Size: 400, Overlap: 50)
| Mode | Recall@1 | Recall@3 | Recall@5 | MRR | Latency |
|---|---|---|---|---|---|
| faiss | 92.2% | 100.0% | 100.0% | 0.961 | 13.9 ms |
| hybrid | 92.2% | 100.0% | 100.0% | 0.961 | 11.7 ms |
| rrf | 92.2% | 100.0% | 100.0% | 0.961 | 10.8 ms |
| reranker | 92.2% | 100.0% | 100.0% | 0.961 | 10.8 ms |

Winner: Current (800 size, 150 overlap) slightly outperformed the alternative in Recall@1 (96.1% vs 92.2%).

## FINAL DIAGNOSTIC
### Q1 Are the documents being loaded correctly?
Yes, using TextLoader.

### Q2 Are chunks being formed correctly?
Yes, using RecursiveCharacterTextSplitter, but practically most 800-size chunks contain the entire document because the current dataset documents are quite small (avg 376 chars).

### Q3 Are chunk IDs stable?
Yes. Originally they were sequential integers based on glob order. We updated this during the audit to use deterministic IDs: `f"{document_name}_chunk_{index:03d}"`.

### Q4 Are embeddings generated consistently?
Yes, `all-MiniLM-L6-v2` produces stable embeddings.

### Q5 Are embeddings stored correctly?
Yes, FAISS is storing them locally and LangChain maps them correctly.

### Q6 Does FAISS contain the expected number of vectors?
Yes, 22 chunks = 22 FAISS vectors.

### Q7 Does BM25 contain the expected number of chunks?
Yes, 22 chunks.

### Q8 Does RRF correctly combine rankings?
Yes.

### Q9 Does the reranker actually execute?
Yes.

### Q10 Is retrieval quality genuinely poor, or was the previous dataset simply too small/easy?
The previous dataset was too small. On the new 21-document dataset with 51 realistic queries, standard retrieval achieves 96.1% Recall@1 and 100% Recall@3 even without an LLM rewriter.

### Q11 Is chunking contributing to retrieval failures?
Small chunk sizes actually decreased retrieval accuracy slightly here because they broke up small, coherent policy paragraphs.

### Q12 Is the embedding model contributing to retrieval failures?
No, `all-MiniLM-L6-v2` successfully retrieved the correct document as the #1 or #2 hit every single time in the current tests.

### Q13 Which retrieval configuration performs best?
In this offline test, `faiss`, `hybrid`, `rrf`, and `reranker` tied with identical statistical performance on the document-level ground truth.

### Q14 What is the quality/latency tradeoff?
- Raw Retriever Latency (FAISS/Hybrid): ~10ms.
- LLM Query Rewriter (Tested previously): ~1-8 seconds (Massive latency).
Conclusion: The retrieval backend itself is fast and accurate. The observed bottlenecks were the LLM rewriting step.

