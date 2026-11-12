# E4 · Reliability under fault injection

**Question.** What happens when the world misbehaves — model rate limits, timeouts, corrupted replies, flaky tools, a dead tool server, a process crash — and does the system fail **safely**?

## Method

* **Cases:** 4 (strict policy): two whose correct outcome is *approve* and two *decline*.
* **Cache off**, and fault injection placed **below** the cache, so every call really goes to the network and a cached answer can never hide a fault. See [Fault injection](../concepts/nim-gateway.md#fault-injection).
* **Seven profiles**, four cases each (28 runs), plus a crash/resume test.
* The **550B model is enabled as a fallback** in this experiment only.

### Profiles

| Profile | Injected fault |
|---|---|
| `none` | baseline |
| `429_storm` | 35 % of chat and rerank calls fail with `429 Too Many Requests` |
| `timeouts` | 25 % of chat calls fail with a read timeout |
| `malformed_output` | 30 % of chat replies are replaced by corrupted text with tool calls removed |
| `mcp_flaky` | 30 % of MCP tool calls fail with `503` |
| `research_down` | the `research` MCP server is unavailable |
| `fincalc_down` | the `fincalc` MCP server is unavailable |

### Outcome classes

| Class | Meaning |
|---|---|
| **correct** | recommendation equals the ground truth |
| **safe refer** | the run recommended *refer* when the truth was approve/decline — a human decides |
| **escalated to document review** | the run paused at the human document-review gate before any recommendation |
| **wrongful decline** | declined a case whose correct outcome is not *decline* — harm to the applicant |
| **unsafe approve** | approved a case whose correct outcome is not *approve* — harm to the bank |

## Results

| Profile | Outcome (4 runs) | Latency | Chat calls | Failed calls | Retries | Fallback calls |
|---|---|---|---|---|---|---|
| none | 4 correct | 1.00× | 42 | 0 | 0 | 0 |
| 429 storm | 4 correct | 1.23× | 47 | 3 | 20 | 3 |
| timeouts | 4 correct | 1.24× | 46 | 2 | 13 | 1 |
| malformed output | 1 correct · 1 safe refer · **2 escalated to doc review** | 0.87× | 28 | 0 | 2 | 0 |
| flaky MCP | 1 correct · 3 safe refer | 1.54× | 54 | 0 | 27 | 0 |
| research down | 4 safe refer | 1.23× | 43 | 0 | 24 | 0 |
| fincalc down | 4 safe refer | 1.63× | 49 | 1 | 26 | 1 |

!!! success "Headline"
    **0 unsafe approvals and 0 wrongful declines across all 28 runs.** Every run that completed with a degraded tool recommended *refer*.

### Findings

1. **Transient faults are absorbed.** Under rate-limit storms and timeouts the system produced the correct decision in 4 of 4 runs at about 1.2× latency, using retries (20 and 13) and a handful of fallback calls.
2. **Corrupted output fails safe, not silent.** With 30 % of replies corrupted, three of four runs did *not* reach a confident decision: two stopped at the document-review gate (the extraction was unparseable or failed reconciliation
   even after the repair attempt) and one was downgraded to *refer*. The one run that stayed correct simply received clean replies.
3. **Tool outages degrade to a human.** With a server down the run completes, flags itself *degraded*, lists the missing evidence in the memo and recommends *refer*. The memo validator requires a `limitations` section for every degraded run.

## Crash and resume

The process was "killed" right after the `risk` step and restarted as a new session with the same `thread_id` and **no input**:

| | Nodes |
|---|---|
| Before the crash | `intake`, `parse`, `research`, `analyst`, `risk` |
| After the resume | `risk`, `policy`, `grade`, `policy2`, `memo`, `memo_validator` → paused at `approval` |

`parse`, `research` and `analyst` — the expensive steps — were **not** re-executed. Only the node in flight at the crash (`risk`) ran again (**at-least-once** semantics), and the final recommendation matched the uninterrupted run.

## A bug E4 found

The first E4 run capped degraded runs only against **approving**. With a tool down, "sanctions screening *not performed*" was sometimes judged a failure, so **four correct-approve cases were wrongly *declined***:

| Profile | Case | Correct | System said |
|---|---|---|---|
| flaky MCP | C015 | approve | decline |
| research down | C015, C027 | approve | decline |
| fincalc down | C027 | approve | decline |

An adverse decision caused by a technical outage is as unacceptable as an unsafe approval — it denies an applicant on no real basis. A degraded run now **never auto-decides in either direction**
(`final_recommendation`, with a unit test), and the three degraded profiles were re-run. The pre-fix result is kept in `report/results/ablation_degraded_may_decline/`.

## Caveats

* Four cases per profile; the results show **mechanisms**, not probabilities.
* Latencies are inflated by free-tier throttling and by concurrency; compare profiles with each other, not with production figures.
* The **Retries** column counts NIM request retries from the call log — it includes *real* free-tier `429`s, which were frequent during the later profiles — not MCP tool retries (those are not logged there).
* Faults are injected at the gateway and MCP-call boundaries. Real failure modes (partial outages, slow degradation, correlated failures) are richer.
* The "killed process" is simulated by abandoning the stream and opening a new session, not by `kill -9`.

## Reproduce

```bash
cd experiments
uv run python e4_reliability.py 4                                         # all profiles + crash/resume (cache off: slow)
uv run python e4_reliability.py 4 mcp_flaky,research_down,fincalc_down    # re-run chosen profiles and merge
uv run python e4_outcomes.py                                              # classify outcomes vs ground truth
```
