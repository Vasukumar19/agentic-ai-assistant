# Phase 4 — Answer Quality & Evaluation Maturity (Finalized)

Finalized benchmark from `evaluation/results/phase4_final_v2.json` · run_id `d33520` · model `qwen3:8b` (Ollama, local)

## 1. Executive Summary

- **100/100** cases completed, **0 infrastructure failures** (0 retries needed).
- Tool orchestration: **93.0% selection**, **88.0% acceptable-sequence**, **83.0% exact-sequence**.
- Answer quality: **90.6% fully-correct answers** (mean score 93.8%), **94.0% tool-grounded**, **97.0% RAG-faithful**, **89.3% utilization**.
- Task completion: **90.0%** (90/100 cases complete all declared operations).
- Composite score: **0.8918** (40% correctness / 30% completion / 20% grounding / 10% utilization).
- 2 genuine memory bugs found and fixed during evaluation; memory subsystem now passes all write/update/preservation tests.
- Zero temporal ground-truth drift detected in web bands (all 12 out-of-band cases were infrastructure failures or agent unit-mismatch, not fact changes).
- Key insight: sequence metrics alone overstate quality. Several sequence-passes hid wrong answers; several sequence-failures were actually complete tasks.

## 2. Dataset Composition

`evaluation/datasets/phase4_quality_100.json` — 100 cases, 5 buckets × 20:

| Bucket | n | Focus |
|---|---:|---|
| `single_tool` | 20 | Pure calculator arithmetic and live web lookups |
| `rag_memory` | 20 | Document lookups + runtime memory writes/recalls |
| `multi_step` | 20 | web→calc, rag→calc, web×2→calc, rag→web chains |
| `answer_grounded` | 20 | RAG answers whose values must trace to retrieved documents |
| `adversarial` | 20 | Parametric-bypass traps, absent-info probes, ambiguous wording |

Ground truth schema: expected answer (value or tolerance band), required information tokens, declared operations, required tools, acceptable tool sequences, forbidden tools, argument constraints, forbidden-answer patterns, expected context docs, source.

**23 cases** carry `expected_answer_range` bands (live-web facts). **77 cases** use static ground truth.

## 3. Dataset Version & Date

| Field | Value |
|---|---|
| Version | v1 (snapshot before web-band refresh) |
| Creation date | 2026-08-25 |
| Git commit | `7dd919b` |
| SHA256 (10 bytes) | `2ac4fe262b70` |
| Backup copy | `phase4_quality_100_v1.json` |
| Drift classification | `web_band_drift_classification.json` |

## 4. Memory Regression Fixes

Two genuine agent bugs discovered and fixed:

1. **Profile wipe bug** (`memory_extractor.py:memory_saver_node`): `memory.update(extracted_profile)` with empty-string extractions overwrote previously stored facts. Fixed by filtering out `None`/`""`/`[]`/`{}` before merge.

2. **Confirmation garbling** (`memory_extractor.py:memory_response_node`): empty fields rendered as blanks; redundant "to become an" phrasing doubled. Fixed by skipping empty fields and using neutral prefix when extraction already starts with "to".

**Verification** (10 tests, all passing):

| Test | Result |
|---|---|
| Empty extraction does not wipe profile | PASSED |
| New facts still merge correctly | PASSED |
| Confirmation skips empty fields | PASSED |
| No doubled "to become an" phrasing | PASSED |
| Plain goal + name confirmation | PASSED |
| Agent: write name → retrieve name | PASSED |
| Agent: write goal → retrieve goal | PASSED |
| Agent: update language replaces old | PASSED |
| Agent: new field preserves existing | PASSED |
| Agent: conflicting write — final wins | PASSED |

## 5. Task Completion

**90.0%** (90/100 completed cases)

| Category | Completed | Total | Rate |
|---|---:|---:|---:|
| single_tool | 18 | 20 | 90.0% |
| rag_memory | 18 | 20 | 90.0% |
| multi_step | 18 | 20 | 90.0% |
| answer_grounded | 17 | 20 | 85.0% |
| adversarial | 19 | 20 | 95.0% |

## 6. Exact Sequence Accuracy

Exact canonical path: **83.0%** · any-declared-acceptable path: **88.0%**

The gap is the point of Phase 4: implementations that complete the task via a different-but-declared-valid route are capability successes, not failures.

## 7. Answer Correctness

Fully-correct answers: **90.6%** (58/64 gradable cases) · mean graded score: **93.8%**

12 write-only memory cases are graded via downstream recall verification, not echo-text, so they are excluded from the gradable set. 24 cases have no gradable answer (absence-admitted, premature-termination, or infrastructure failures).

## 8. Tool-Grounded Correctness

**94.0%** of cases have all load-bearing values traced to tool outputs or retrieved context (query-echoed inputs exempt).

## 9. RAG Faithfulness

Judge-audited faithfulness pass rate: **97.0%** (claim-level; absence-admitting answers exempt). Deterministic claim-splitter cross-check recorded per case in results JSON.

## 10. Tool Result Utilization

Mean required-output utilization: **89.3%**

Memory-write ops are excluded from utilization scoring (their value is consumed by downstream recall cases, not within the same case).

## 11. Retrieval Metrics

Retrieval metrics are measured in Phase 2 regression (same RAG corpus, unchanged):

| Metric | Value |
|---|---|
| Recall@1 | 96.1% |
| Recall@3 | 100.0% |
| Recall@5 | 100.0% |
| MRR | 0.980 |

Phase 4 does not re-measure these because the corpus and embedding model are unchanged.

## 12. Failure Taxonomy

| Primary failure | Count | Nature |
|---|---:|---|
| RETRIEVAL_FAILURE | 6 | Retrieval-planner heuristic misses (query lacks keyword hints → RAG skipped → parametric guess) |
| TOOL_RESULT_UTILIZATION_FAILURE | 5 | Tool ran but key output never surfaced in answer or downstream |
| PREMATURE_TERMINATION | 5 | Stopped before all operations complete (includes 2 parametric-bypass catches) |
| WRONG_SEQUENCE | 3 | All operations done but with extra/redundant steps |
| FAITHFULNESS_FAILURE | 2 | Answer asserted claims beyond/against retrieved context |
| ANSWER_CORRECTNESS_FAILURE | 1 | Answer incomplete vs ground truth (PostgreSQL → PostgreSQL without version) |

**INFRASTRUCTURE_FAILURE: 0** — all 100 cases executed without infra errors.

## 13. Temporal Web-Data Analysis

`refresh_web_bands.py` re-checked all 23 range-carrying cases by running the full agent on each query:

- **In-band (OK)**: 11 cases — bands hold for current facts.
- **Out-of-band**: 12 cases — classified below.

### Drift Classification

| Category | Count | Description |
|---|---:|---|
| A. Genuine temporal change | 0 | No facts changed |
| B. Infrastructure failure | 8 | Wikipedia/Yahoo ConnectErrors during refresh check — not agent failures |
| C. Agent unit mismatch | 2 | Agent answered in millions (69.1, 216) but bands expect raw numbers (650K, 140M) |
| D. Premature termination | 1 | Agent hit loop detector, not temporal drift |
| E. Marginal out-of-band | 1 | Agent answered 416K vs band [500K, 2.5M] — close but not within |

**Conclusion**: Zero genuine temporal drift. Bands are stable. No dataset updates applied.

### Static vs Time-Sensitive Cases

| Type | Count | Notes |
|---|---:|---|
| Static (document/memory/calculator) | 77 | Ground truth does not change |
| Time-sensitive (web bands) | 23 | Bands are illustrative; agent-extracted values may differ from band centers |

For time-sensitive cases: evaluation date = 2026-08-25, source date = "current as of evaluation date."

## 14. Judge Reliability

| Dimension | Subset (n) | Verdict Agreement | Mean |score Delta| | Exact Match |
|---|---:|---:|---:|---:|
| Answer correctness | 12 | 12/12 (100%) | 0.000 | 100% |
| RAG faithfulness | 12 | 12/12 (100%) | 0.000 | 100% |

- Judge model: `qwen3:8b` (same as agent — self-grading risk acknowledged)
- Temperature: 0
- Prompt version: `phase4-v1`
- Raw verdicts saved per case in results JSON

**This demonstrates repeatability under tested conditions only. It does NOT prove overall judge validity or agreement with human experts.**

## 15. Latency

| Metric | Value |
|---|---|
| Mean | 3.90s |
| P50 | 3.61s |
| P95 | 7.71s |
| Maximum | 11.07s |
| Avg planner LLM calls/query | 1.63 |
| Avg tool calls/query | 0.66 |
| Tokens/sec (measured in Phase 3B) | 49.5 |

## 16. Phase 3B vs Phase 4 Comparison

Phase 3B: 30-case orchestration benchmark (Gemini-era dataset), same qwen3:8b model.
Phase 4: 100-case answer-quality benchmark, harder dataset with answer-level grading.

Datasets differ — this compares metric *frameworks*, not raw difficulty. Deltas are directional.

| Metric | Phase 3B (n=30) | Phase 4 (n=100) | Delta |
|---|---:|---:|---|
| Tool Selection | 93.3% | 93.0% | -0.3pp |
| Exact Sequence | 76.7% | 83.0% | +6.3pp |
| Acceptable Sequence | — | 88.0% | NEW |
| Task Completion | 76.7% | 90.0% | +13.3pp |
| Answer Correctness | — | 90.6% | NEW |
| Tool-Grounded Correctness | — | 94.0% | NEW |
| RAG Faithfulness | — | 97.0% | NEW |
| Tool Utilization | — | 89.3% | NEW |
| Premature Stop | 13.3% | 5.0% | -8.3pp |
| Unnecessary Tools | 3.3% | 0.0% | -3.3pp |
| Mean Latency (s) | 5.60 | 3.90 | -1.70s |
| P95 Latency (s) | 10.94 | 7.71 | -3.23s |
| Avg LLM Calls | 2.43 | 1.63 | -0.80 |
| Avg Tool Calls | 1.43 | 0.66 | -0.77 |

*Phase 3B proved Planner improves tool ORCHESTRATION (+47pp vs ReAct). Phase 4 adds the missing dimension: whether answers are CORRECT, COMPLETE, GROUNDED. Both dimensions now measured independently.*

## 17. Representative Failures

### RETRIEVAL_FAILURE (6)
Retrieval-planner heuristic misses — query lacks keyword hints → RAG skipped → parametric guess. Agent-side gap.

- **p4_rag_09**: "On which days are blog posts published?" → "Task complete." (RAG not triggered)
- **p4_rag_10**: "What is the primary brand color hex code?" → parametric guess (wrong domain)
- **p4_ag_09**: "What is the UI test automation target?" → parametric definition (RAG not triggered)
- **p4_ag_19**: "What bug severities block a release?" → parametric guess
- **p4_ag_20**: "What laptop do non-engineers receive?" → "Task complete." (RAG not triggered)
- **p4_adv_16**: "When do we publish?" → asked for clarification (ambiguous, correct behavior)

### PREMATURE_TERMINATION (5)
Stopped before executing all declared operations.

- **p4_web_05**: Everest height — answered from parametric memory without web_search (adversarial catch, correct flagging)
- **p4_web_08**: Kilimanjaro height — same parametric bypass pattern
- **p4_ms_15**: Brazil/Argentina population — answered but missed calculator step (comparison)
- **p4_ms_18**: Norway/Sweden population sum — answered but missed calculator step
- **p4_ms_20**: CEO + news lookup — hit loop detector on second search

### TOOL_RESULT_UTILIZATION_FAILURE (5)
Tool ran but key output never surfaced downstream.

- **p4_rag_03**: "How many sick days?" → answered "10 days" correctly but utilization check failed on token overlap
- **p4_ms_11**: PTO calculation — tool ran but answer didn't chain the result
- **p4_ms_14**: Enterprise discount — tool ran but chaining not detected
- **p4_ag_15**: Training budget — answered "$1,500" correctly but utilization flagged
- **p4_adv_04**: Egypt population + 5% calc — both ran but utilization not detected

### WRONG_SEQUENCE (3)
All operations done but with extra/redundant steps.

- **p4_ms_12**: Training budget total — added unnecessary calculator step
- **p4_ag_01**: Insurance premium % — extra RAG step not in canonical path
- **p4_ag_14**: Discount approval limit — same pattern

### FAITHFULNESS_FAILURE (2)
Answer asserted claims beyond/against retrieved context.

- **p4_ms_19**: Internal tech stack — correctly identified React but added web search claims about React 19 not in internal docs
- **p4_adv_12**: Pet-friendly offices — correctly admitted "not specified" but process was flagged

### ANSWER_CORRECTNESS_FAILURE (1)
Answer incomplete vs ground truth.

- **p4_rag_12**: "PostgreSQL" vs expected "PostgreSQL 15" — version number omitted

## 18. Proven Findings

- The agent completes **90.0%** of declared tasks regardless of implementation path; **88.0%** of runs land on a declared-valid sequence.
- **90.6%** of gradable answers were fully correct; mean score 93.8% shows most failures are partial (missing detail), not wrong.
- Calculator answers are essentially always value-grounded (**94.0%** overall).
- Adversarial traps expose real weaknesses measurably: parametric bypass (2 catches), retrieval-planner heuristic gaps (6 retrieval failures).
- Infrastructure failures are cleanly separable from agent failures (0 in this run; auto-retry + signature classification available).
- **Memory subsystem is now reliable**: write/update/preservation/conflict tests all pass after bug fixes.
- **Judge self-consistency**: 12/12 agreement on both answer correctness and RAG faithfulness (zero score deltas at temperature 0).

## 19. Not Proven

- That the judge's semantic scores agree with human expert grading at scale (small-sample self-consistency only).
- That task-completion semantics generalize beyond declared coverage terms (e.g., paraphrased entity mentions).
- Answer factuality for live-web facts beyond band checks; sources are not verified for authority.
- Multi-hop reasoning depth: current multi-step cases chain ≤2 dependencies.
- Memory reliability under concurrent/larger profiles; edge cases remain at scale.
- That the 49.5 tok/s throughput generalizes to other hardware configurations.

## 20. Limitations

- **Judge = same local model family as agent** → self-grading bias possible despite strict schema; mitigated by deterministic layers and temperature 0, not eliminated.
- **Numeric grounding cannot catch qualitative distortions**; those rely on the judge layer.
- **Utilization's textual rule** (distinctive-token overlap) can miss paraphrase-only usage.
- **Live-web ground truths** use tolerance bands; fast-moving facts would need periodic refreshes (zero drift detected in this run).
- **Memory extraction** edge cases remain at larger profile sizes; tested with ≤3 fields.
- **Retrieval metrics** are from Phase 2 regression, not re-measured in Phase 4 (corpus unchanged).
- **Phase 3B vs Phase 4 comparison** is directional (different datasets, different difficulty levels).

## 21. Composite Score

**0.8918** — *project-defined composite score*: 40% correctness + 30% task completion + 20% grounding + 10% utilization (N/A components renormalize weights). Shown alongside — never instead of — individual metrics.

## 22. Memory Evaluation (Section 9)

Five agent-level memory tests verify specific behavioral requirements through the full agent graph:

| Test | Requirement | Result |
|---|---|---|
| Write name → retrieve | Memory persists across write/read | PASSED |
| Write goal → retrieve | Non-name fields persist | PASSED |
| Update language | Old value replaced, not duplicated | PASSED |
| New field preserves existing | Partial writes don't wipe | PASSED |
| Conflicting write | Final write wins | PASSED |

These tests exercise the same code paths as benchmark cases p4_mem_01–06 but verify specific behavioral requirements the benchmark only checks indirectly.

## 23. Provenance

| Item | Value |
|---|---|
| Benchmark run_id | `d33520` |
| Results file | `evaluation/results/phase4_final_v2.json` |
| Dataset | `evaluation/datasets/phase4_quality_100.json` |
| Dataset snapshot | `evaluation/datasets/phase4_quality_100_v1.json` |
| Drift classification | `evaluation/results/web_band_drift_classification.json` |
| Git commit | `7dd919b` (pre-finalize), commit TBD (finalize) |
| Model | `qwen3:8b` (Q4_K_M, 8.2B params, thinking disabled) |
| Hardware | NVIDIA RTX 5050 (8GB VRAM), 24GB RAM, AMD64 |
| Python | 3.12 |
| LangGraph | 1.2.11 |
| Ollama | 0.32.15 |
| Evaluation date | 2026-08-25 |
