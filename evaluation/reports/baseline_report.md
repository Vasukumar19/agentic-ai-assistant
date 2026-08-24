==================================================
AGENT BASELINE EVALUATION
==================================================

Dataset:
  50 test cases

Routing Accuracy:
  98.0%

Tool Selection Accuracy:
  50.0%

Context Keyword Coverage:
  11.1%

Answer Accuracy:
  100.0%

Faithfulness:
  100.0%

Tool Success Rate:
  100.0%

Average Latency:
  6.60 s

Median Latency:
  5.27 s

P95 Latency:
  19.18 s

Average LLM Calls:
  1.1

Average Tokens:
  0

Estimated Cost / Query:
  $0.0000
==================================================

## Failure Analysis
- routing_failure: 1 (2.0%)
- retrieval_failure: 14 (28.0%)
- tool_selection_failure: 10 (20.0%)

## Slowest Cases
- web_search_042: 34.25s
- multi_step_048: 25.26s
- calculator_031: 19.18s
- web_search_044: 18.78s
- multi_step_046: 17.35s
