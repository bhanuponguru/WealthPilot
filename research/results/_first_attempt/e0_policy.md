# E0: end-to-end policy adherence

| policy | cases | decision_acc | decision_CI95 | rule_acc | threshold_acc | tier_acc | grade_acc | failed_runs | degraded_runs | avg_secs |
|---|---|---|---|---|---|---|---|---|---|---|
| strict | 12 | 0.5 | 0.2538-0.7462 | 0.382 | 0.476 | 0.583 | 0.333 | 0 | 0 | 844.0 |
| lenient | 12 | 0.333 | 0.1381-0.6094 | 0.347 | 0.45 | 0.833 | 0.333 | 0 | 0 | 799.5 |

Policy-flip agreement: 0.333 over 6 cases whose correct decision differs between policies (CI95 (0.0968, 0.7)).

## Per-rule accuracy
| rule | correct |
|---|---|
| CP-1 | 8/24 |
| CP-2 | 8/24 |
| CP-3 | 11/24 |
| CP-4 | 10/24 |
| CP-5 | 9/24 |
| CP-6 | 9/24 |
| CP-7 | 9/24 |
| CP-8 | 8/24 |
| CP-9 | 9/24 |
| CP-10 | 6/24 |
| CP-11 | 10/24 |
| CP-12 | 8/24 |

Usage: {'uncached_calls': 1199, 'prompt_tokens': 1291335, 'completion_tokens': 92677, 'calls_per_run': 50.0}
