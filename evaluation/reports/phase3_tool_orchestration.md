# Phase 3 Tool Orchestration Report

Generated: 2026-08-25T10:01:31Z
Model: gemini-3.6-flash

## MOCK RESULTS (Deterministic, No API Calls)

These results were produced using a deterministic Mock LLM to validate the orchestration infrastructure logic only.
They do **NOT** represent real LLM capability.

| Metric | ReAct (Mock) | Planner (Mock) | Δ |
|---|---:|---:|---:|
| Tool Selection Accuracy | 24.0% | 44.0% | +20.0pp |
| Sequence Accuracy | 20.0% | 40.0% | +20.0pp |
| Multi-Step Completion | 20.0% | 40.0% | +20.0pp |
| Avg Latency | 0.84s | 1.56s | +0.72s |

> **Note:** Mock deltas reflect improved orchestration logic, not real LLM reasoning quality.

---

## REAL LLM VALIDATION

- **Dataset**: `evaluation/datasets/phase3_live_10.json` (10 cases)
- **Cases attempted**: 10
- **Cases completed**: 10
- **Cases rate-limited**: 0

### Before/After Comparison (Real LLM)

| Metric | ReAct (Real) | Planner (Real) | Δ |
|---|---:|---:|---:|
| Tool Selection Accuracy | not run | 90.0% | N/A |
| Sequence Accuracy | not run | 70.0% | N/A |
| Multi-Step Completion | not run | 57.1% | N/A |
| Missing Tool Rate | not run | 0.0% | N/A |
| Wrong Tool Rate | not run | 20.0% | N/A |
| Premature Stop Rate | not run | 10.0% | N/A |
| Unnecessary Tool Rate | not run | 0.0% | N/A |
| Arg Accuracy | not run | 100.0% | N/A |
| Dep Accuracy | not run | 81.5% | N/A |
| Tool Success Rate | not run | 70.0% | N/A |
| Avg LLM Calls | not run | 2.3 | N/A |
| Avg Tool Calls | not run | 1.4 | N/A |
| Mean Latency (s) | not run | 4.99 | N/A |
| P50 Latency (s) | not run | 4.49 | N/A |
| P95 Latency (s) | not run | 8.98 | N/A |

### Per-Case Trace

| ID | Category | Expected | Actual | Status | Failure | Latency | LLM Calls |
|---|---|---|---|---|---|---:|---:|
| live_001 | single_tool_calc | calculator | calculator | completed | ✅ pass | 3.70s | 2 |
| live_002 | single_tool_search | web_search | web_search | completed | ✅ pass | 3.29s | 2 |
| live_003 | search_then_calc | web_search, calculator | web_search, calculator | completed | ✅ pass | 5.86s | 3 |
| live_004 | search_then_calc | web_search, calculator | web_search, calculator | completed | ✅ pass | 5.00s | 3 |
| live_005 | rag_then_calc | rag, calculator | rag, calculator | completed | ✅ pass | 3.98s | 2 |
| live_006 | rag_then_calc | rag, calculator | rag, calculator | completed | ✅ pass | 3.07s | 2 |
| live_007 | multi_search_compare | web_search, web_search, calculator | web_search, web_search | completed | premature_stop | 8.98s | 3 |
| live_008 | multi_search_compare | web_search, web_search, calculator | web_search, calculator | completed | wrong_tool | 7.14s | 3 |
| live_009 | memory_tool |  |  | completed | ✅ pass | 1.52s | 0 |
| live_010 | complex_multistep | web_search, web_search, calculator | web_search, calculator | completed | wrong_tool | 7.35s | 3 |

### Failure Analysis

**live_007** — premature_stop
- Query: Find the population of Brazil and the population of Argentina. Which one is larger and by how much?
- Expected: `['web_search', 'web_search', 'calculator']`
- Actual: `['web_search', 'web_search']`
- Tool calls:
  - `web_search({'query': 'population of Brazil'})` → `Brazil had an official resident population of 203 million in 2022, according to the Brazilian Institute of Geography and`
  - `web_search({'query': 'population of Argentina'})` → `Demographics of Argentina ... This is a demography of Argentina including population density, ethnicity, economic status`

**live_008** — wrong_tool
- Query: What is the current price of gold per ounce and the current price of silver per ounce? What is the gold-to-silver price ratio?
- Expected: `['web_search', 'web_search', 'calculator']`
- Actual: `['web_search', 'calculator']`
- Tool calls:
  - `web_search({'query': 'current price of gold per ounce and current price of silver per ounce'})` → `Live Price of Gold provides up-to-date live gold prices in multiple currencies for all countries, available 24/7. You ca`
  - `calculator({'expression': 'gold_price / silver_price'})` → `Error: ('NameError', "gold_price / silver_price\nNameError: name 'gold_price' is not defined")`

**live_010** — wrong_tool
- Query: Find the GDP of India and the GDP of Pakistan. Calculate the ratio of India's GDP to Pakistan's GDP and tell me how many times larger India's economy is.
- Expected: `['web_search', 'web_search', 'calculator']`
- Actual: `['web_search', 'calculator']`
- Tool calls:
  - `web_search({'query': 'GDP of India and GDP of Pakistan'})` → `Gross domestic product (GDP) is the market value of all final goods and services from a nation in a given year. [2] Coun`
  - `calculator({'expression': '3.96 / 0.407'})` → `9.72972972972973`

### Latency Overhead Analysis

The Planner architecture issues **one structured LLM call per tool step** plus a final call, versus the ReAct loop which used one call per reasoning round. This typically results in N+1 LLM calls for an N-tool task.

Observed mean latency: **4.99s** with avg **2.3** LLM calls per query.
