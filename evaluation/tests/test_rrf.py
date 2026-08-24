import unittest
from nodes.rrf import reciprocal_rank_fusion

class DummyDoc:
    def __init__(self, chunk_id):
        self.metadata = {"chunk_id": chunk_id}
        self.page_content = f"content {chunk_id}"

class TestRRF(unittest.TestCase):
    def test_ranking(self):
        faiss = [DummyDoc(1), DummyDoc(2), DummyDoc(3)]
        bm25 = [DummyDoc(2), DummyDoc(3), DummyDoc(4)]
        
        # RRF(k=60)
        # Doc 1: 1/(60+1) from faiss = 0.01639
        # Doc 2: 1/(60+2) from faiss + 1/(60+1) from bm25 = 0.01612 + 0.01639 = 0.0325
        # Doc 3: 1/(60+3) from faiss + 1/(60+2) from bm25 = 0.01587 + 0.01612 = 0.0319
        # Doc 4: 1/(60+3) from bm25 = 0.01587
        
        results = reciprocal_rank_fusion(faiss, bm25, k=60)
        
        # Expected order: 2, 3, 1, 4
        self.assertEqual(results[0]["doc"].metadata["chunk_id"], 2)
        self.assertEqual(results[1]["doc"].metadata["chunk_id"], 3)
        self.assertEqual(results[2]["doc"].metadata["chunk_id"], 1)
        self.assertEqual(results[3]["doc"].metadata["chunk_id"], 4)
        
    def test_empty(self):
        self.assertEqual(reciprocal_rank_fusion([], []), [])
        
    def test_one_sided(self):
        faiss = [DummyDoc(1)]
        results = reciprocal_rank_fusion(faiss, [], k=60)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["doc"].metadata["chunk_id"], 1)

if __name__ == "__main__":
    unittest.main()
