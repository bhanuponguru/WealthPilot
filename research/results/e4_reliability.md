# E4: reliability under fault injection (cache off)

| profile | runs | completed | decision_correct | unsafe_approves | degraded_runs | degraded_auto_approved | avg_secs | latency_x | chat_calls | failed_calls | retries | fallback_calls | tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| none | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 361.4 | 1.0 | 42 | 0 | 0 | 0 | 66912 |
| 429_storm | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 446.2 | 1.23 | 47 | 3 | 20 | 3 | 68248 |
| timeouts | 4 | 4/4 | 4/4 | 0 | 0 | 0 | 448.3 | 1.24 | 46 | 2 | 13 | 1 | 63741 |
| malformed_output | 4 | 4/4 | 1/4 | 0 | 0 | 0 | 314.7 | 0.87 | 28 | 0 | 2 | 0 | 40922 |
| mcp_flaky | 4 | 4/4 | 1/4 | 0 | 3 | 0 | 555.1 | 1.54 | 54 | 0 | 27 | 0 | 81340 |
| research_down | 4 | 4/4 | 0/4 | 0 | 4 | 0 | 444.6 | 1.23 | 43 | 0 | 24 | 0 | 65696 |
| fincalc_down | 4 | 4/4 | 0/4 | 0 | 4 | 0 | 587.8 | 1.63 | 49 | 1 | 26 | 1 | 74121 |

## Crash and resume
- case C015: nodes before crash ['intake', 'parse', 'research', 'analyst', 'risk']; after resume ['risk', 'policy', 'grade', 'policy2', 'memo', 'memo_validator']; re-ran already-completed nodes: ['risk']; resumed to `approval`; recommendation approve

## Outcome classification (vs ground truth)
| profile | runs | correct | safe_refer | escalated_doc_review | wrongful_decline | unsafe_approve |
|---|---|---|---|---|---|---|
| none | 4 | 4 | 0 | 0 | 0 | 0 |
| 429_storm | 4 | 4 | 0 | 0 | 0 | 0 |
| timeouts | 4 | 4 | 0 | 0 | 0 | 0 |
| malformed_output | 4 | 1 | 1 | 2 | 0 | 0 |
| mcp_flaky | 4 | 1 | 3 | 0 | 0 | 0 |
| research_down | 4 | 0 | 4 | 0 | 0 | 0 |
| fincalc_down | 4 | 0 | 4 | 0 | 0 | 0 |
