# E3 (a)(b): fairness audit

## (a) Proxy-group audit on real SBA test data (FY2017-19; decline = riskiest 20%)
AUC 0.6813, n=155941, decision threshold PD>=0.0534. Proxy groups are NOT protected classes.

| attribute | DPD | EO_diff | groups |
|---|---|---|---|
| region | 0.2789 | 0.4596 | 5 |
| age_group | 0.129 | 0.1585 | 2 |
| business_type | 0.2486 | 0.3021 | 3 |

Mitigation (ThresholdOptimizer, equalized odds) on `region`: {'attribute': 'region', 'before_eo_diff': 0.5995, 'after_eo_diff': 0.387, 'before_selection_rate': 0.2089, 'after_selection_rate': 0.4011, 'before_balanced_acc': 0.594, 'after_balanced_acc': 0.5948}

## (b) Planted-bias detection (synthetic; model never sees the protected attribute)
| bias | dpd | dpd_sd | eod | detected |
|---|---|---|---|---|
| 0.0 | 0.0112 | 0.0086 | 0.0162 | 0.15 |
| 0.3 | 0.0451 | 0.0143 | 0.0545 | 1.0 |
| 0.6 | 0.0902 | 0.0153 | 0.1278 | 1.0 |
| 1.0 | 0.1459 | 0.0164 | 0.2336 | 1.0 |
