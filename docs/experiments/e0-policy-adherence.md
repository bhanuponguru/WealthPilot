# E0 · Policy adherence

**Question.** Given a clear credit policy written in prose, does the system apply it correctly — and does its decision *change* when the policy
changes?

This is the central experiment: WealthPilot is policy-agnostic, so what matters is faithful reading and application of whatever text it is handed.

## Method

* **Cases:** 12 synthetic applicants (`C004, C020, C035, C046, C057, C066, C001, C030, C015, C047, C050, C002`), chosen deterministically and stratified:
  cases whose correct decision *differs* between the two policies, both-decline, both-approve, and cases involving *refer*.
* **Policies:** *strict* and *lenient* (see [Credit policy and RAG](../concepts/policy-rag.md#the-two-example-policies)) — 24 runs.
* **Documents:** clean PDFs. Runs stop at the human-approval gate; no human input.
* **Ground truth:** the hidden reference engine computes every rule status, the grade, the recommendation and the approver tier.
* **Hidden answer key:** agents read only the policy prose.

### Metrics

| Metric | Definition |
|---|---|
| Decision accuracy | recommendation equals ground truth |
| Rule accuracy | per-rule status equals ground truth (`not_applicable` counted as `pass`), over 12 rules × 24 runs = 288 judgements |
| Threshold accuracy | the numeric threshold the agent extracted from the text equals the policy's value (±0.5 %) |
| Tier / grade accuracy | required approver tier / risk grade equals ground truth |
| **Policy-flip agreement** | among cases whose correct decision differs between the two policies, the fraction where the system's decisions differ the same, correct way |

## Results

| | Strict | Lenient |
|---|---|---|
| Decision accuracy | **100 %** (12/12; 95 % CI 76–100 %) | **91.7 %** (11/12; CI 65–99 %) |
| Rule accuracy | 97.2 % | 94.4 % |
| Thresholds read correctly | 100 % | 100 % |
| Approver tier | 91.7 % | 100 % |
| Risk grade | 100 % | 100 % |
| Failed or degraded runs | 0 / 0 | 0 / 0 |

**Policy-flip agreement: 83 % (5 of 6)** — 95 % CI 44–97 %.

### Per-rule accuracy (24 runs each)

| Rule | Correct | Rule | Correct |
|---|---|---|---|
| CP-1 Operating history | 24 | CP-7 Statement years | 24 |
| CP-2 Prohibited industries | 23 | **CP-8 Collateral** | **17** |
| CP-3 Minimum DSCR | 24 | CP-9 Personal guarantee | 22 |
| CP-4 Maximum leverage | 24 | CP-10 Sanctions | 24 |
| CP-5 Minimum liquidity | 23 | CP-11 Adverse media | 23 |
| CP-6 Loan-to-revenue | 24 | CP-12 Acceptable grade | 24 |

## What went wrong (12 of 288 judgements)

| Count | Rule | Error |
|---|---|---|
| 7 | **CP-8** collateral | The rule applies only to loans above a size (USD 150,000 strict; 400,000 lenient). The model repeatedly **misread that loan-size condition** — e.g. "USD 117,000 is below the USD 150,000 threshold, but the policy states that requests above…" — producing 5 wrong `fail`s and 2 `missing_data` after the numeric re-check could not reconcile its comparisons. |
| 2 | CP-9 guarantee | wrong pass on a conditional requirement |
| 1 | CP-2 | cryptocurrency treated as prohibited under the **lenient** policy (which prohibits only cannabis and adult entertainment) |
| 1 | CP-5 | a current ratio of 0.9956 passed against a 1.00 minimum |
| 1 | **CP-11** | a **hallucinated fact**: for a business whose only coverage was a positive article (a small-business award), the model asserted a "medium severity adverse media finding" and escalated. The facts said `none`. This is the one error that is not a policy-reading error. |

!!! info "Decisions are more robust than rules"
    Several rule-level errors did not change the decision (for example a wrong `fail` on CP-8 for a case that was declined anyway for another reason).
    Decision accuracy (91.7–100 %) is higher than rule accuracy (94–97 %) for that reason, and the safeguards in [the decision rule](../concepts/decision-rule.md)
    turn most remaining doubts into *refer* rather than a wrong approve or decline.

## Ablation: numeric verification

After batching, the first complete run had **no numeric verification**. Its results:

| | Strict | Lenient |
|---|---|---|
| Decision accuracy | 91.7 % | 66.7 % |
| Rule accuracy | 95.8 % | 92.4 % |
| Policy-flip agreement | 33 % | |

9 of its 17 mismatches were **arithmetic comparison errors** by the model (for example treating `132,000` as greater than `150,000`). Adding the
requirement that the model list every comparison it relied on — which code re-evaluates, triggering a targeted re-ask — brought the results to the
table above: **+8.3 points** strict, **+25 points** lenient, and flip agreement from 33 % to 83 %. See
[numeric verification](../concepts/policy-rag.md#numeric-verification). Files: `report/results/ablation_no_numeric_verify/`.

## How the result evolved

| Stage | Strict decision | Lenient decision | Rule accuracy (S / L) | Why |
|---|---|---|---|---|
| 1. First run | 50 % | 33 % | 38 % / 35 % | an **empty-reply cache bug** replayed empty model answers, mostly as `missing_data` (it measured infrastructure noise, not policy reading) |
| 2. Batched judging, no verification | 91.7 % | 66.7 % | 96 % / 92 % | per-rule agent loops replaced by batched judging with code-side retrieval |
| 3. **Final** | **100 %** | **91.7 %** | 97 % / 94 % | + numeric verification and re-ask |

Stage 1 is kept in `report/results/_first_attempt/` as a reminder that **an experiment can measure your infrastructure instead of your system.**

## Caveats

* 12 cases per policy; the lenient interval (65–99 %) is wide.
* The correct answer under each policy is computed by *our own* reference engine, which encodes our reading of the policy text. The policies and the
  engine were written together, so this tests consistent application of explicit rules rather than discovery of ambiguity.
* Run-to-run variation exists even at temperature 0 (see [E3](e3-fairness.md#c-identity-counterfactuals): a plain re-run changed 1 of 24 rule statuses).
* The per-run time shown in `e0_policy.md` (about 400 s) reflects free-tier throttling and four concurrent cases, not the system's intrinsic speed.

## Reproduce

```bash
cd experiments && CHAT_FALLBACK_MODEL="" uv run python e0_policy.py 12
```

Outputs: `report/results/e0_policy.json` (including every mismatch with the agent's reason) and `e0_policy.md`.
