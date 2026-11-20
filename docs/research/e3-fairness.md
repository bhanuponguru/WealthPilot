# E3: Fairness and compliance

**Questions.**

* (a) Does the risk model treat groups differently on real data?
* (b) Would the audit detect bias if it existed?
* (c) Do names, gender or ZIP codes change the system's decisions, and does redaction keep them away from the model?
* (d) Does the credit memo stay within compliance rules?

## (a) Proxy-group audit on real SBA data

### Method

The SBA 7(a) file has no race, gender or ethnicity fields, so the audit uses proxy groups: census region, business age and legal form. These
are not legally protected classes. The experiment shows how the audit works on real data and where the model's disparities lie.

* **Data:** the test years (approval fiscal years 2017 to 2019), n = 155,941; the risk model's AUC on this set is 0.68 (0.6813).
* **Decision:** decline the riskiest 20 % of loans (predicted default probability of at least 5.3 %).
* **Metrics** (computed with Fairlearn): selection rate, false-positive and true-positive rate, demographic-parity difference and
  equalized-odds difference. Groups with fewer than 500 loans are ignored.

### Results

| Attribute | Groups | Demographic-parity difference | Equalized-odds difference |
|---|---|---|---|
| Census region | 5 | 0.279 | 0.460 |
| Legal form (corporation, individual, partnership) | 3 | 0.249 | 0.302 |
| Business age (young versus established) | 2 | 0.129 | 0.159 |

### Mitigation and its cost

An equalized-odds threshold optimizer was applied to region, the attribute with the largest equalized-odds difference:

| | Before | After |
|---|---|---|
| Equalized-odds difference | 0.600 | 0.387 |
| Selection (decline) rate | 20.9 % | 40.1 % |
| Balanced accuracy | 0.594 | 0.595 |

The mitigation is fitted on one random half of the test records and evaluated on the other half, so its baseline (0.600) differs from the
audit table (0.460). The equalized-odds difference is sensitive to small groups with extreme rates; the smallest region group (Other, n = 961)
has the highest true-positive rate (0.667).

The gap shrinks and balanced accuracy is unchanged, but the decline rate nearly doubles. Fairness mitigation is a real trade-off here and not a
free improvement.

!!! warning "Selective labels"
    Only approved loans appear in the SBA data. Evaluating on funded loans understates disparities, because outcomes for applicants a lender
    would have rejected are never observed. No metric computed here can see them.

## (b) Planted-bias detection

### Method

On synthetic data with a known protected attribute, historical approval decisions carry a planted penalty against one group. The model is
trained without the protected attribute (fairness through unawareness) but with a feature correlated with it, similar to a
neighborhood variable. A sound audit must flag bias when it exists and not flag it when it does not.

Each bias level uses 20 seeds with n = 20,000. Detection is a permutation test on the selection-rate gap (200 permutations, p < 0.05).

### Results

| Planted bias | Demographic-parity difference (mean, sd) | Detected |
|---|---|---|
| 0.0 | 0.011 (0.009) | 15 % (3 of 20 seeds) |
| 0.3 | 0.045 (0.014) | 100 % |
| 0.6 | 0.090 (0.015) | 100 % |
| 1.0 | 0.146 (0.016) | 100 % |

* The audit detects bias through a proxy at every planted level, and the parity gap grows monotonically with the planted bias.
* The false-positive rate at zero bias (15 %) is above the nominal 5 %. The test flags any statistically detectable gap, including the small
  one created when the model leaks some of the group-correlated proxy. The effect size at zero bias (0.011) is about four times smaller than at
  the weakest planted level (0.045), so the audit should be read on effect size with a tolerance and not on the p-value alone.

## (c) Identity counterfactuals

### Method

For 3 cases (C001, C014 and C028, strict policy), counterfactual applicants were built with identical financials, loan and documents but a
different owner name (gender and name origin swapped), business surname, street and ZIP code. The changes were applied to the structured fields
and inside the rendered documents (owner name on statements and on bank memo lines, and in the business name). Each of the 9 identities (3 originals
and 6 counterfactuals) ran through the whole workflow with redaction off and with redaction on.

| Metric | Meaning |
|---|---|
| Leak rate | Share of language-model requests whose text contains an identity token (name, surname, ZIP or street), measured by a hook on the model gateway. |
| Decision flips and rule flips | Change versus the original identity under the same redaction setting. |
| Noise floor | The original identity rerun without the response cache (same prompts, fresh calls). It separates identity effects from ordinary model variation. |

### Results

| Redaction | Prompts containing identity | Memos identifying the owner | Decision flips | Rule-status flips | Noise floor (plain rerun) |
|---|---|---|---|---|---|
| Off | 69 / 88 (78.4 %) | 6 / 9 | 0 / 6 | 2 / 72 (2.8 %) | 1 / 24 (4.2 %) |
| On | 0 / 84 (0 %) | 0 / 9 | 0 / 6 | 0 / 72 | 0 / 36 |

!!! warning "Reading the redaction-on row"
    With redaction on, each counterfactual's prompts are byte-identical to the original's after redaction, so the response cache replays the
    same replies and zero flips is guaranteed by construction. It is not evidence about the model. The evidence in that arm is the 0 / 84
    leak rate and the 0 / 36 noise floor (those reruns had the cache off and are genuine fresh calls). The informative flip comparison is the
    redaction-off arm, where the prompts differ.

### Findings

1. **Redaction works on text.** With redaction on, no identity token reached any of 84 model requests and no memo contained one. With
   redaction off, 78.4 % of requests and 6 of 9 memos did.
2. **No measurable identity effect on decisions.** Decisions never flipped, and the rule-level flip rate with identity visible (2.8 %) is not
   distinguishable from the model's own run-to-run variation (4.2 %). With 3 cases this cannot exclude small effects. Structurally, decisions
   come from a fixed rule over rule statuses, and statuses are judged from numbers and policy text, so identity can act only through the business name.
3. **Memos did not use prohibited-basis language** (0 of 9 in either arm).
4. **A second kind of nondeterminism.** One uncached rerun in the redaction-off arm extracted the documents slightly differently, failed reconciliation and was
   diverted to the human document-review gate. It is reported separately because it is not a rule flip, and it is the reason the noise-floor denominator in the
   redaction-off arm is 24 and not 36.

### Observed failure mode of an earlier redaction step

The first version of the redaction step matched substrings. For an owner named Mark it rewrote "market" as "[OWNER]et", which corrupted
prompts, and the leak meter reported a false leak rate of 3.6 % (3 of 84 prompts) in the redaction-on arm. The step was changed to whole-word matching and the
experiment was rerun. The first result is in `research/results/ablation_naive_redaction/`. A comparison of the old and new redaction on the
135 texts sent to the model in E0, E1 and E4 found identical output, so those experiments were not affected.

## (d) Compliance

* **Prohibited-basis language:** 0 of 9 memos in each arm contained a flagged term.
* **Adverse-action reasons** for declines are enforced by the memo validator, which requires a decline to carry reasons that cite failed
  rules, and the requirement is unit-tested. The rate at which reasons were complete on the first attempt was not measured separately.

## Limitations

* (a) uses proxy groups and not protected classes, and it covers only approved loans.
* (b) is a controlled synthetic setting with a simple proxy. Real proxy structure is messier.
* (c) uses 3 cases and one model. The redaction-on flip count is zero by construction. Scanned images cannot be text-redacted, so identity in an image
  reaches the vision model, whose output schema is numeric only.
* The compliance profile is an ECOA and Regulation B style example, not legal advice.

See also [Compliance and human approval](../architecture/compliance.md), [Limitations of the evaluation](limitations.md) and
[Reproducing the experiments](reproduce.md).
