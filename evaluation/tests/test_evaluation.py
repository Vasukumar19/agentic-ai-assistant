import unittest
from evaluation.metrics.deterministic import evaluate_routing, evaluate_context_coverage

class TestEvaluationMetrics(unittest.TestCase):
    def test_evaluate_routing(self):
        self.assertTrue(evaluate_routing("chat", "chat"))
        self.assertFalse(evaluate_routing("chat", "research_query"))
        self.assertIsNone(evaluate_routing(None, "chat"))
        
    def test_evaluate_context_coverage(self):
        self.assertEqual(evaluate_context_coverage(["apple", "banana"], "I like apples and bananas"), 1.0)
        self.assertEqual(evaluate_context_coverage(["apple", "banana"], "I like apples"), 0.5)
        self.assertEqual(evaluate_context_coverage(["apple", "banana"], "I like oranges"), 0.0)
        self.assertIsNone(evaluate_context_coverage(None, "I like apples"))

if __name__ == "__main__":
    unittest.main()
