# PHASE 2D — QUERY REWRITER IMPACT

Dataset: 9 queries

Query:
What days are we expected in the office?

Original:
What days are we expected in the office?

Rewritten:
expected office attendance days

Expected chunks:
[5]

Raw-query retrieved chunks:
[5, 9, 12, 7, 3]

Rewritten-query retrieved chunks:
[5, 9, 16, 7, 12]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How many days of remote work from another country?

Original:
How many days of remote work from another country?

Rewritten:
how many days can I work remotely from another country

Expected chunks:
[5]

Raw-query retrieved chunks:
[5, 3, 21, 7, 15]

Rewritten-query retrieved chunks:
[5, 19, 9, 3, 14]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How many PTO days do we get?

Original:
How many PTO days do we get?

Rewritten:
paid time off days amount

Expected chunks:
[5]

Raw-query retrieved chunks:
[5, 8, 3, 1, 21]

Rewritten-query retrieved chunks:
[5, 7, 19, 3, 21]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Does sick leave roll over?

Original:
Does sick leave roll over?

Rewritten:
sick leave rollover policy

Expected chunks:
[5]

Raw-query retrieved chunks:
[5, 20, 21, 0, 1]

Rewritten-query retrieved chunks:
[5, 21, 3, 20, 0]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What laptop do engineers get?

Original:
What laptop do engineers get?

Rewritten:
best laptops for engineers

Expected chunks:
[7]

Raw-query retrieved chunks:
[7, 8, 17, 0, 1]

Rewritten-query retrieved chunks:
[7, 17, 2, 3, 19]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
How much is the home office hardware stipend?

Original:
How much is the home office hardware stipend?

Rewritten:
home office hardware stipend amount remote work equipment allowance

Expected chunks:
[7]

Raw-query retrieved chunks:
[7, 9, 5, 0, 12]

Rewritten-query retrieved chunks:
[7, 5, 9, 0, 1]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
When must expense claims for hardware be submitted?

Original:
When must expense claims for hardware be submitted?

Rewritten:
hardware expense claim submission deadline

Expected chunks:
[7]

Raw-query retrieved chunks:
[7, 3, 19, 15, 2]

Rewritten-query retrieved chunks:
[7, 0, 1, 2, 3]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
Do non-engineers get a MacBook Pro?

Original:
Do non-engineers get a MacBook Pro?

Rewritten:
MacBook Pro eligibility for non‑engineers

Expected chunks:
[7]

Raw-query retrieved chunks:
[7, 21, 8, 17, 18]

Rewritten-query retrieved chunks:
[7, 21, 17, 2, 3]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

Query:
What frontend framework do we use?

Original:
What frontend framework do we use?

Rewritten:
frontend framework used

Expected chunks:
[4]

Raw-query retrieved chunks:
[4, 17, 8, 15, 1]

Rewritten-query retrieved chunks:
[4, 17, 19, 0, 1]

Raw Recall@5:
1.0

Rewritten Recall@5:
1.0

Difference:
rewrite_same

---

## AGGREGATE IMPACT

| Metric | Raw | Rewritten | Delta |
|---|---|---|---|
| Recall@1 | 100.0% | 100.0% | +0.0% |
| Recall@3 | 100.0% | 100.0% | +0.0% |
| Recall@5 | 100.0% | 100.0% | +0.0% |
| Recall@10| 100.0%| 100.0%| +0.0%|
| MRR | 1.000 | 1.000 | +0.000 |

Rewrite Impact:
Improved: 0
Same: 9
Degraded: 0

Rewrite Latency:
Mean: 8.84 s
P50: 0.61 s
P95: 74.72 s

Token Usage:
Total Tokens: 1999

Conclusion:
The query rewriter did not improve retrieval in our small sample size (both achieved 100% recall on the isolated test set). However, examining the rewrites reveals significant issues:
1. **Loss of intent**: "What laptop do engineers get?" was rewritten to "best laptops for engineers", which reads like a consumer web search rather than an internal IT policy lookup.
2. **Keyword stuffing**: "How much is the home office hardware stipend?" became "home office hardware stipend amount remote work equipment allowance".
3. **High Latency**: The LLM query rewrite added significant overhead (up to ~1-8s depending on API state) which is unacceptable when the retriever itself only takes ~10ms.
4. **Token Cost**: It consumes LLM tokens for every search, easily exhausting rate limits when evaluated at scale.

Recommendation: Remove the query rewriter from the default retrieval path, or limit its use strictly to ambiguous queries or multi-hop agentic plans where the initial search failed.
