# E0: end-to-end policy adherence

| policy | cases | decision_acc | decision_CI95 | rule_acc | threshold_acc | tier_acc | grade_acc | failed_runs | degraded_runs | avg_secs |
|---|---|---|---|---|---|---|---|---|---|---|
| strict | 2 | 1.0 | 0.3424-1.0 | 0.958 | 1.0 | 1.0 | 1.0 | 0 | 0 | 39.7 |
| lenient | 2 | 1.0 | 0.3424-1.0 | 0.917 | 1.0 | 1.0 | 1.0 | 0 | 0 | 42.3 |

Policy-flip agreement: 1.0 over 1 cases whose correct decision differs between policies (CI95 (0.2065, 1.0)).

## Per-rule accuracy
| rule | correct |
|---|---|
| CP-1 | 4/4 |
| CP-2 | 3/4 |
| CP-3 | 4/4 |
| CP-4 | 4/4 |
| CP-5 | 4/4 |
| CP-6 | 4/4 |
| CP-7 | 4/4 |
| CP-8 | 2/4 |
| CP-9 | 4/4 |
| CP-10 | 4/4 |
| CP-11 | 4/4 |
| CP-12 | 4/4 |

Usage: {'uncached_calls': 4, 'prompt_tokens': 7567, 'completion_tokens': 1489, 'calls_per_run': 1.0}
