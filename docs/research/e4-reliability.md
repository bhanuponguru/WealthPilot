# E4: Reliability under fault injection

**Question.** What happens when the environment misbehaves (model rate limits, timeouts, corrupted replies, flaky tools, a dead tool
server, a process crash), and does the system fail safely?

## Method

### Data

* **Cases:** 4 cases under the strict policy: C015 and C027, whose correct outcome is approve, and C001 and C008, whose correct outcome is
  decline.
* **Cache off.** Faults are injected below the response cache, so every call reaches the network and a cached answer can never hide a fault.
  See [Model gateway](../architecture/model-gateway.md).
* **Seven fault profiles**, each run on all four cases (28 runs), plus a crash and resume test.
* **Fallback model:** the `nvidia/nemotron-3-ultra-550b-a55b` model is enabled as a fallback in this experiment only.

### Fault profiles

| Profile | Injected fault |
|---|---|
| Baseline | None. |
| Rate-limit storm | 35 % of chat and rerank calls fail with `429 Too Many Requests`. |
| Timeouts | 25 % of chat calls fail with a read timeout. |
| Corrupted output | 30 % of chat replies are replaced by corrupted text with the tool calls removed. |
| Flaky tool calls | 30 % of tool-server calls fail with `503`. |
| Research server down | The research tool server is unavailable. |
| Calculation server down | The financial-calculation tool server is unavailable. |

### Outcome classes

| Class | Meaning |
|---|---|
| Correct | The recommendation equals the ground truth. |
| Safe refer | The run recommended referral although the truth was approve or decline, so a human decides. |
| Escalated to document review | The run paused at the human document-review gate before any recommendation. |
| Wrongful decline | The run declined a case whose correct outcome is not decline: harm to the applicant. |
| Unsafe approve | The run approved a case whose correct outcome is not approve: harm to the bank. |

## Results

| Profile | Outcome (4 runs) | Latency | Chat calls | Failed calls | Retries | Fallback calls |
|---|---|---|---|---|---|---|
| Baseline | 4 correct | 1.00x | 42 | 0 | 0 | 0 |
| Rate-limit storm | 4 correct | 1.23x | 47 | 3 | 20 | 3 |
| Timeouts | 4 correct | 1.24x | 46 | 2 | 13 | 1 |
| Corrupted output | 1 correct, 1 safe refer, 2 escalated to document review | 0.87x | 28 | 0 | 2 | 0 |
| Flaky tool calls | 1 correct, 3 safe refer | 1.54x | 54 | 0 | 27 | 0 |
| Research server down | 4 safe refer | 1.23x | 43 | 0 | 24 | 0 |
| Calculation server down | 4 safe refer | 1.63x | 49 | 1 | 26 | 1 |

Across all 28 runs there were 0 unsafe approvals and 0 wrongful declines. All 28 runs completed. Every run in which a tool was degraded
(3 of 4 runs under flaky tool calls, and all 4 under each server outage) recommended referral, and none was auto-approved.

### Findings

1. **Transient faults are absorbed.** Under rate-limit storms and timeouts the system produced the correct decision in 4 of 4 runs at about
   1.2 times the baseline latency, using retries (20 and 13) and a few fallback calls (3 and 1).
2. **Corrupted output fails safe and not silently.** With 30 % of replies corrupted, 3 of 4 runs did not reach a confident decision: two ended
   without a recommendation and paused at the document-review gate (one logged an extraction reply that was not valid JSON), and one was downgraded to
   referral. One run reached the correct decision.
3. **Tool outages degrade to a human.** With a tool server down, the run completes, marks itself degraded, lists the missing evidence in the memo and
   recommends referral. The memo validator requires a limitations section for every degraded run.

## Crash and resume

The process was interrupted immediately after the risk-scoring step on case C015 and restarted as a new session with the same thread
identifier and no input.

| | Steps |
|---|---|
| Before the interruption | Intake, document parsing, credit research, financial analysis, risk scoring |
| After the resume | Risk scoring, policy check, grade, policy check phase 2, memo, memo validation; then paused at human approval |

Document parsing, credit research and financial analysis, the expensive steps, were not executed again. Only the step in flight at the
interruption (risk scoring) ran again, which gives at-least-once semantics. The final recommendation (approve) matches the uninterrupted run.

## Observed failure mode of an earlier safety cap

In the first E4 run, degraded runs were capped only against approval. With a tool down, the statement "sanctions screening not performed" was
sometimes judged a failure, and four cases whose correct outcome is approve were declined:

| Profile | Case | Correct outcome | System recommendation |
|---|---|---|---|
| Flaky tool calls | C015 | Approve | Decline |
| Research server down | C015, C027 | Approve | Decline |
| Calculation server down | C027 | Approve | Decline |

An adverse decision caused by a technical outage is as unacceptable as an unsafe approval, because it denies an applicant on no real basis. The
workflow was changed so that a degraded run never auto-decides in either direction, and the three degraded profiles were rerun. In the earlier
run these three profiles gave 2 of 4 correct decisions each. Results are in `research/results/ablation_degraded_may_decline/`.

## Limitations

* There are 4 cases per profile, so the results show mechanisms and not probabilities.
* Latencies are inflated by free-tier throttling and by concurrency. Compare profiles with each other, not with production figures.
* The retries column counts model-request retries from the model-call log. It includes real free-tier `429` responses, which were frequent during the later profiles, and it does not
  include tool-call retries, which are not logged there.
* Faults are injected at the model-gateway and tool-call boundaries. Real failure modes (partial outages, slow degradation, correlated
  failures) are richer.
* The interrupted process is simulated by abandoning the event stream and opening a new session, not by terminating the process.
* The outcome classification covers only the strict policy and clean documents.

See also [Limitations of the evaluation](limitations.md) and [Reproducing the experiments](reproduce.md).
