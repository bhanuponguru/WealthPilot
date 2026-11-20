# E0: end-to-end policy adherence

| policy | cases | decision_acc | decision_CI95 | rule_acc | threshold_acc | tier_acc | grade_acc | failed_runs | degraded_runs | avg_secs |
|---|---|---|---|---|---|---|---|---|---|---|
| strict | 12 | 0.917 | 0.6461-0.9851 | 0.958 | 1.0 | 0.917 | 1.0 | 0 | 0 | 438.5 |
| lenient | 12 | 0.667 | 0.3906-0.8619 | 0.924 | 1.0 | 1.0 | 1.0 | 0 | 0 | 440.4 |

Policy-flip agreement: 0.333 over 6 cases whose correct decision differs between policies (CI95 (0.0968, 0.7)).

## Per-rule accuracy
| rule | correct |
|---|---|
| CP-1 | 23/24 |
| CP-2 | 24/24 |
| CP-3 | 23/24 |
| CP-4 | 24/24 |
| CP-5 | 23/24 |
| CP-6 | 24/24 |
| CP-7 | 24/24 |
| CP-8 | 15/24 |
| CP-9 | 22/24 |
| CP-10 | 24/24 |
| CP-11 | 23/24 |
| CP-12 | 22/24 |

Usage: {'uncached_calls': 137, 'prompt_tokens': 167097, 'completion_tokens': 49913, 'calls_per_run': 5.7}
