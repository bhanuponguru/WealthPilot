# Lessons learned

Things that went wrong during the project and what they taught. Most were found **by the experiments**, not by tests.

## 1. An experiment can measure your infrastructure instead of your system

The first policy-adherence run scored **38 % rule accuracy**. Almost every error was `missing_data` from `agent_error: ValueError`. The cause: a fallback model sometimes returned *empty*
replies, and the response cache **stored them** — so every retry replayed the same empty answer. 105 poisoned entries were purged, and empty replies are now retried and never cached.

> **Lesson.** When results look catastrophically bad, check what the failure *is* before touching the model. Look at the error reasons, not just the score.

## 2. Silent failures are worse than loud ones

* An agent that hit a recursion limit was swallowed by a `try/except` and fell back to a safe default — the tier was wrong with no error.
* A model that returned *garbled text* for long outputs (not an error code) would have produced silently wrong answers if it had been the default fallback.
* A degraded run was capped against approving, but not against **declining** — four correct approvals were wrongly declined.

> **Lesson.** Every fallback should either be correct or be *visible*. "Safe default" needs a second look: safe for whom?

## 3. Don't trust the LLM with arithmetic or labels

* `132,000 is above 150,000` — fixed by making the model list its comparisons and re-checking them in code.
* "Not in the prohibited list … `status: fail`" — fixed by asking boolean questions and mapping in code.
* A looping tool-using agent for a task that was really *extraction + comparison* — fixed by extracting limits with the LLM and comparing in code.

## 4. Fix the input, not the instruction

Telling the model to "read the year above each column" did nothing for column swaps; rebuilding the table so each row states its values by year fixed them (80 % → 99.5 %).

## 5. A too-good metric is a bug until proven otherwise

The first risk model reported **AUC 0.946**. The cause was a label leak: for charged-off loans `TermInMonths` is the *realised* term. Single-feature AUC testing found it in one step. The honest model scores 0.68.
A related slip: the data stores "paid in full" as `P I F`; a first check that matched `PIF` dropped every paid loan and reported a 100 % charge-off rate.

## 6. Naive string handling corrupts prompts

Substring redaction turned "market" into "[OWNER]et" for an owner named *Mark*, corrupting prompts and inflating the leak meter. Whole-word matching fixed it. The fairness experiment found it because the leak
meter reported a *non-zero* leak that should have been zero — a false positive worth investigating.

## 7. Verify the claim, not just the code

The documentation and plan claimed "MLflow traces (LangGraph autolog)" but no code enabled it. The tests passed; the *claim* was false. An independent review caught it, tracing was built, and a trace was verified to exist with the right tags.
Similarly, a lint pass caught that cleaning up "dead code" had deleted a live prompt (`BATCH_SYS`) — the offline tests did not exercise that function, so regression tests for it were added.

## 8. Free-tier infrastructure is a design constraint, not a footnote

* The public model catalog listed many models that return `404`/`410` for the account.
* Limits were **per model** and fluctuated; one model went from fast to throttled to unusable (503 → empty → garbled).
* Effective throughput was 5–15 calls per minute, so a design needing ~40 calls per case was infeasible. Batching and retrieval-in-code cut it to ~13.

> **Lesson.** Measure what you can actually call before designing around it, and keep model ids in configuration.

## 9. Statistical honesty

* A first 5-seed false-positive estimate (20 %) looked like "≈ 5 %" until 20 seeds gave 15 %. Small samples flatter and mislead in both directions.
* Zero flips with redaction on is **guaranteed by the cache** when prompts are identical; the real evidence there is the leak rate and an uncached noise floor.
* A "noise floor" that looked like 36 % turned out to be one run diverted to document review — a different phenomenon. Separate *kinds* of variation.

## 10. Keep the superseded results

Every ablation (`report/results/ablation_*`, `_first_attempt/`) documents a bug the experiments caught. They are more instructive than the final numbers.

## Process notes

* Starting a background process with `pkill -f <pattern>` can kill your own shell if the pattern appears in its command line; bracket one character (`[m]lflow`).
* Run one capacity-sensitive experiment at a time: concurrent experiments distort each other's latency and trigger rate limits.
* Cheap offline checks (lint for undefined names, import-all-modules) catch mistakes that slow, expensive live runs would only reveal late.
