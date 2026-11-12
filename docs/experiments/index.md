# Experiments

WealthPilot was **evaluated against ground truth**, not just built. Five experiments probe the claims the system makes. All scripts are in
`experiments/`; all raw results and tables are in `report/results/`; each arm is also logged as an MLflow run.

| ID | Question | Headline |
|---|---|---|
| [**E0** Policy adherence](e0-policy-adherence.md) | Given a clear policy in prose, does the system apply it correctly — and change its answer when the policy changes? | Decision accuracy **100 %** (strict) / **91.7 %** (lenient); correct policy-flip in **5 of 6** cases; thresholds read correctly **100 %** |
| [**E1** Document parsing](e1-parsing.md) | How accurately are financial statements extracted from clean, messy and scanned PDFs? | **99.5 %** noisy / **96.9 %** scanned field accuracy; layout reconstruction and reconciliation are the key ingredients |
| [**E2** Policy RAG](e2-rag.md) | Which retrieval design finds the right rule? | hybrid + rerank: right rule first **97 %** of the time vs 77 % without the reranker |
| [**E3** Fairness and compliance](e3-fairness.md) | Does the risk model or the LLM treat groups or identities differently? Does redaction work? | planted bias detected at every level; **0** decision flips under identity swaps; redaction leaks **0 / 84** prompts |
| [**E4** Reliability](e4-reliability.md) | What happens when models rate-limit, time out, return garbage, or a tool server dies? | **0 unsafe approvals, 0 wrongful declines** in 28 runs; degraded runs recommend *refer* |

## How to read these results

!!! warning "Small samples, deliberately"
    The free NVIDIA NIM tier delivered roughly 5–15 chat calls per minute and throttled per model, so sample sizes are small
    (E0: 12 cases × 2 policies; E1: 12 cases × 3 variants; E3(c): 3 cases; E4: 4 cases × 7 profiles). Confidence intervals are wide. The results
    demonstrate **mechanisms and failure modes**; they are not precise accuracy estimates for a production system.

* **Ground truth** comes from a deterministic *reference engine* that reads a hidden answer key (`reference.yaml`); agents never see it.
* **Synthetic data** — applicants and documents are generated with known true values; the risk model is trained on real SBA outcomes.
* **Honest reporting** — failures and bugs found by the experiments are documented, and pre-fix results are kept as ablations in
  `report/results/ablation_*`.

## Which code produced which result

The system was hardened while the experiments ran, so results come from slightly different code versions:

| Experiment | Version notes |
|---|---|
| E1, E2, E3 (a)(b) | independent of the later graph changes. E3(b) was re-run with 20 seeds at the end. |
| E0 | the final run uses batched rule judging, numeric verification and the empty-reply guard; two earlier runs are kept (see [E0 history](e0-policy-adherence.md#how-the-result-evolved)). |
| E3 (c) | re-run after the whole-word redaction fix; the first run is kept as an ablation. |
| E4 | `none`, `429 storm`, `timeouts`, `malformed output` and the crash test ran **before** the "degraded never auto-decides" cap; the three degraded profiles ran **after** it (the only ones the cap can affect). |
| Redaction bug vs E0/E1/E4 | checked directly: old and new redaction produce **identical** output on all 135 texts those experiments used, so the bug did not affect them. |

## Shared infrastructure

* **The cache** makes repeated work cheap — except in E4, which disables it and injects faults *below* it.
* **The call log** (`nim_calls`, tagged per experiment arm) provides call counts, retries, fallbacks and token usage.
* **Models:** accuracy experiments run on `nemotron-3.5-lightning-30b` only (`CHAT_FALLBACK_MODEL` empty); E4 enables the 550B model as a fallback.

## Reproducing

```bash
# services running: Postgres, Ollama, MLflow (optional), MCP servers; NIM key set
export NIM_RPM_BUDGET=15 MLFLOW_DISABLE_AGENT_HINT=1
cd experiments
CHAT_FALLBACK_MODEL="" uv run python e0_policy.py 12            # ~1-2 h on the free tier (much faster with a warm cache)
CHAT_FALLBACK_MODEL="" uv run python e1_parsing.py 12
CHAT_FALLBACK_MODEL="" uv run python e2_rag.py
uv run python e3_fairness.py                                     # no LLM
CHAT_FALLBACK_MODEL="" uv run python e3_counterfactual.py 3
uv run python e4_reliability.py 4 && uv run python e4_outcomes.py
```

!!! note
    Results will differ slightly from run to run: models are nondeterministic even at temperature 0, and free-tier model availability changes.
