# E0: end-to-end policy adherence

| policy | cases | decision_acc | decision_CI95 | rule_acc | threshold_acc | tier_acc | grade_acc | failed_runs | degraded_runs | avg_secs |
|---|---|---|---|---|---|---|---|---|---|---|
| strict | 12 | 1.0 | 0.7575-1.0 | 0.972 | 1.0 | 0.917 | 1.0 | 0 | 0 | 411.3 |
| lenient | 12 | 0.917 | 0.6461-0.9851 | 0.944 | 1.0 | 1.0 | 1.0 | 0 | 0 | 397.4 |

Policy-flip agreement: 0.833 over 6 cases whose correct decision differs between policies (CI95 (0.4365, 0.9699)).

## Per-rule accuracy
| rule | correct |
|---|---|
| CP-1 | 24/24 |
| CP-2 | 23/24 |
| CP-3 | 24/24 |
| CP-4 | 24/24 |
| CP-5 | 23/24 |
| CP-6 | 24/24 |
| CP-7 | 24/24 |
| CP-8 | 17/24 |
| CP-9 | 22/24 |
| CP-10 | 24/24 |
| CP-11 | 23/24 |
| CP-12 | 24/24 |

Usage: {'uncached_calls': 131, 'prompt_tokens': 172118, 'completion_tokens': 59687, 'calls_per_run': 5.5}
