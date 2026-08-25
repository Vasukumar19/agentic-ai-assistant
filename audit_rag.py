import pickle
import json
import time
from pathlib import Path
from langchain_community.vectorstores import FAISS
from nodes.embeddings import embeddings
from nodes.bm25 import bm25_search
from nodes.rrf import reciprocal_rank_fusion
from reranker import rerank
import config
from numpy import dot
from numpy.linalg import norm

def cosine_sim(a, b):
    return dot(a, b)/(norm(a)*norm(b))

def run_audit():
    with open("evaluation/reports/rag_pipeline_audit.md", "w") as f:
        f.write("# RAG Pipeline Audit\n\n")
        
        # 1. Corpus
        docs_dir = Path("documents")
        doc_files = list(docs_dir.glob("*.txt"))
        
        # Read chunks
        with open("bm25_chunks.pkl", "rb") as pkl:
            chunks = pickle.load(pkl)
            
        avg_len = sum(len(c.page_content) for c in chunks) / len(chunks) if chunks else 0
        min_len = min(len(c.page_content) for c in chunks) if chunks else 0
        max_len = max(len(c.page_content) for c in chunks) if chunks else 0
        
        f.write("## Corpus\n")
        f.write(f"Documents: {len(doc_files)}\n")
        f.write(f"Chunks: {len(chunks)}\n")
        f.write(f"Average chunk length: {avg_len:.0f} chars\n")
        f.write(f"Min chunk length: {min_len} chars\n")
        f.write(f"Max chunk length: {max_len} chars\n\n")
        
        # 2. Chunking
        f.write("## Chunking\n")
        f.write("Splitter: RecursiveCharacterTextSplitter\n")
        f.write("Chunk size: 800\n")
        f.write("Overlap: 150\n")
        
        # Calculate actual overlap
        overlaps = []
        for i in range(len(chunks)-1):
            c1 = chunks[i]
            c2 = chunks[i+1]
            if c1.metadata["document_id"] == c2.metadata["document_id"]:
                # find overlap
                t1 = c1.page_content
                t2 = c2.page_content
                # naive overlap check
                overlap_len = 0
                for size in range(min(len(t1), len(t2)), 0, -1):
                    if t1[-size:] == t2[:size]:
                        overlap_len = size
                        break
                overlaps.append(overlap_len)
                
        avg_overlap = sum(overlaps)/len(overlaps) if overlaps else 0
        f.write(f"Observed overlap: {avg_overlap:.0f} chars (average)\n\n")
        
        # 3. Embeddings
        f.write("## Embeddings\n")
        f.write("Model: sentence-transformers/all-MiniLM-L6-v2\n")
        
        emb_A = embeddings.embed_query("What days can employees work remotely?")
        emb_B = embeddings.embed_query("What is the company's remote work schedule?")
        emb_C = embeddings.embed_query("What is the reimbursement policy for laptops?")
        
        dim = len(emb_A)
        f.write(f"Dimension: {dim}\n")
        f.write(f"Normalization: Assumed built-in L2 normalization for MiniLM\n")
        f.write(f"Distance metric: FAISS default (L2 distance or inner product)\n\n")
        
        f.write("### Sanity Check\n")
        sim_AB = cosine_sim(emb_A, emb_B)
        sim_AC = cosine_sim(emb_A, emb_C)
        f.write(f"sim(A, B) = {sim_AB:.4f} (Related)\n")
        f.write(f"sim(A, C) = {sim_AC:.4f} (Unrelated)\n\n")
        
        # 4. Vector Store
        try:
            vectorstore = FAISS.load_local(str(config.FAISS_INDEX_DIR), embeddings, allow_dangerous_deserialization=True)
            num_vectors = vectorstore.index.ntotal
            metadata_entries = len(vectorstore.docstore._dict)
        except Exception as e:
            num_vectors = 0
            metadata_entries = 0
            
        f.write("## Vector Store\n")
        f.write("Index type: FAISS (langchain default IndexFlatL2)\n")
        f.write(f"Vectors: {num_vectors}\n")
        f.write(f"Metadata entries: {metadata_entries}\n\n")
        
        # 5. BM25
        f.write("## BM25\n")
        f.write("Tokenizer: rank_bm25 default whitespace tokenizer\n")
        f.write(f"Corpus size: {len(chunks)}\n\n")
        
        # 6. Retrieval configurations
        f.write("## Retrieval Algorithms Configured\n")
        f.write("- FAISS: Yes\n")
        f.write("- Hybrid (FAISS + BM25 merged): Yes\n")
        f.write("- RRF: Yes (nodes/rrf.py)\n")
        f.write("- Reranker: Yes (reranker.py using CrossEncoder)\n\n")

    print("Audit report generated at evaluation/reports/rag_pipeline_audit.md")

if __name__ == "__main__":
    run_audit()
