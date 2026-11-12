# E3 · Fairness and compliance

**Questions.** (a) Does the risk model treat groups differently on real data? (b) Would our audit even *detect* bias if it existed? (c) Do names, gender or ZIP codes
change the system's decisions, and does redaction actually keep them away from the model? (d) Does the memo stay within compliance rules?

## (a) Proxy-group audit on real SBA data

The SBA 7(a) file has **no race, gender or ethnicity fields**, so this audit uses **proxy groups** — census region, business age and legal form. These are
**not legally protected classes**; the experiment shows how the audit works on real data and where model disparities sit.

* **Data:** the test years (FY2017–2019), n = 155,941; **AUC 0.68**.
* **Decision:** decline the riskiest 20 % (PD ≥ 5.3 %).
* **Metrics** (Fairlearn): selection rate, false/true-positive rate, demographic-parity difference (DPD), equalized-odds difference (EOD). Groups under 500 loans are ignored.

| Attribute | Groups | Demographic-parity diff. | Equalized-odds diff. |
|---|---|---|---|
| Census region | 5 | 0.279 | 0.460 |
| Legal form (corporation / individual / partnership) | 3 | 0.249 | 0.302 |
| Business age (young vs established) | 2 | 0.129 | 0.159 |

### Mitigation and its cost

`ThresholdOptimizer` (equalized odds) on **region** — the most disparate attribute:

| | Before | After |
|---|---|---|
| Equalized-odds difference | 0.600 | **0.387** |
| Selection (decline) rate | 20.9 % | **40.1 %** |
| Balanced accuracy | 0.594 | 0.595 |

The gap shrinks and accuracy is unchanged, but the **decline rate nearly doubles** — fairness mitigation is a real trade-off here, not a free improvement.

!!! warning "Selective labels"
    Only *approved* loans appear in the SBA data. Evaluating on funded cases understates disparities, because outcomes for applicants a lender would have
    rejected are never observed. No metric computed here can see them.

## (b) Planted-bias detection

On synthetic data with a known protected attribute `g`, historical approval decisions carry a **planted penalty** on `g = 1`. The model is trained **without** `g` (fairness through
unawareness) but with a feature correlated with it (a neighbourhood-like proxy). A sound audit must flag bias when it exists and not when it does not.

20 seeds per level, n = 20,000, permutation test on the selection-rate gap (200 permutations):

| Planted bias | Demographic-parity diff. (mean ± sd) | Detected (p < 0.05) |
|---|---|---|
| 0.0 | 0.011 ± 0.009 | 15 % (3 of 20 seeds) |
| 0.3 | 0.045 ± 0.014 | 100 % |
| 0.6 | 0.090 ± 0.015 | 100 % |
| 1.0 | 0.146 ± 0.016 | 100 % |

* The audit **detects bias through a proxy at every planted level**, and the parity gap grows monotonically with it.
* The zero-bias false-positive rate (15 %) is above the nominal 5 %: the test flags *any* statistically detectable gap, including the small one created when the model leaks a little of
  the group-correlated proxy. The effect size at zero bias (0.011) is **4× smaller** than at the weakest planted level (0.045), so in practice read the audit on **effect size with a tolerance**,
  not on the p-value alone. (An earlier 5-seed run showed 20 %.)

## (c) Identity counterfactuals

### Design

For 3 cases (strict policy) we built counterfactual applicants with **identical financials, loan and documents** but a different owner name (gender and name origin swapped), business
surname, street and ZIP — changed in the structured fields **and inside the rendered documents** (owner name on statements, on bank memo lines, in the business name). Each of the 9
identities ran through the whole graph with redaction **off** and **on**. The **noise floor** is the original identity re-run *without the cache* (same prompts, fresh calls).

| Metric | Meaning |
|---|---|
| Leak rate | share of LLM chat requests whose text contains an identity token (name, surname, ZIP, street) — measured by a prompt hook in the gateway |
| Decision / rule flips | change versus the original identity, same redaction mode |
| Noise floor | the same case re-run uncached — separates identity effects from ordinary model variation |

### Results

| Redaction | Prompts containing identity | Memos naming/identifying the owner | Decision flips | Rule-status flips | Noise floor (plain re-run) |
|---|---|---|---|---|---|
| **off** | 69 / 88 (**78 %**) | 6 / 9 | 0 / 6 | 2 / 72 (2.8 %) | 1 / 24 (4.2 %) |
| **on** | 0 / 84 (**0 %**) | 0 / 9 | 0 / 6 | 0 / 72 | 0 / 36 |

!!! warning "Read the *on* row carefully"
    With redaction on, each counterfactual's prompts are **byte-identical** to the original's after redaction, so the cache replays the same replies and **zero flips is guaranteed
    by construction** — it is not evidence about the model. The evidence in that arm is the **0 / 84 leak rate** and the **0 / 36 noise floor** (those re-runs had the cache off, so they are
    genuine fresh calls). The informative flip comparison is the *off* arm, where prompts really differ.

### Findings

1. **Redaction works on text.** With it on, no identity token reached any of 84 LLM requests and no memo contained one; without it, 78 % of requests and two-thirds of memos did.
2. **No measurable identity effect on decisions.** Decisions never flipped, and the rule-level flip rate with identity visible (2.8 %) is **indistinguishable from the model's own run-to-run variation (4.2 %)**.
   With 3 cases this cannot exclude small effects. Structurally, decisions come from a fixed rule over rule statuses, and statuses are judged from numbers and policy text — identity can only act through the
   business label.
3. **Memos never used prohibited-basis language** (0 / 9 in either arm).
4. **A different kind of nondeterminism:** one uncached re-run extracted the documents slightly differently, failed reconciliation and was diverted to the human document-review gate. It is
   reported separately (it is not a rule flip) — this is why the table's noise-floor denominator is 24, not 36, in the *off* arm.

### A bug this experiment found

The first version of the redactor matched **substrings**. For an owner named *Mark* it rewrote "market" as "`[OWNER]`et" — corrupting prompts — and the leak meter reported a **3.6 %** false leak rate
on the redaction-on arm. Both are now **whole-word**, with a regression test, and the experiment was re-run. The first result is kept in `report/results/ablation_naive_redaction/`. A direct check confirmed the
bug did not affect E0, E1 or E4 (old and new redaction are identical on all 135 texts they used).

## (d) Compliance

* **Prohibited-basis language:** 0 of 9 memos per arm contained a flagged term.
* **Adverse-action reasons** for declines are *enforced* by the memo validator (a decline must carry reasons that cite failed rules) and unit-tested; their first-pass rate was **not separately measured**.

## Caveats

* (a) uses proxies, not protected classes, and only approved loans.
* (b) is a controlled synthetic setting with a simple proxy; real proxy structure is messier.
* (c) uses 3 cases and one LLM; the redaction-on flip count is zero by construction (see above). Scanned images cannot be text-redacted, so identity in an image reaches the vision model, whose output
  schema is numeric only.

## Reproduce

```bash
cd experiments
uv run python e3_fairness.py                                        # (a)(b): no LLM; ~2 min
CHAT_FALLBACK_MODEL="" uv run python e3_counterfactual.py 3         # (c): LLM
```
