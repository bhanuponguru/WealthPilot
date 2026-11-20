# Research overview

This section reports an evaluation of WealthPilot against ground truth. It is written as a self-contained research report in
reference-manual form: each experiment page states the question, method, data, metrics, results with confidence intervals,
interpretation and limitations.

!!! note "The research package is separate from the product"
    The evaluation lives in its own package (`research/`), distinct from the deployed product. The package contains the synthetic-data
    generator, the reference engine that holds the ground truth, and the experiment runners. The product contains none of this
    code and none of the answer keys, and no product page depends on it. The package produces the optional demonstration data that the
    product can load as plain files (see [The synthetic world](synthetic-data.md)).

## Experiments

| ID | Question | Page |
|---|---|---|
| E0 Policy adherence | Given a clear credit policy in prose, does the system apply it correctly, and does its decision change when the policy changes? | [E0](e0-policy-adherence.md) |
| E1 Document parsing | How accurately are financial statements extracted from clean, noisy-layout and scanned PDFs, and what does each pipeline component contribute? | [E1](e1-parsing.md) |
| E2 Policy retrieval | Which retrieval design most reliably finds the policy rule that answers a question? | [E2](e2-rag.md) |
| E3 Fairness and compliance | Does the risk model treat groups differently, would an audit detect planted bias, do identity attributes change decisions, and does redaction keep them from the model? | [E3](e3-fairness.md) |
| E4 Reliability | What happens under rate limits, timeouts, corrupted replies, flaky tools, a dead tool server and a process crash? | [E4](e4-reliability.md) |

Supporting pages: [The synthetic world](synthetic-data.md), [Limitations of the evaluation](limitations.md) and
[Reproducing the experiments](reproduce.md).

## Headline results

| Experiment | Result |
|---|---|
| E0 | Decision accuracy 100 % under the strict policy (12 of 12; 95 % CI 76-100 %) and 91.7 % under the lenient policy (11 of 12; CI 65-99 %). Policy-flip agreement 83 % (5 of 6; CI 44-97 %). Thresholds read correctly from the policy text in 100 % of cases. |
| E1 | Field accuracy of the full parsing pipeline: 100 % on clean, 100 % on noisy-layout and 96.9 % on scanned documents (608 field values per cell). Reconstructing the table layout is the decisive step for noisy documents. |
| E2 | Hybrid retrieval with a reranker returns the correct rule first in 97.1 % of 104 queries, against 76.9 % for hybrid retrieval without the reranker. |
| E3 | Planted bias is detected at every planted level (100 % of 20 seeds at each of three levels, 15 % false-positive rate at zero bias). No decision changed under identity swaps (0 of 6). With redaction on, 0 of 84 model requests contained an identity token, against 69 of 88 with redaction off. |
| E4 | 0 unsafe approvals and 0 wrongful declines in 28 fault-injected runs. Every run that completed with a degraded tool recommended referral to a human. |

## Method common to all experiments

**Ground truth.** A deterministic reference engine computes the correct outcome for every synthetic applicant under each credit
policy. It reads a hidden, machine-readable answer key that holds the same thresholds as the policy prose. The system under test
never has access to the key: it must extract every threshold from the prose.

**Synthetic applicants and documents.** Applicants, financial statements, bank statements, loan requests and planted sanctions and
adverse-media cases are generated with known true values, so extraction and decision accuracy can be measured exactly. See
[The synthetic world](synthetic-data.md).

**Risk model.** The default-risk model is trained on real SBA 7(a) loan outcomes (label: charged off within five years of approval; training on
approval fiscal years 2010-2015, calibration on 2016, test on 2017-2019). Its test-set AUC is 0.68 (n = 155,941). The fairness audit in
[E3](e3-fairness.md) evaluates this model on real data.

**Models and components.** The accuracy experiments (E0 to E3) use one chat model, `nvidia/nemotron-3.5-lightning-30b-a3b`, with no
fallback model. Scanned pages are read by a vision model, retrieval uses a hosted reranker, and embeddings come from a local model
(`nomic-embed-text`). E4 additionally enables the `nvidia/nemotron-3-ultra-550b-a55b` model as a fallback. All hosted models are
free-tier NVIDIA NIM endpoints.

**Small samples.** The free model tier throttles requests per model, which bounds the number of end-to-end runs. Sample sizes are
therefore small: E0 uses 12 cases under 2 policies, E1 uses 12 applicants in 3 document variants, E3(c) uses 3 cases and E4 uses 4 cases
under 7 fault profiles. Every rate is reported with a 95 % confidence interval where one is meaningful: Wilson intervals for proportions
(E0, E1) and a 2,000-resample bootstrap for the mean reciprocal rank in E2. The intervals are wide, and the results demonstrate mechanisms
and failure modes rather than precise accuracy estimates for a production system.

**Repeatability.** Models are nondeterministic even at temperature 0, and free-tier availability changes. A rerun reproduces the
mechanisms but not necessarily every count. See [Limitations of the evaluation](limitations.md).

## Experimental versions and re-runs

The system under test was modified between some experiments. The table states which result was produced before or after which system
change. Earlier runs are kept in `research/results/` under the names shown.

| Experiment | Versions and ordering |
|---|---|
| E2, E1 | Run first. Independent of the later workflow changes. |
| E0 | Three runs in order. (1) First complete run (`_first_attempt`): per-rule agent loops with 50 model calls per run; the response cache replayed empty model replies, so most mismatches are missing-data results (132 of 183) and the run measures an infrastructure defect, not policy reading. (2) Batched rule judging with retrieval performed outside the model, without numeric verification (`ablation_no_numeric_verify`). (3) The reported run, which adds numeric verification and the re-ask step. See [E0](e0-policy-adherence.md). |
| E3(c) | Two runs in order. The first used a redaction step that matched substrings (`ablation_naive_redaction`) and reported a 3.6 % leak rate with redaction on. The reported run uses whole-word matching. A comparison of old and new redaction on the 135 texts that E0, E1 and E4 sent to the model found identical output, so the earlier behavior did not affect those experiments. |
| E3(a)(b) | Run last; (b) uses 20 seeds per bias level. Independent of the workflow changes. |
| E4 | Two runs in order. The first applied the safety cap on degraded runs only against approval (`ablation_degraded_may_decline`). The reported run applies it in both directions: a degraded run never auto-decides. The baseline, rate-limit storm, timeout and corrupted-output profiles and the crash test were run before the change and were not repeated: their rows are identical in both result sets. Only the three profiles with degraded tools were rerun. See [E4](e4-reliability.md). |

## Selecting the language model

The default chat model is `nvidia/nemotron-3.5-lightning-30b-a3b`. After the experiments above, a probe and a small comparison were
run to check whether another available model should replace it. Raw results are in `research/results/nim_probe.json` and
`research/results/model_compare/`.

### Availability probe

The probe sent two small requests to each of 54 chat models listed in the provider catalog: a tool-calling request that must return a
correct tool call, and a plain question with a checkable answer.

| Outcome | Models |
|---|---|
| Answered both probes correctly | 11 |
| Answered, but failed the tool-calling probe | 1 (`nvidia/ising-calibration-1.5-31b`) |
| Returned 404 (not available for the account) | 37 |
| Not reachable during the probe | 5 (3 name-resolution failures, 2 read timeouts at 60 s) |

The 11 models that answered both probes, with latency of the two probe requests in seconds:

| Model | Tool call | Question |
|---|---|---|
| `nvidia/nemotron-3.5-bolt-e4b` | 0.8 | 0.2 |
| `poolside/laguna-xs-2.1` | 0.9 | 0.5 |
| `nvidia/nemotron-3-ultra-550b-a55b` | 1.6 | 1.5 |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 3.3 | 1.0 |
| `nvidia/nemotron-3.5-lightning-30b-a3b` (default) | 3.2 | 2.5 |
| `minimaxai/minimax-m3.1-flash` | 3.9 | 3.9 |
| `mistralai/mistral-large-4-1t-a52b` | 1.2 | 10.1 |
| `meta/muse-glimmer-30b` | 16.2 | 9.7 |
| `stepfun-ai/step-5-preview` | 2.0 | 27.1 |
| `openai/gpt-oss-20b` | 42.4 | 44.0 |
| `google/gemma-4-31b-it` | 45.2 | 55.8 |

Short-probe latency is a weak indicator of latency inside the pipeline, where prompts are much longer.

### End-to-end comparison

A reduced E0 (2 cases, C004 and C001, under both policies) was run for candidate models:

| Model | Decision accuracy (strict / lenient) | Rule accuracy (strict / lenient) | Uncached model calls | Mismatches |
|---|---|---|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` (default) | 100 % / 100 % (CI 34-100 %) | 95.8 % / 91.7 % | 4 | 3 (CP-8 twice, CP-2 once) |
| `poolside/laguna-xs-2.1` | 100 % / 100 % (CI 34-100 %) | 95.8 % / 95.8 % | 40 | 2 (both CP-8) |

The run for `minimaxai/minimax-m3.1-flash` was aborted and produced no results. Both completed runs had 0 failed and 0 degraded runs and agreed with
the reference on the one policy-flip case. The comparison is not like-for-like in latency: the default model's run was served almost entirely from the
response cache (4 uncached calls, against 40 for the other model), so its average run time (39.7 s and 42.3 s) is not comparable with the
other model's (194.7 s and 187.8 s).

With 2 cases the comparison cannot rank the models. It shows that the second model completes the task and reproduces the same class of
CP-8 loan-size errors as the default. The default remains `nvidia/nemotron-3.5-lightning-30b-a3b`; the second model is a candidate for further
evaluation, not a demonstrated improvement.
