# Risk model

The probability-of-default (PD) model is trained on **real outcomes** from the public SBA 7(a) loan dataset
(`wealthpilot.risk.pd_model`). It is deliberately modest: it uses only the loan and business *profile*, because the SBA data contains no
borrower financial statements.

## Data

* **Source:** SBA 7(a) FOIA extract, approval fiscal years 2010–2019 (545,751 loans, 42 columns).
* **No protected attributes:** the file has no race, gender or ethnicity fields. The [fairness audit](../experiments/e3-fairness.md) therefore
  uses *proxy* groups (region, business age, legal form), which are **not** legally protected classes.
* **Excluded:** loans that were cancelled or never disbursed (`CANCLD`, `COMMIT`).

## The label

> **`label = 1` if the loan was charged off within 5 years of approval; otherwise 0** (paid in full *or still active*).

Every FY2010–2019 approval has at least six years of history in the as-of-2026 file, so the label has **no right-censoring**: a still-active
loan is correctly "not defaulted", not "unknown".

!!! failure "Two traps found while building this"
    1. **`TermInMonths` leaks the label.** For charged-off loans it holds the *realised* term (7, 43, 52 months…), while paid loans keep
       their original round term (84, 120, 60). The term column alone scored **AUC 0.95**. It is excluded from the features.
    2. **The file stores "paid in full" as `P I F`** (with spaces), not `PIF` as the data dictionary says. A first check that matched `PIF`
       silently dropped every paid loan and reported a 100 % charge-off rate.

    A first model trained on all terms reported AUC 0.946 — too good to be true — which is what prompted the investigation.

## Features

Known at origination for any applicant, including synthetic ones:

| Feature | Type | Notes |
|---|---|---|
| `log_loan` | numeric | `log1p(max(loan, 1000))` |
| `jobs` | numeric | jobs supported, clipped to 0–200 |
| `franchise` | binary | franchise code present |
| `naics2` | categorical | 2-digit industry sector |
| `business_age` | categorical | the SBA age category, derived from years in business |
| `business_type` | categorical | corporation / individual / partnership |
| `state` | categorical | borrower state |
| `fixed_var` | categorical | fixed or variable rate |
| `collateral` | categorical | collateral pledged (Y/N) |

## Training

* **Model:** LightGBM, up to 400 trees, learning rate 0.05, 31 leaves, early stopping on the calibration year.
* **Temporal split:** train FY2010–2015 (266,226 loans), calibrate FY2016 (56,786), test FY2017–2019 (155,941).
* **Calibration:** isotonic regression fit on the calibration year.
* **Explanations:** SHAP `TreeExplainer`; the top three *risk-increasing* contributions become human-readable reason codes.
* **Registry:** `train-pd` logs metrics and registers the model as `wealthpilot-pd` in MLflow; the serving copy is `models/pd_model.joblib`
  so `fincalc` does not depend on MLflow at runtime.

## Performance

| Metric | Value |
|---|---|
| Test AUC | **0.68** |
| Brier score (calibrated) | 0.0404 (a constant predictor scores 0.0412) |
| Base rate, train / test | 3.7 % / 4.3 % |
| Mean predicted PD, test | 3.9 % |

A modest but real, well-calibrated signal from profile-only features. The PD feeds the [risk grade](decision-rule.md#risk-grade); it does not
replace the policy's ratio rules.

## Scoring an applicant

`fincalc.score_pd` takes the applicant profile, loan amount, term, years in business, NAICS code and whether collateral is pledged, and returns (illustrative values):

```json
{
  "pd": 0.0264,
  "pd_band": "moderate",
  "model_version": "pd-lgbm-v1",
  "reasons": [
    {"feature": "business_age", "reason": "Age of business", "shap": 0.31, "value": "Less than 3 years old but at least 2"}
  ]
}
```

## Limitations

* **Selective labels.** Only *approved* loans appear in the data, so the model says nothing about applicants a lender would have rejected.
* **Profile-only features.** It cannot use the parsed financial ratios; those enter through the policy and the scorecard instead.
* **Different population.** The model is trained on US SBA loans and applied to synthetic applicants. It demonstrates the mechanism, not a
  production-grade credit score.
