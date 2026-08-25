# Phase 4 — Answer Quality & Evaluation Maturity

Generated from `evaluation/results/phase4_final.json` · run_id `62bf81` · model `qwen3:8b` (Ollama, local)

## Executive Summary

- **100/100** cases completed (0 infrastructure failures, excluded from agent rates where marked).
- Tool orchestration stays strong on the harder, ground-truth-rich dataset: **92.0% selection**, **88.0% acceptable-sequence**, **83.0% exact-sequence**.
- First direct evidence on ANSWERS: **90.0% task completion**, **85.7% fully-correct answers** (mean correctness score 91.1%), **94.0% tool-grounded**, **97.0% RAG-faithful**, utilization 84.2%.
- Project-defined composite score: **0.8783** (40% correctness / 30% completion / 20% grounding / 10% utilization — configurable; NOT an industry standard).
- Key insight: sequence metrics alone overstate quality. Several sequence-'failures' are actually complete tasks (consolidated searches), while several sequence-'passes' hid wrong or unfaithful answers that only answer-level metrics caught.

## Dataset

`evaluation/datasets/phase4_quality_100.json` — 100 cases, 5 buckets × 20:

| Bucket | n | Focus |
| `adversarial` | 20 | parametric-bypass traps, absent-info hallucination probes, unnecessary-tool traps, ambiguous wording, multi-valid sequences |
| `answer_grounded` | 20 | RAG answers whose values must trace to retrieved documents (faithfulness-judged) |
| `multi_step` | 20 | web→calc, rag→calc, web×2→calc, rag→web chains with declared operations & acceptable sequences |
| `rag_memory` | 20 | document lookups + runtime memory writes/recalls ({rid}-templated for isolation) |
| `single_tool` | 20 | pure calculator arithmetic and live web lookups |

Ground truth schema per case: expected answer (value or tolerance band), required information tokens, declared operations with coverage terms, required tools, acceptable tool sequences, forbidden tools, argument constraints, forbidden-answer patterns, expected context docs, source. Legacy datasets remain supported via normalization.

## Evaluation Methodology

1. **Task Completion** (operation-based): every declared operation must be satisfied by real evidence — a lookup op requires tool output covering its declared entities (one consolidated search covering both entities PASSES); a calculator op requires clean execution; rag/memory ops require engaged retrieval. Independent of step order.
2. **Exact vs Acceptable sequences**: canonical path tracked separately from dataset-declared alternative implementations. No benchmark-specific exceptions — everything comes from declared ground truth.
3. **Answer Correctness**: deterministic layer first (numeric match with 2% band, range bands for live-web values, required-information tokens, forbidden-pattern checks). A structured-output LLM judge (qwen3:8b @ temperature 0, Pydantic schema with correct/score/reason/missing_information/contradictions) handles natural-language answers only.
4. **Tool-Grounded Correctness** (deterministic): every load-bearing number in the final answer must trace to tool outputs or retrieved context (query-echoed inputs exempt). Catches calc-says-X answer-says-Y failures.
5. **RAG Faithfulness**: claim-level judge verdicts (supported/unsupported/contradicted claims) cross-checked by a deterministic word-overlap claim splitter. Recall@K is explicitly NOT used as a faithfulness proxy.
6. **Tool Result Utilization**: each required output must surface in later tool arguments (chaining) or the final answer (numeric or distinctive-token match). Absence-answers exempt.
7. **Failure taxonomy v2** with INFRASTRUCTURE_FAILURE separated (DNS/rate-limit signatures auto-retried once).

## Task Completion

**90.0%** (90/100 completed cases)

## Exact Sequence Accuracy

Exact canonical path: **83.0%** · any-declared-acceptable path: **88.0%**

The gap is exactly the point of Phase 4: implementations that complete the task via a different-but-declared-valid route are capability successes, not failures.

## Answer Correctness

Fully-correct answers: **85.7%** · mean graded score: **91.1%**

## Tool-Grounded Correctness

**94.0%** of applicable cases have all load-bearing values traced to tool outputs/context.

## RAG Faithfulness

Judge-audited faithfulness pass rate: **97.0%** (claim-level; absence-admitting answers exempt). Deterministic claim-splitter agreement recorded per case in results JSON.

## Tool Result Utilization

Mean required-output utilization: **84.2%**

## Composite Score

**0.8783** — *project-defined composite score*: 40% correctness + 30% task completion + 20% grounding + 10% utilization (N/A components renormalize weights). Shown alongside — never instead of — individual metrics.

## Failure Taxonomy

| Primary failure | Count |
|---|---:|
| TOOL_RESULT_UTILIZATION_FAILURE | 11 |
| RETRIEVAL_FAILURE | 6 |
| PREMATURE_TERMINATION | 4 |
| WRONG_SEQUENCE | 3 |
| ANSWER_CORRECTNESS_FAILURE | 2 |
| FAITHFULNESS_FAILURE | 2 |

## Adversarial Evaluation

- Adversarial bucket task completion: **95.0%** (20 cases).
- Parametric-bypass traps: caught — Everest/Kilimanjaro answered from memory without web_search (p4_web_05, p4_web_08), correctly flagged PREMATURE_TERMINATION even though values were right.
- Absent-info probes: agent correctly admitted 'not specified' instead of fabricating figures.
- Unnecessary-tool traps (mental math/date reasoning): no forbidden tools fired.

## Latency

Mean 3.92s · P50 3.62s · P95 7.64s · avg planner LLM calls/query 1.63 · avg tool calls/query 0.66

## Phase 3B vs Phase 4

Phase 3B: 30-case orchestration benchmark (Gemini-era dataset), same qwen3:8b model. Phase 4: new 100-case answer-quality benchmark. Datasets differ — this compares metric *frameworks*, not raw difficulty.

| Metric | Phase 3B | Phase 4 | Delta |
|---|---:|---:|---:|
| Tool Selection | 93.3% | 92.0% | -1.3pp ⚠ |
| Exact Sequence | 76.7% | 83.0% | +6.3pp ✅ |
| Acceptable Sequence | — | 88.0% | NEW |
| Task Completion | 70.0% | 90.0% | +20.0pp ✅ |
| Answer Correctness | — | 85.7% | NEW |
| Tool-Grounded Correctness | — | 94.0% | NEW |
| RAG Faithfulness | — | 97.0% | NEW |
| Tool Result Utilization | — | 84.2% | NEW |
| Premature Stop | 3.3% | 4.0% | +0.7pp ⚠ |
| Unnecessary Tools | 0.0% | 0.0% | +0.0pp |
| Argument Accuracy | 100.0% | 100.0% | +0.0pp |
| Mean Latency (s) | 560.0% | 3.92s | -168.0pp ✅ |
| P95 Latency (s) | 1094.0% | 7.64s | -330.0pp ✅ |

*Phase 3B proved Planner improves tool ORCHESTRATION (same-model ReAct comparison: +47pp selection). Phase 4 adds the missing dimension: whether answers are CORRECT, COMPLETE, GROUNDED. Both dimensions are now measured independently.*

## Representative Failures

### RETRIEVAL_FAILURE (6)
*Retrieval-planner heuristic misses (query lacks keyword hints → RAG skipped → parametric guess). Agent-side gap.*

- **p4_rag_09** (`rag_memory`): Q: `On which days are blog posts published?`
  - expected: `every Tuesday on Medium` · actual: `Task complete.`
  - judge: *The actual answer 'Task complete' does not convey the expected answer's information about publication days (Tuesday) and platform (Medium). It provides no relevant context to answe*
- **p4_rag_10** (`rag_memory`): Q: `What is the primary brand color hex code?`
  - expected: `#0F52BA (Tech Blue)` · actual: `The primary brand color hex code for many well-known brands can vary, but for example, the primary brand color hex code for Facebook is #3b5998, for Twitter it `
- **p4_ag_09** (`answer_grounded`): Q: `What is the UI test automation target?`
  - expected: `90%` · actual: `The UI test automation target refers to the user interface elements or components that are being tested through automated testing tools. These targets can inclu`
- **p4_ag_19** (`answer_grounded`): Q: `What bug severities block a release?`
  - expected: `open Sev-1 or Sev-2 bugs` · actual: `Bug severities that typically block a release include critical and high severity issues. Critical bugs are those that cause the application to crash, prevent co`
- …and 2 more (see results JSON).

### PREMATURE_TERMINATION (4)
*Stopped before executing all declared operations — includes adversarial parametric bypass catches.*

- **p4_web_05** (`single_tool`): Q: `How tall is Mount Everest in meters?`
  - expected: `None` · actual: `Mount Everest is approximately 8,848.86 meters tall.`
- **p4_web_08** (`single_tool`): Q: `What is the height of Mount Kilimanjaro in meters?`
  - expected: `None` · actual: `The height of Mount Kilimanjaro is approximately 5,895 meters.`
- **p4_ms_15** (`multi_step`): Q: `Find the population of Brazil and the population of Argentina. Which o`
  - expected: `None` · actual: `The population of Brazil is 213,964,342 (as of 2026), and the population of Argentina is 46,044,703 (as of 2022). Brazil has a larger population than Argentina `
- **p4_ms_18** (`multi_step`): Q: `Find the populations of Norway and Sweden and tell me their total comb`
  - expected: `None` · actual: `The population of Norway in 2025 was 5,610,870, and the population of Sweden in 2025 was 10,596,620. Their total combined population is 16,207,490.`

### ANSWER_CORRECTNESS_FAILURE (2)
*Answer incomplete or wrong vs ground truth.*

- **p4_rag_12** (`rag_memory`): Q: `What database is our primary relational database?`
  - expected: `PostgreSQL 15` · actual: `The primary relational database is PostgreSQL.`
- **p4_mem_04** (`rag_memory`): Q: `What is my goal?`
  - expected: `AI engineer62bf81` · actual: `Your goal is to become an AI engineer.`
  - *Root cause: `{rid}` suffix in expected answer — the extractor reasonably treated it as noise. Dataset updated (see Post-Run Fixes).*

### FAITHFULNESS_FAILURE (2)
*Answer asserted claims beyond/against retrieved context.*

- **p4_ms_19** (`multi_step`): Q: `Which frontend framework does our internal tech stack document say we `
  - expected: `None` · actual: `The internal tech stack document states that we use React as the frontend framework. According to the web search, the latest major version of React is React 19.`
- **p4_ms_20** (`multi_step`): Q: `Who is the CEO of our company according to internal docs? Then find on`
  - expected: `None` · actual: `According to the internal documents, the CEO of our company is Todd Armstrong (from the document 'company_values.txt' and 'social_events.txt'). A recent news ar`

### TOOL_RESULT_UTILIZATION_FAILURE (11)
*Tool ran but its key output never surfaced downstream. Memory-write cases (p4_mem_01–03) are now fixed (see Post-Run Fixes below).*

- **p4_rag_03** (`rag_memory`): Q: `How many sick days are allowed per year?`
  - expected: `10 days` · actual: `10 days`
- **p4_mem_01** (`rag_memory`): ~~`your goal is to become an .`~~ → FIXED — profile wipe bug.
- **p4_mem_02** (`rag_memory`): ~~`your goal is to become an to become an AI engineer`~~ → FIXED — double phrasing.
- **p4_mem_03** (`rag_memory`): ~~`not provided in the retrieved context`~~ → FIXED — recall now works across writes.
- …and 7 more non-memory cases (see results JSON).

### WRONG_SEQUENCE (3)
*All operations done but with extra/redundant steps outside declared paths.*

- **p4_ag_01** (`answer_grounded`): Q: `What percentage of health insurance premiums does GlobalTech cover for`
  - expected: `80%` · actual: `GlobalTech covers 80% of the health insurance premiums for dependents.`
- **p4_ag_14** (`answer_grounded`): Q: `Up to what discount percentage can a Regional Sales Director approve?`
  - expected: `15%` · actual: `A Regional Sales Director can approve discounts up to 15%.`
- **p4_adv_11** (`adversarial`): Q: `Per our sales playbook, who approves discounts up to 15% - the CFO or `
  - expected: `Regional Sales Director` · actual: `According to the sales playbook, discounts up to 15% can be approved by the Regional Sales Director, not the CFO.`
  - judge: *The actual answer correctly identifies the Regional Sales Director as the approver for discounts up to 15% per the sales playbook (Doc 1). It directly matches the expected answer a*

## Judge Reliability

- Same subset judged twice (n=12): verdict agreement **12/12**, mean |score delta| **0.000**, exact-score match **100%**.
- **RAG faithfulness double-run** (n=12 context-rich cases): verdict agreement **12/12**, mean |score delta| **0.000**.
- Judge model: `qwen3:8b`, prompt version `phase4-v1`, temperature 0, structured output, raw verdicts saved per case.
- Small-sample consistency check ONLY — no statistical reliability claimed. Both dimensions (answer correctness + faithfulness) now covered.

## Evaluation Limitations

- Judge = same local model family as agent → self-grading bias possible despite strict schema; mitigated by deterministic layers and temperature 0, not eliminated.
- Numeric grounding cannot catch qualitative distortions; those rely on the judge layer.
- Utilization's textual rule (distinctive-token overlap) can miss paraphrase-only usage.
- Live-web ground truths use tolerance bands; fast-moving facts would need periodic refreshes (see Web Band Drift below).
- Memory extraction glitches (fields swapped/dropped during write) propagate to recall cases — two genuine bugs found and fixed (see Post-Run Fixes); additional edge cases remain at larger profile sizes.

## Post-Run Agent Fixes

Two genuine agent bugs found via Phase 4 memory-bucket failures, both now fixed:

1. **Profile wipe bug** (`nodes/memory_extractor.py:memory_saver_node`): `memory.update(extracted_profile)` with empty-string extractions (e.g. `{"name": ""}`) overwrote previously stored facts, causing "What is my name?" to fail after a second unrelated memory write. Fixed by filtering out empty/None/empty-list values before merging (`clean_profile = {k: v for k, v in ... if v not in (None, "", [], {})}`).

2. **Confirmation message garbling** (`nodes/memory_extractor.py:memory_response_node`): empty fields rendered as blanks (`"your name is , your goal is to become an ."`) and the extractor stored redundant phrasing in goal (`"to become an AI engineer"`) which got doubled in the template (`"your goal is to become an to become an AI engineer"`). Fixed by skipping empty fields and using neutral phrasing (`"your goal is {goal}"`) when the extraction already contains a "to ..." prefix.

**Re-run on 6-case memory subset post-fix**: task completion 100%, utilization 100%, zero failures. Write cases now grade via downstream recall verification (confirmation text ignored); recall cases pass correctly across sequential writes.

## Web Band Drift Check

`refresh_web_bands.py` re-checks all 22 range-carrying cases against current live search results:

- **In-band (OK)**: 8 cases — bands still hold for current facts.
- **Drift detected**: 14 cases — live search results fell outside declared tolerance bands. Most drift is on fast-moving data (e.g. population figures, web search result counts).
- Drift is expected given the dataset was created 2026-08-25; the band values are illustrative, not permanent ground truth.
- `--apply` mode available to widen bands from fresh evidence; should be reviewed via `git diff` before committing.

## Proven Findings

- The agent completes **90.0%** of declared tasks regardless of implementation path; 88.0% of runs land on a declared-valid sequence.
- **85.7%** of gradable answers were fully correct; mean score 91.1% shows most failures are partial (missing detail), not wrong.
- Calculator answers are essentially always value-grounded (**94.0%** overall incl. search/RAG cases).
- Adversarial traps expose real weaknesses measurably: parametric bypass (2 catches), retrieval-planner heuristic gaps (6 retrieval failures), redundant steps (wrong_sequence bucket).
- Infrastructure failures are cleanly separable from agent failures (auto-retry + signature classification).
- **Judge self-consistency**: 12/12 agreement on both answer correctness AND RAG faithfulness dimensions (zero score deltas at temperature 0).

## Not Proven

- That the judge's semantic scores would agree with human expert grading at scale (small-sample self-consistency only).
- That task-completion semantics generalize beyond declared coverage terms (e.g., paraphrased entity mentions in search snippets).
- Answer factuality for live-web facts beyond band checks; sources are not verified for authority.
- Multi-hop reasoning depth: current multi-step cases chain ≤2 dependencies.
- Memory reliability under concurrent/larger profiles; extraction edge cases remain at scale.