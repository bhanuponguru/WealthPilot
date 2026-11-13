# Design decisions

The significant decisions, in the style of lightweight architecture-decision records. Several **reverse the original plan** — those are marked, with the reason.

## D1 · Deterministic routing instead of an LLM supervisor  *(changed from the plan)*

* **Context.** The first design had an LLM supervisor choosing the next agent.
* **Decision.** A fixed LangGraph workflow with conditional edges that are Python predicates over typed state, and counters on every loop.
* **Why.** Control flow becomes testable without a model, repeatable run to run, and explainable. It removes a source of nondeterminism that would have made the experiments harder to interpret.
* **Consequence.** The "six agents" are roles with defined responsibilities, not autonomous planners. See [Agents](../concepts/agents.md).

## D2 · The LLM reads; code decides

* **Decision.** The recommendation comes from a fixed decision rule over rule statuses; ratios and thresholds are compared by code; the approver tier is chosen by code from extracted limits; sanctions are classified by code.
* **Why.** Each place an LLM was trusted with a decision or arithmetic produced an error in testing (a self-contradicting `fail`, `132,000 > 150,000`, a looping tier agent). Moving the *decision* to code and keeping the LLM for *reading* removed those failure classes — or turned them into `missing_data` → *refer*.

## D3 · The policy is data, with a hidden answer key

* **Decision.** Policies are Markdown with stable rule ids; thresholds are extracted from the prose by the system; the machine-readable `reference.yaml` is read only by the ground-truth engine.
* **Why.** It is the only way to measure policy *reading*. If agents could see the key, a policy swap would be a trivially-correct file swap.
* **Consequence.** Policies must follow a few conventions ([Writing a new policy](../guides/new-policy.md)).

## D4 · Boolean answers, not labels

* **Decision.** The model answers `applies`, `rule_satisfied`, `exception`; code maps them to a status.
* **Why.** On prohibition rules the model wrote "not in the prohibited list" and then `status: fail`.

## D5 · Verify the LLM's arithmetic

* **Decision.** Each rule answer lists the numeric comparisons it relied on; code re-evaluates them; a contradiction triggers one targeted re-ask, then `missing_data`.
* **Why.** Arithmetic comparison mistakes were the largest error class in the first complete policy-adherence run (9 of 17 mismatches). Verification lifted lenient decision accuracy from 66.7 % to 91.7 %.

## D6 · Batched rule judging with retrieval in code  *(changed from the plan)*

* **Context.** The first design gave each rule its own tool-using agent that searched the policy itself (about 40 chat calls per case).
* **Decision.** Code retrieves passages for every rule through the MCP search tool; one LLM call then judges four rules at a time (about 13 chat calls per case).
* **Why.** The free NIM tier delivered only about 5–15 chat calls per minute; at 40 calls per case the experiment suite would have taken most of a day.
* **Consequence.** Retrieval always happens (the model cannot "forget" to look). The trade-off is that the model has fewer chances to self-correct by tool use, which D5 compensates for.

## D7 · MLflow instead of Langfuse  *(changed from the plan)*

* **Why.** Development ran on a 5.8 GB WSL2 VM; self-hosted Langfuse needs about six containers. MLflow is one process and covers tracing (LangGraph autolog), experiment tracking and the model registry.
* **Consequence.** One MLflow trace per case, tagged with `case_id`/`policy_id`/`thread_id`. Per-call metrics live in Postgres (`nim_calls`).

## D8 · Local embeddings with Ollama  *(changed from the plan)*

* **Why.** None of the 12 NIM embedding models in the public catalog worked for the development account (`404`/`410`).
* **Decision.** `nomic-embed-text` via Ollama (768 dimensions, with its required `search_document:` / `search_query:` prefixes).

## D9 · One shared gateway backed by Postgres

* **Decision.** A *library* (not a service) whose cache, rate limiter and call log live in Postgres, imported by the graph and every MCP server.
* **Why.** One request budget and one cache across all processes without operating another service. It also gives uniform fault injection and observability.

## D10 · An adaptive rate limit and an explicit, empty-by-default fallback  *(changed during the project)*

* **Decision.** AIMD limiter (×0.7 on `429`, +0.15 rpm on success, floor 6, ceiling `NIM_RPM_BUDGET`); `429`s do not open circuit breakers; the fallback model is off unless configured.
* **Why.** Real `429`s appeared well below the nominal budget and the limit was *per model*. The only alternative chat model degraded to garbled output on long replies, so enabling it by default would swap a visible failure for a silent wrong answer.

## D11 · Thinking off by default

* **Decision.** `enable_thinking=false` on reasoning models.
* **Why.** ~3× lower latency and near-zero reasoning tokens. With thinking on, a single document extraction was still running after four minutes.

## D12 · Layout reconstruction before extraction

* **Decision.** Rebuild tables from word coordinates so rows state their values by year.
* **Why.** The raw LLM swapped fiscal-year columns on mixed header formats — an error that reconciliation cannot catch. Fixing the *input* (80.3 % → 99.5 %) worked; telling the model to be careful did not.

## D13 · Degraded means refer — in both directions

* **Decision.** A run with any unavailable tool or check cannot auto-decide: approve *and* decline are capped at *refer*.
* **Why.** E4 found that "sanctions screening not performed" was sometimes read as a failure, wrongly declining four approvable cases. See [E4](../experiments/e4-reliability.md#a-bug-e4-found).

## D14 · Fixed fiscal-horizon label and no `TermInMonths`

* **Decision.** The PD label is "charged off within 5 years of approval"; the term column is not a feature.
* **Why.** `TermInMonths` holds the *realised* term for charged-off loans, a label leak worth AUC 0.95. See [Risk model](../concepts/risk-model.md#the-label).

## D15 · Human approval for every case

* **Decision.** There is no auto-decision path. The approver's tier must meet the policy's own delegation-of-authority requirement.
* **Why.** Credit decisions are consequential and regulated; the system's job is to prepare a verified recommendation, not to take the decision.

## D16 · Redaction instead of "don't mention it"

* **Decision.** Strip identity from every text before a model sees it (whole-word), and measure the leak rate; additionally scan memos for prohibited language.
* **Why.** Prompt instructions alone ("don't consider gender") cannot be verified; removing the information can. Measured: 78 % of prompts carried identity without redaction, 0 % with it.

## D17 · Honest ablations are kept

* **Decision.** Every result superseded by a bug fix or design change is preserved in `report/results/ablation_*` and `_first_attempt/`.
* **Why.** Several early results measured infrastructure problems (an empty-reply cache, a naive redactor, a missing decline cap). Keeping them documents what the experiments caught.

## D18 · A case index table, not checkpoint scanning

* **Context.** The first console lost a paused case when the browser tab was refreshed, and there was no way to list waiting cases.
* **Decision.** The `Runner` mirrors each run's status and headline facts into a small `case_runs` table (best-effort; never holds identity). The console's **Cases** page and Overview counts read it.
* **Why.** Checkpoints hold full state but cannot be listed cheaply; a purpose-built index makes the human-in-the-loop workflow durable across refreshes, restarts and reboots.

## D19 · Blocking runs with live progress, one event loop per action

* **Decision.** Each console action that executes the graph opens its own event loop and session and streams node updates into a progress box; viewing a case uses a cheap read-only session.
* **Why.** Streamlit scripts are synchronous; a short-lived session per action avoids stale connections and shared mutable state. The cost is that a run blocks the page — acceptable for a single-user tool, and closing the tab does not stop the run.

## D20 · Fail fast, and say how to fix it

* **Decision.** The database pool times out in 5 s and is created once; pages check a cached health status before touching Postgres; every failed check carries the command that fixes it (`wealthpilot doctor` and the console's System page share the same checks).
* **Why.** A missing service used to cost 30 s per page and end in a stack trace. A dead dependency should produce an instant, actionable sentence.

## D21 · Hide identity from the approver by default

* **Decision.** The *Application* tab shows what the agents saw and keeps the sealed identity behind an explicit checkbox; downloads never include it.
* **Why.** An approver who decides on the same facts as the model cannot be nudged by names or places; seeing identity stays possible for the cases (verifying a document) that need it.
