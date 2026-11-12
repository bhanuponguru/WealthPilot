# E4: reliability under fault injection (cache off)

| profile | runs | completed | decision_correct | unsafe_approves | degraded_runs | degraded_auto_approved | avg_secs | latency_x | chat_calls | failed_calls | retries | fallback_calls | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 361.4 | 1.0 | 42 | 0 | 0 | 0 | 66912 |
| 429_storm | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 446.2 | 1.23 | 47 | 3 | 20 | 3 | 68248 |
| timeouts | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 448.3 | 1.24 | 46 | 2 | 13 | 1 | 63741 |
| malformed_output | 4 | 4/4 | 1/4 | 0 | 0 | 0 | 314.7 | 0.87 | 28 | 0 | 2 | 0 | 40922 |
| mcp_flaky | 4 | 4/4 | 2/4 | 0 | 4 | 0 | 499.0 | 1.38 | 53 | 0 | 1 | 0 | 78171 |
| research_down | 4 | 4/4 | 2/4 | 0 | 4 | 0 | 488.2 | 1.35 | 40 | 0 | 21 | 0 | 61843 |
| fincalc_down | 4 | 4/4 | 2/4 | 0 | 4 | 0 | 589.9 | 1.63 | 48 | 0 | 16 | 0 | 71459 |

## Crash and resume
- case C015: nodes before crash ['intake', 'parse', 'research', 'analyst', 'risk']; after resume ['risk', 'policy', 'grade', 'policy2', 'memo', 'memo_validator']; re-ran already-completed nodes: ['risk']; resumed to `approval`; recommendation approve