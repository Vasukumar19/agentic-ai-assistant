==================================================
AGENT BASELINE EVALUATION
==================================================

Dataset:
  50 test cases

Routing Accuracy:
  98.0%

Tool Selection Accuracy:
  50.0%

Recall@1:
  20.0%

Recall@5:
  20.0%

MRR:
  0.200

Context Keyword Coverage:
  17.8%

Answer Accuracy:
  100.0%

Faithfulness:
  55.6%

Tool Success Rate:
  100.0%

Retrieval Latency:
  0.01 s

Reranker Latency:
  0.00 s

Average Total Latency:
  7.16 s

Median Total Latency:
  5.44 s

P95 Total Latency:
  18.51 s

Average LLM Calls:
  1.1

Average Tokens:
  0

Estimated Cost / Query:
  $0.0000
==================================================

## Failure Analysis
- routing_failure: 1 (2.0%)
- retrieval_failure: 13 (26.0%)
- tool_selection_failure: 10 (20.0%)

## Slowest Cases
- multi_step_048: 34.45s
- web_search_044: 24.20s
- multi_step_049: 18.51s
- multi_step_046: 17.03s
- rag_030: 15.52s
