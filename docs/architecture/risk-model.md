# Risk model

The probability-of-default model is trained on real outcomes from the public SBA 7(a) loan dataset. It is deliberately modest: it
uses only the loan and business profile, because the dataset contains no borrower financial statements.

## Data

* **Source.** The SBA 7(a) FOIA extract for approval fiscal years 2010 to 2019.
* **No protected attributes.** The file has no race, gender or ethnicity fields. The [fairness evaluation](../research/e3-fairness.md)
  therefore uses proxy groups such as region, business age and legal form, which are not legally protected classes.
* **Excluded.** Loans that were cancelled or never disbursed.

## The label

A loan is labeled 1 if it was charged off within five years of approval, and 0 otherwise (paid in full or still active).

Every approval in the covered years has at least six years of history in the extract, so the label has no right-censoring: a
still-active loan is correctly "not defaulted", not "unknown".

!!! warning "Fields that must not be features"
    The term-in-months field holds the realized term for charged-off loans and the original round term for paid loans, so it
    reveals the label on its own. It is excluded from the features, and the sample is not filtered on it.

## Features

All features are known at origination for any applicant.

| Feature | Type | Notes |
|---|---|---|
| Loan amount | Numeric | Logarithm of the amount, with a floor of $1,000 |
| Jobs supported | Numeric | Clipped to 0 to 200 |
| Franchise | Binary | Whether a franchise code is present |
| Industry sector | Categorical | Two-digit NAICS sector |
| Business age | Categorical | The SBA age category, derived from years in business |
| Legal form | Categorical | Corporation, individual or partnership |
| State | Categorical | Borrower state |
| Rate type | Categorical | Fixed or variable |
| Collateral | Categorical | Whether collateral is pledged |

## Training

* **Model.** LightGBM gradient-boosted trees: up to 400 trees, learning rate 0.05, 31 leaves, with early stopping on the calibration
  year.
* **Temporal split.** Train on approval years 2010 to 2015 (266,226 loans), calibrate on 2016 (56,786) and test on 2017 to 2019
  (155,941).
* **Calibration.** Isotonic regression fitted on the calibration year.
* **Explanations.** SHAP values from the tree model. The top three risk-increasing contributions become human-readable reasons.
* **Registry and serving.** The training command logs metrics and registers the model as `wealthpilot-pd` in MLflow. The serving copy
  is the file in the `artifacts/` folder, so the tool server does not depend on MLflow at run time.

The trained model and its metrics ship with the product. Retraining is optional and needs the SBA extract in the `data/` folder:

```bash
docker compose exec console wealthpilot train-pd
```

## Performance

| Metric | Value |
|---|---|
| Test AUC | 0.68 |
| Brier score, calibrated | 0.0404 |
| Base rate, train and test | 3.7 percent and 4.3 percent |
| Mean predicted probability, test | 3.9 percent |

The model offers a modest but real signal from profile-only features, and its probabilities are well calibrated on the test years. The
probability feeds the [risk grade](decision-rule.md#risk-grade). It does not replace the policy's ratio rules.

## Scoring an applicant

The scoring tool takes the applicant profile (state, legal form, rate type, jobs supported, franchise), the loan amount, the term,
years in business, the NAICS code and whether collateral is pledged. It returns the calibrated probability, the probability band, the
model version and the top reasons. The values below are illustrative:

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

* **Selective labels.** Only approved loans appear in the data, so the model says nothing about applicants a lender would have
  rejected.
* **Profile-only features.** The model cannot use the parsed financial ratios. They enter through the policy rules and the scorecard
  instead.
* **Different population.** The model is trained on US SBA loans. Applied to another portfolio it demonstrates the mechanism and
  is not a production-grade credit score.
