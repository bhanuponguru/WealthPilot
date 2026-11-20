# E0: Policy adherence

**Question.** Given a clear credit policy written in prose, does the system apply it correctly, and does its decision change when the
policy changes?

WealthPilot is policy-agnostic, so this is the central experiment: what matters is faithful reading and application of whatever policy text
the system is given.

## Method

### Data

* **Cases:** 12 synthetic applicants (C004, C020, C035, C046, C057, C066, C001, C030, C015, C047, C050, C002), selected deterministically
  and stratified: cases whose correct decision differs between the two policies, cases that are declined under both, cases that are
  approved under both, and cases involving a referral.
* **Policies:** the strict and the lenient example policy, 24 runs in total. The policies differ in numbers and in qualitative rules, for
  example in the list of prohibited industries and in the loan-size conditions that trigger the collateral and guarantee rules. See
  [Credit policy and retrieval](../architecture/policy-retrieval.md).
* **Documents:** clean PDFs. Each run stops at the human-approval gate; no human input is supplied.
* **Model:** `nvidia/nemotron-3.5-lightning-30b-a3b`, with no fallback model.

### Ground truth

The reference engine computes every rule status, the risk grade, the recommendation and the required approver tier from a hidden answer key.
The system under test reads only the policy prose. See [The synthetic world](synthetic-data.md).

### Metrics

| Metric | Definition |
|---|---|
| Decision accuracy | The recommendation equals the ground truth. Wilson 95 % interval. |
| Rule accuracy | The per-rule status equals the ground truth, with "not applicable" counted as "pass". Covers rules CP-1 to CP-12 over 24 runs: 288 judgements. |
| Threshold accuracy | The numeric threshold the system extracted from the text equals the policy's value, within 0.5 %. |
| Tier accuracy | The required approver tier equals the ground truth. CP-13 (delegation of authority) is measured through this metric. |
| Grade accuracy | The risk grade equals the ground truth. |
| Policy-flip agreement | Among cases whose correct decision differs between the two policies, the fraction in which the system's decisions are both correct, that is, differ in the correct way. Wilson 95 % interval. |

## Results

| | Strict | Lenient |
|---|---|---|
| Decision accuracy | 100 % (12 of 12; 95 % CI 76-100 %) | 91.7 % (11 of 12; CI 65-99 %) |
| Rule accuracy | 97.2 % | 94.4 % |
| Thresholds read correctly | 100 % | 100 % |
| Approver tier | 91.7 % | 100 % |
| Risk grade | 100 % | 100 % |
| Failed runs / degraded runs | 0 / 0 | 0 / 0 |

Policy-flip agreement is 83 % (5 of 6 cases; 95 % CI 44-97 %).

### Per-rule accuracy

Correct judgements out of 24 runs per rule.

| Rule | Correct | Rule | Correct |
|---|---|---|---|
| CP-1 Operating history | 24 | CP-7 Statement years | 24 |
| CP-2 Prohibited industries | 23 | CP-8 Collateral | 17 |
| CP-3 Minimum DSCR | 24 | CP-9 Personal guarantee | 22 |
| CP-4 Maximum leverage | 24 | CP-10 Sanctions | 24 |
| CP-5 Minimum liquidity | 23 | CP-11 Adverse media | 23 |
| CP-6 Loan-to-revenue | 24 | CP-12 Acceptable grade | 24 |

## Observed failure modes

Twelve of 288 rule judgements disagreed with the ground truth.

| Count | Rule | Observed error |
|---|---|---|
| 7 | CP-8 collateral | The rule applies only to loans above a size (USD 150,000 under the strict policy, USD 400,000 under the lenient policy). The model repeatedly misread this loan-size condition, for example stating that "USD 117,000 is below the USD 150,000 threshold, but the policy states that requests above..." and then judging the rule as failed. This produced 5 wrong failures and 2 missing-data results, the latter after the numeric re-check could not reconcile the model's comparisons. |
| 2 | CP-9 guarantee | A wrong pass on a conditional requirement. |
| 1 | CP-2 | Cryptocurrency exchange treated as prohibited under the lenient policy, which prohibits only cannabis and adult entertainment. |
| 1 | CP-5 | A current ratio of 0.9956 passed against a minimum of 1.00. |
| 1 | CP-11 | An unsupported fact. For a business whose only press coverage was a positive article (a small-business award) and whose adverse-media severity in the case data was none, the model asserted a medium-severity adverse-media finding. This is the only error that is not a policy-reading error. |

Several rule-level errors did not change the decision, for example a wrong CP-8 failure on a case that is declined because of other failed rules. Decision accuracy (91.7 % to 100 %) is therefore higher than rule accuracy (94.4 % to 97.2 %). The safeguards in
[the decision rule](../architecture/decision-rule.md) convert most remaining doubts into a referral rather than a wrong approval or decline.

## Ablation: numeric verification

The run before numeric verification was added (batched rule judging, no verification of the model's comparisons) gave these results:

| | Strict | Lenient |
|---|---|---|
| Decision accuracy | 91.7 % | 66.7 % |
| Rule accuracy | 95.8 % | 92.4 % |
| Policy-flip agreement | 33 % (CI 10-70 %) | |

That run had 17 rule mismatches. Nine were on CP-8 (15 of 24 correct), mostly comparisons of the loan amount with the size threshold, for
example judging that USD 132,000 is above USD 150,000. Two were invalid-JSON errors in rule judging.

Numeric verification requires the model to list every comparison it relied on. The comparisons are re-evaluated outside the model, and a
disagreement triggers a targeted re-ask. With it, decision accuracy rises by 8.3 points under the strict policy and by 25 points under
the lenient policy, and policy-flip agreement rises from 33 % to 83 %. See [Credit policy and retrieval](../architecture/policy-retrieval.md).
Results are in `research/results/ablation_no_numeric_verify/`.

## Experimental versions

| Run | Strict decision | Lenient decision | Rule accuracy (strict / lenient) | Model calls per run | Description |
|---|---|---|---|---|---|
| 1. First complete run | 50 % | 33 % | 38.2 % / 34.7 % | 50.0 | One agent loop per rule. The response cache replayed empty model replies, which appeared mostly as missing-data results (132 of 183 mismatches). The run reflects this infrastructure defect and not policy reading; it is retained for completeness and supports no conclusion. |
| 2. Batched judging, no verification | 91.7 % | 66.7 % | 95.8 % / 92.4 % | 5.7 | Batched rule judging with retrieval performed outside the model. |
| 3. Reported run | 100 % | 91.7 % | 97.2 % / 94.4 % | 5.5 | Adds numeric verification and the re-ask step. |

The reported run used 131 uncached model calls (172,118 prompt tokens and 59,687 completion tokens). Results of run 1 are in
`research/results/_first_attempt/`.

## Interpretation

Under both policies the system extracts every threshold correctly and applies nearly every rule correctly, and its decision changes with the
policy in the correct direction in five of six cases where it should. The remaining errors concentrate on one construct: a rule whose
applicability depends on a numeric condition in the text (CP-8, and to a lesser extent CP-9). The one unsupported fact (CP-11) shows that the
model can assert evidence that is not in the case data.

## Limitations

* There are 12 cases per policy; the lenient-policy interval (65-99 %) and the flip-agreement interval (44-97 %) are wide.
* The ground truth is computed by the project's own reference engine, which encodes the authors' reading of the policy text. The policies
  and the engine were written together, so the experiment tests consistent application of explicit rules, not the discovery of ambiguity.
* Run-to-run variation exists even at temperature 0. In [E3](e3-fairness.md) a plain uncached rerun changed 1 of 24 rule statuses.
* The average run time in the results (411.3 s and 397.4 s) reflects free-tier throttling and four concurrent cases, not the intrinsic
  speed of the system.

See also [Limitations of the evaluation](limitations.md) and [Reproducing the experiments](reproduce.md).
