# WealthPilot — SME loan underwriting assistant: implementation and experiments

*All numbers below are produced by the scripts in `experiments/` and stored in `report/results/`. Sample sizes are small by
design (free NVIDIA NIM tier, see "Limitations"); every rate comes with a 95% interval where one is meaningful.*

## 1. What was built

A multi-agent assistant that underwrites SME loans end to end: **parse** financial documents, **analyse** ratios, **research**
the borrower, **score** default risk, **apply a credit policy** read from its prose via RAG, **draft a memo** — and **stop for a
human decision**. It is policy-agnostic: the question under test is how faithfully it applies *whatever clear policy it is given*;
US inputs (SBA 7(a) data, an ECOA/Reg-B-style profile) are example configuration, not the subject of evaluation.

| Area | Implementation |
|---|---|
| Orchestration | LangGraph StateGraph, deterministic routing (code predicates over typed state), parallel analyst‖research, bounded loops, Postgres checkpointer + store |
| Agents (6 roles) | Parser, Financial Analyst, Credit Research, Risk Scorer, Policy/Compliance, Memo Writer (five call the LLM; the Risk Scorer is tool-only) |
| MCP | 3 FastMCP servers over streamable HTTP (16 tools): `fincalc`, `policydocs`, `research`; consumed via `langchain-mcp-adapters` |
| Documents | PDF text layer → layout reconstruction → LLM extraction → reconciliation → repair; scanned pages → NIM vision model |
| Risk | LightGBM PD model on real SBA 7(a) outcomes (5-year charge-off), SHAP reasons, MLflow registry; ratio scorecard; fixed grade matrix |
| Policy RAG | structure-aware chunking, BM25 + pgvector (Ollama embeddings) + RRF, NIM rerank |
| Memory | per-case checkpoints; long-term applicant/decision memory (LangGraph store); semantic precedents (pgvector) |
| Reliability | shared NIM gateway: Postgres cache, adaptive global rate limit, retry/backoff, circuit breaker, model fallback, fault injection |
| Compliance | redaction of protected attributes, prohibited-basis language scan, memo validator, hash-chained audit log |
| Human approval | `interrupt()` before every decision; approver tier enforced against the policy's delegation of authority |
| Interfaces | Typer CLI, Streamlit approval console |

Design rules that shaped the results: the LLM never does arithmetic that is not re-checked by code, never decides the final
recommendation (the policy's fixed decision rule does), never routes the graph, and never sees protected attributes. A degraded run
(tool outage) can never auto-approve.

## 2. Setup of the experiments

* **Data.** Real: SBA 7(a) FOIA FY2010–2019 (545,751 loans, 42 columns — *no race/gender/ethnicity fields*) and the OFAC SDN list.
  Synthetic: 80 applicants with true 3-year statements, bank statements, planted sanctions/adverse-media cases, PDFs in three
  variants (clean, noisy layout, scanned image-only), and ground-truth decisions under two policies computed by a hidden reference engine.
* **Two policies.** *Conservative* and *Growth*, authored as prose with rule ids CP-1…CP-13. They differ in numbers **and** in
  qualitative rules (prohibited industries, an exception band, guarantee conditions, collateral conditions). The YAML answer key is
  visible only to the ground-truth engine, so agents must read the prose.
* **LLM.** Free NVIDIA NIM endpoints only. Chat/tools: `nemotron-3.5-lightning-30b`; vision: `nemotron-3.5-super-vl-120b`;
  rerank: `llama-nemotron-rerank-vl-1b-v2`; embeddings: local Ollama `nomic-embed-text`.

## 3. Results

### 3.0 Risk model (SBA 7(a))
A first model scored AUC 0.946 — too good. The cause was a **label leak**: for charged-off loans `TermInMonths` holds the *realised*
term (7, 43, 52 months…), for paid loans the original round term (84, 120, 60), so term alone gives AUC 0.95. It is excluded.
The final label is *charged off within 5 years of approval*, which also removes right-censoring (every approval has ≥6 years of history).
Test (FY2017–19, n = 155,941): **AUC 0.68**, Brier 0.0404 vs 0.0412 for a constant predictor, base rate 4.3%. This is a modest but real
signal from profile-only features (no financials), and it is calibrated (isotonic).

### 3.1 E0 — End-to-end policy adherence
Same 12 cases under both policies, scored against the reference engine (24 runs). Runs stop at the human-approval gate.

| | Strict | Lenient |
|---|---|---|
| Decision accuracy | **100%** (12/12, CI 76–100%) | **91.7%** (11/12, CI 65–99%) |
| Per-rule status accuracy | 97.2% | 94.4% |
| Policy thresholds read correctly from prose | 100% | 100% |
| Approver tier | 91.7% | 100% |
| Risk grade | 100% | 100% |

**Policy-flip agreement: 83% (5/6).** For the six cases whose correct decision differs between the two policies, the system changed
its decision the same way in 5. This is the cleanest evidence that it follows the policy it is given rather than a fixed habit.

*What the errors were.* Of 12 rule-level mismatches (out of 288 rule judgements), 7 were on CP-8 (collateral), where the condition is
"required only for loans above a size": the model repeatedly misread that *loan-size condition* (e.g. "USD 117,000 is below the USD 150,000
threshold, but the policy states that requests above…"), 5 as a wrong `fail` and 2 as `missing_data` after the numeric re-check could not
reconcile its comparisons. The other five are single slips: cryptocurrency treated as prohibited under the lenient policy (where only
cannabis and adult entertainment are), a **hallucinated fact** (for a business whose only coverage was a positive article about a
small-business award, the model asserted a "medium severity adverse media finding" and escalated — the case facts said `none`; the one
error that is not a policy-reading error), a current ratio of 0.9956 passed against a 1.00 minimum, and two guarantee judgements.

*Ablation — numeric verification.* Before it, the same experiment gave strict **91.7%** / lenient **66.7%** decision accuracy and
**33%** flip agreement, with 9 of 17 mismatches being arithmetic comparison errors. The fix: the model lists every numeric comparison it
relied on, code re-evaluates each, and a contradiction triggers a targeted re-ask (and, if still inconsistent, `missing_data` → refer).
Raw ablation results: `report/results/ablation_no_numeric_verify/`.

### 3.2 E1 — Document parsing (12 cases × 3 variants; 19 fields per year)

| Variant | Rule-based, oracle labels | Rule-based, canonical labels | LLM, raw text | LLM, layout-reconstructed | + reconciliation repair |
|---|---|---|---|---|---|
| Clean | 100% | 100% | 97.9% | 100% | 100% |
| Noisy layout | 100% | 36.7% | 80.3% | 99.5% | **100%** |
| Scanned (image-only) | 0% | 0% | 96.9% | 96.9% | 96.9% |

Bank statements (monthly rows): 144/144 correct in all three variants.

* A rule-based parser that knows every label variant is perfect on text PDFs but cannot read a scan at all; with only canonical labels it
  collapses on noisy layouts. The LLM is robust to unseen label variants and to scans.
* On noisy layouts the raw LLM made a **column-swap** error (assigning FY2023 numbers to FY2024 when headers were formatted
  differently) — an error **reconciliation cannot catch**, because each year's totals still balance. Rebuilding tables from word
  coordinates so every row states its values *by year* removed it (80.3% → 99.5%).
* On scans, reconciliation **flagged both** wrong documents (2/2) but the repair did not fix them (96.9% unchanged): detection works,
  automatic repair of OCR digit errors does not, which is what the human document-review gate is for.
* Extended thinking was tried for extraction and abandoned: a single document took >4 minutes.

### 3.3 E2 — Policy RAG ablation (104 queries; gold = the rule section that answers)

| Chunking | Retrieval | Rerank | recall@1 | recall@3 | MRR |
|---|---|---|---|---|---|
| structure | BM25 | – | 0.798 | 0.856 | 0.822 |
| structure | dense | – | 0.740 | 0.904 | 0.821 |
| structure | hybrid (RRF) | – | 0.769 | 0.885 | 0.819 |
| structure | BM25 | NIM | 0.923 | 0.923 | 0.923 |
| structure | dense | NIM | 0.942 | 0.942 | 0.942 |
| structure | hybrid | NIM | **0.971** | 0.971 | **0.971** |
| fixed windows | BM25 | – | 0.625 | 0.856 | 0.732 |
| fixed windows | dense | – | 0.683 | 0.904 | 0.779 |
| fixed windows | hybrid | – | 0.673 | 0.923 | 0.790 |
| fixed windows | hybrid | NIM | 0.923 | 0.990 | 0.954 |

Reranking is the dominant lever (hybrid recall@1 0.77 → 0.97). Structure-aware chunking beats fixed windows until a reranker closes
the gap (note the fixed-window metric is generous: a window counts as a hit if it overlaps the gold section). Hybrid fusion alone did
not beat BM25 here — the policy corpus is small and keyword-rich.

### 3.4 E3 — Fairness and compliance

**(a) Proxy-group audit on real SBA data** (the file has no protected attributes, so we audit *proxies*, which are **not** legally
protected classes). Decision = decline the riskiest 20% (PD ≥ 5.3%).

| Attribute | Demographic-parity diff. | Equalized-odds diff. |
|---|---|---|
| Census region (5 groups) | 0.279 | 0.460 |
| Legal form (3 groups) | 0.249 | 0.302 |
| Business age: young vs established | 0.129 | 0.159 |

ThresholdOptimizer (equalized odds) on region cut the equalized-odds gap 0.60 → 0.39 at essentially unchanged balanced accuracy
(0.594 → 0.595), but **doubled the decline rate** (20.9% → 40.1%) — a real trade-off, not a free lunch. Caveat: **selective labels** —
only approved loans are observed, so disparities among *rejected* applicants are invisible.

**(b) Planted-bias detection** (synthetic; the model never sees the protected attribute, only a correlated proxy):

| Planted bias | Demographic-parity diff. (mean ± sd, 20 seeds) | Detected (permutation p<0.05) |
|---|---|---|
| 0.0 | 0.011 ± 0.009 | 15% (3 of 20 seeds) |
| 0.3 | 0.045 ± 0.014 | 100% |
| 0.6 | 0.090 ± 0.015 | 100% |
| 1.0 | 0.146 ± 0.016 | 100% |

Every planted level is detected, and the parity gap grows monotonically with the planted bias. The zero-bias false-positive rate (15%) is
above the nominal 5% because the test flags *any* statistically detectable gap, including the small one created when the model leaks a
little of the group-correlated proxy; the effect size at zero bias (0.011) is 4× smaller than at the weakest planted level (0.045). In
practice the audit should be read on effect size with a tolerance, not on the p-value alone. (An earlier 5-seed run showed 20%; 20 seeds
replaced it.)

**(c)(d) Identity counterfactuals** — see §3.5.

### 3.5 E3(c) identity counterfactuals

**Design.** For 3 cases we built counterfactual applicants with *identical financials, loan and documents* but a different owner name
(gender and name-origin swapped), business surname, street and ZIP — changed both in the structured fields **and inside the rendered
document text** (owner name on statements, on bank-statement memo lines, in the business name). Each of 9 identities ran through the full
graph with redaction **off** and **on**. The noise floor is the original identity re-run *without the cache* (same prompts, fresh calls).

| Redaction | Prompts containing identity tokens | Memos naming/identifying the owner | Decision flips | Rule-status flips | Noise floor (plain re-run) |
|---|---|---|---|---|---|
| **off** | 69/88 (**78%**) | 6/9 | 0/6 | 2/72 (2.8%) | 1/24 (4.2%) |
| **on** | 0/84 (**0%**) | 0/9 | 0/6 | 0/72 | 0/36 |

* **Read the "on" row carefully.** With redaction on, each counterfactual's prompts are *identical* to the original's after redaction, so the
  cache replays the same replies and **0 decision/rule flips is guaranteed by construction** — it is not evidence about the model. The
  evidence in that arm is the **0/84 leak rate** and the **0/36 noise floor** (those re-runs had the cache off, so they are genuine fresh
  calls). The informative flip comparison is the *off* arm, where prompts really differ.
* **Redaction works on text.** With it on, no identity token reached any of 84 LLM requests and no memo contained one. Without it,
  78% of requests did and two-thirds of memos mentioned the owner.
* **No measurable identity effect on decisions.** Decisions never flipped; the rule-level flip rate with identity visible (2.8%) is
  statistically indistinguishable from the model's own run-to-run variation (4.2%). With 3 cases this cannot exclude small effects.
  The structural reason is also worth stating: decisions come from a fixed rule over the rule statuses, and rule statuses are judged
  from numbers and policy text, so identity can only act through the LLM's reading of the business label.
* **Memos never used prohibited-basis language** (0/9 in either arm).
* **A different non-determinism showed up:** one no-cache re-run extracted the documents slightly differently, failed reconciliation and
  was diverted to the human document-review gate (reported separately, not counted as a rule flip).
* **The redactor itself had a bug that this experiment found.** The first version matched substrings, so for an owner named "Mark" it
  rewrote "market" as "[OWNER]et" (corrupting prompts) and the leak meter reported 3.6% false leaks. Both are now whole-word
  (`report/results/ablation_naive_redaction/` keeps the first result).
* **Not covered:** scanned documents cannot be text-redacted, so identity in an image reaches the vision model (whose output schema is
  numeric only). First-pass adverse-action completeness (E3(d)) is *enforced* by the memo validator and unit-tested but was not
  separately measured as a rate.

### 3.6 E4 — Reliability under fault injection

**Design.** 4 cases (2 correct-approve, 2 correct-decline under the strict policy) × 7 fault profiles, cache **off** and fault injection
placed *below* the cache so every call really hits the network. Plus a crash/resume test. Outcomes are classified against ground truth;
the safety measures are **unsafe approve** (approving what should not be approved) and **wrongful decline** (declining what should not
be declined — an adverse action with no real basis).

| Profile | Outcome (4 runs) | Latency | Chat calls | Failed calls | Retries | Fallback calls |
|---|---|---|---|---|---|---|
| none | 4 correct | 1.00× | 42 | 0 | 0 | 0 |
| 429 storm (35% of chat/rerank calls) | 4 correct | 1.23× | 47 | 3 | 20 | 3 |
| timeouts (25% of chat calls) | 4 correct | 1.24× | 46 | 2 | 13 | 1 |
| malformed model output (30% of chat calls) | 1 correct, 1 safe refer, **2 escalated to human doc review** | 0.87× | 28 | 0 | 2 | 0 |
| flaky MCP servers (30% of tool calls) | 1 correct, 3 safe refer | 1.54× | 54 | 0 | 27 | 0 |
| research server down | 4 safe refer | 1.23× | 43 | 0 | 24 | 0 |
| fincalc server down | 4 safe refer | 1.63× | 49 | 1 | 26 | 1 |

**Headline: across all 28 runs there were 0 unsafe approvals and 0 wrongful declines, and every run that completed with a degraded
tool recommended *refer*.**

* **Transient faults are absorbed.** With rate-limit storms or timeouts the system produced the correct decision in 4/4 runs at ~1.2×
  latency, using retries (20 and 13) and a handful of fallback-model calls.
* **Output corruption fails safe, not silent.** When 30% of model replies were corrupted, 3 of 4 runs did *not* reach a confident decision:
  two stopped at the document-review gate (extraction JSON unparseable after one repair attempt) and one was downgraded to refer.
  The one run that stayed correct got lucky with clean replies.
* **Tool outages degrade to a human.** With a server down the run completes, flags itself degraded, lists the missing evidence in the
  memo and recommends *refer*. The memo validator requires a limitations section whenever a run is degraded.
* **Crash and resume.** Killing the process right after the risk step and resuming in a new session (same thread id, no input) continued from
  the Postgres checkpoint: parse, research and analyst — the expensive nodes — were **not** re-run; only the node in flight at the crash
  (`risk`) ran again (at-least-once semantics), and the final recommendation matched the uninterrupted run.

**A bug E4 found.** The first E4 run capped degraded runs only against *approving*. With a tool down, "sanctions screening not performed"
was sometimes judged a failure, so 4 correct-approve cases were **wrongly declined**. A degraded run now never auto-decides in either
direction (`final_recommendation`, unit-tested). The pre-fix result is kept in `report/results/ablation_degraded_may_decline/`.

Caveat: these are 4 cases per profile; the rates describe mechanisms, not precise probabilities. Latencies are inflated by the free
tier's throttling and by concurrency, so compare them with each other, not with production.

### 3.7 Which code produced which result

The system was hardened while the experiments ran, so results come from slightly different versions. Honest accounting:

| Experiment | Code version notes |
|---|---|
| E1, E2, E3(a)(b) | independent of the later graph changes. E3(b) was re-run with 20 seeds at the end. |
| E0 | final run uses batched rule judging + numeric verification + the empty-reply guard; the pre-verification run is kept as an ablation. |
| E3(c) | re-run after the whole-word redaction fix (the first run is kept as an ablation). |
| E4 | `none`, `429_storm`, `timeouts`, `malformed_output` and the crash test ran **before** the "degraded never auto-decides" cap, `mcp_flaky`/`research_down`/`fincalc_down` ran **after** it (they were the only profiles the cap can affect). |
| Redaction bug vs. E0/E1/E4 | checked: old (substring) and new (whole-word) redaction produce **identical** output on all 135 texts those experiments sent to the model, so the bug did not affect them. |

### 3.8 Observability

`mlflow.langchain.autolog()` is enabled in every graph session and each underwriting run is wrapped in a parent span, so **one case = one MLflow
trace** tagged with `case_id`, `policy_id` and `thread_id` (verified: a C004 run produced a 54-span trace; resume calls produce their own
traces under the same tags). In addition, every NIM/Ollama call is logged to the Postgres `nim_calls` table with latency, tokens, retries,
cache hit/miss, model and the case/experiment tag — that table is what E0/E4's usage and fallback columns are computed from. Experiment
metrics and the PD model are MLflow runs/registry entries. Not done: a Langfuse deployment (RAM), and dashboards beyond MLflow's UI.

## 4. Engineering findings worth recording

1. **Cache poisoning.** The shared cache stored *empty* model replies and replayed them forever; the first E0 run measured infrastructure
   noise, not policy reading (38% rule accuracy, mostly `missing_data`). Empty replies are now retried and never cached.
2. **Naive redaction was a bug, not just a leak.** Substring matching turned "market" into "[OWNER]et" for an owner named Mark and made
   the leak meter report false positives. Redaction and the meter are now whole-word.
3. **Free-tier reality.** The public NIM catalog lists many retired models; limits are per model; the 550B model degraded over the session
   (503s → empty replies → *garbled text* on long outputs); effective throughput was ~5–15 chat calls/minute. Responses: batch work, do
   retrieval in code (~13 chat calls per case instead of ~40), an adaptive shared rate limit (AIMD), 429s excluded from the circuit breaker.
4. **A bug that tests cannot see:** the policy agent contradicted itself on prohibition-style rules ("not a prohibited industry … status:
   fail") when asked for pass/fail. The model now answers plain boolean questions; code maps them to a status.
5. **Tool-use loop.** A tool-using tier agent hit the recursion limit and silently fell back to the safe default; the LLM now only
   *extracts* the authority limits from prose and code does the comparison.

## 5. Limitations

* Small samples (E0: 12 cases × 2 policies; E1: 12 cases; E3(c): 3 cases; E4: 4 cases per profile). Intervals are wide; treat these as
  evidence of mechanism, not precise rates.
* Synthetic documents and applicants: label noise, formats and fraud patterns are far simpler than reality. Adverse media and the business
  registry are mocks. The SBA data has no financial statements, so the PD model cannot use the parsed ratios.
* One LLM family; the single usable chat model was heavily rate-limited. Results on other models will differ.
* The CP-8 loan-size condition is still misread at a visible rate (7 of 12 remaining mismatches).
* Scanned documents are not text-redactable; identity cues in images reach only the vision model's numeric extraction.
* Fairness: proxies are not protected classes; the audit cannot see rejected applicants.
