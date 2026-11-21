# Design decisions

This page lists the decisions behind the design. The main ones, those that involved a real choice between approaches or a change after
measurement, are recorded in full in the [Architecture Decision Records](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md), with options, rationale, evidence and a revisit trigger. Each
of those appears here as a one-line summary with a link. The remaining decisions, mostly about the console, tooling and operations, are
written out in full on this page. The numbering (D1 to D24) is stable so that other pages can refer to it.

## D1. Deterministic routing instead of a model supervisor

The workflow is a fixed graph. Conditional branches are code conditions over typed state, and every loop has a counter.

Record: [ADR-002, Deterministic routing instead of a model supervisor](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-002-deterministic-routing-instead-of-a-model-supervisor).

## D2. The language model reads; code decides

The recommendation comes from a fixed decision rule over rule statuses. Ratios and thresholds are compared by code. The approver tier is chosen by code from extracted limits. Sanctions matches are classified by code.

Record: [ADR-004, The language model reads; code decides](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-004-the-language-model-reads-code-decides).

## D3. The policy is data

A policy is a Markdown document with stable rule ids, and it is the only input. The system extracts thresholds from the text. The `policies/` folder contains policy text only. Any machine-readable answer key lives in the research package, never in the product.

Record: [ADR-005, The policy is data](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-005-the-policy-is-data).

## D4. Boolean answers, not labels

For each rule the model answers whether the rule applies, whether the case is in compliance and whether the situation is an exception. Code maps the answers to a status.

Record: [ADR-007, Boolean answers mapped to statuses by code](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-007-boolean-answers-mapped-to-statuses-by-code).

## D5. Verify the model's arithmetic

Each rule answer lists the numeric comparisons it relied on. Code re-evaluates them. A contradiction triggers one targeted re-ask, and a persistent contradiction turns the rule into missing data.

Record: [ADR-010, Verify the model's arithmetic](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-010-verify-the-models-arithmetic).

## D6. Batched rule judging with retrieval in code

Code retrieves passages for every rule through the search tool, then one model call judges four rules at a time.

Record: [ADR-009, Batched rule judging with retrieval in code](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-009-batched-rule-judging-with-retrieval-in-code).

## D7. MLflow for tracing and the model registry

**Context.** Tracing, a model registry and a small footprint are all needed, on hardware that may be modest.

**Decision.** MLflow provides tracing for the workflow, with one trace per case, and the model registry. Per-call metrics live in
Postgres.

**Rationale.** MLflow is a single process. Self-hosted LLM-observability platforms typically need several supporting services.

**Consequences.** Traces are tagged with case id, policy id and thread id. Tracing is best effort and never blocks underwriting. See
[Observability](observability.md).

## D8. Local embeddings

**Context.** Policy retrieval needs an embedding model. The availability of hosted embedding models varies by account.

**Decision.** Embeddings come from a local service running the `nomic-embed-text` model, with the document and query prefixes that
model requires.

**Rationale.** A local model removes a dependency on hosted availability and keeps embedding traffic off the hosted API's rate limit.

**Consequences.** The deployment includes an `ollama` service and a one-shot job that downloads the model. The vector dimension is
fixed at 768.

## D9. One shared gateway backed by Postgres

The gateway is a library, not a service. Its cache, rate limiter and call log live in Postgres, and both processes load it.

Record: [ADR-011, One shared gateway backed by Postgres](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-011-one-shared-gateway-backed-by-postgres).

## D10. An adaptive rate limit and an explicit, empty-by-default fallback

**Context.** Hosted model services enforce limits that fluctuate and differ by model. A second chat model may handle long structured
outputs worse than the first.

**Decision.** An additive-increase, multiplicative-decrease limiter adjusts the shared rate: it falls on `429` and recovers on
success, between a floor and the `NIM_RPM_BUDGET` ceiling. Rate-limit responses do not open circuit breakers. The fallback model is off
unless configured.

**Rationale.** The limiter finds the usable rate on its own. A fallback that degrades output silently would trade a visible failure
for a wrong answer.

**Consequences.** Throughput varies with the service's behavior, and the System page shows the current rate. Enabling a fallback is a
deliberate configuration choice.

## D11. Thinking off by default

**Context.** The chat and vision models are reasoning models, and extended thinking multiplies latency.

**Decision.** Extended thinking is disabled by default (`NIM_THINKING=false`).

**Rationale.** Latency drops substantially and reasoning tokens are nearly eliminated, and the tasks are extraction and judgment over
supplied text rather than open-ended reasoning.

**Consequences.** Output quality is judged with thinking off. Enabling it is a configuration change.

## D12. Layout reconstruction before extraction

Tables are rebuilt from word coordinates so that each row states its values by year before the model sees them.

Record: [ADR-013, Layout reconstruction before extraction](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-013-layout-reconstruction-before-extraction).

## D13. Degraded means refer, in both directions

A run with any unavailable tool or check cannot be recommended for approval or decline. Both are capped at refer.

Record: [ADR-016, Degraded means refer, in both directions](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-016-degraded-means-refer-in-both-directions).

## D14. A fixed five-year label and no term feature

The probability label is "charged off within five years of approval", and the term field is not a feature.

Record: [ADR-018, A fixed five-year label and no term feature](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-018-a-fixed-five-year-label-and-no-term-feature).

## D15. Human approval for every case

There is no automatic decision path. The approver's tier must meet the policy's own delegation-of-authority requirement.

Record: [ADR-019, Human approval for every case](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-019-human-approval-for-every-case).

## D16. Redaction instead of "don't mention it"

Identity is stripped from every text before a model sees it, with whole-word matching. Memos are additionally scanned for prohibited language.

Record: [ADR-021, Whole-word redaction instead of prompt instructions](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-021-whole-word-redaction-instead-of-prompt-instructions).

## D17. Superseded results are preserved

**Context.** Several early evaluation results measured infrastructure problems that were later corrected.

**Decision.** Results superseded by a design change are kept in the research package next to the current ones.

**Rationale.** They document what the evaluation caught and keep the current numbers honest.

**Consequences.** The research results folder contains superseded and ablation runs. See [Research](../research/index.md).

## D18. A case index table, not checkpoint scanning

**Context.** The console needs to list cases and reopen those that are paused. Checkpoints hold full state but cannot be listed
cheaply.

**Decision.** The workflow engine mirrors each run's status and headline facts into a small, best-effort index that never holds
identity while redaction is on. The Inbox and Cases pages read it.

**Rationale.** A purpose-built index makes the human-in-the-loop workflow durable across refreshes, restarts and reboots.

**Consequences.** The index can be stale or missing without affecting underwriting. See [Case index](console.md#case-index).

## D19. Runs execute on a background worker

**Context.** Streamlit stops a page script when the user changes page or closes the tab, which would abandon a run executed in the
script.

**Decision.** A process-wide run manager owns one worker thread with its own event loop. Each run opens its own workflow session
there. A page only watches a run through a progress object that a self-refreshing element polls. Viewing a case uses a cheap
read-only session.

**Rationale.** A run that belongs to the worker survives navigation, and the checkpointer makes a run interrupted by a restart cheap
to continue.

**Consequences.** There is no durable queue. A console restart interrupts runs in flight, which appear as interrupted and are
continued by hand. See [How the console is built](console.md#runs-belong-to-a-worker-not-to-the-page).

## D20. Fail fast, and say how to fix it

**Context.** A missing service can otherwise cost many seconds per page and end in a stack trace.

**Decision.** The database pool times out in a few seconds and is created once. Pages check a cached health status before touching
Postgres. Every failed check carries the command that fixes it, and `wealthpilot doctor` and the System page share the checks.

**Rationale.** A dead dependency should produce an instant, actionable sentence.

**Consequences.** Health checks are cached for a few seconds, so a recovery can take that long to show. See
[How the console is built](console.md#fail-fast-on-a-missing-database).

## D21. Hide identity from the approver by default

**Context.** An approver who sees names and places can be nudged by them.

**Decision.** The Application tab shows what the agents saw and keeps the sealed identity behind an explicit checkbox. Downloads never
include it.

**Rationale.** An approver who decides on the same facts as the model cannot be nudged by identity, and seeing identity stays
possible for cases that need it, such as verifying a document.

**Consequences.** The case is identified by case number, industry, loan amount and the masked business name.

## D22. Product-first navigation

**Context.** A credit officer's day is to see what is waiting, review it and decide.

**Decision.** The sidebar groups the six pages by who needs them: Work (Inbox, New case, Cases, History), Reference (Credit
policies) and Administration (System). The home page is an inbox of cases that need a decision, not a status page. A new application is
the primary content of New case. A sample-applicant tab exists only in demonstration mode. The redaction option sits behind advanced
options.

**Rationale.** The interface should reflect the reviewer's workflow and nothing else. Research tooling does not belong in the product.

**Consequences.** The product has no experiment or results pages. A test pins the list of pages. See
[How the console is built](console.md#page-structure).

## D23. A reviewer profile instead of retyping identity on every decision

**Context.** Typing the approver id and tier on every decision is error-prone and invites a default value ending up in a compliance
record.

**Decision.** The sidebar holds the reviewer's name and authority tier for the session, and the decision form is pre-filled from it.
The id is required and the console never writes a placeholder id to the audit log.

**Rationale.** Pre-filling reduces errors, and requiring the id keeps the record meaningful. The authoritative tier check stays in the
approval gate, so it holds for every client.

**Consequences.** The profile identifies the reviewer and is not authentication. The command-line interface takes the approver id as
its own option. Owner names stay masked on the review screens (D21).

## D24. Product and research are separate packages

The repository has two packages. The product never imports research code. The answer keys live in the research package. The `policies/` folder contains policy text only. Demonstration data, produced by the research package, is consumed by the product as plain files and is off by default. A test enforces these rules: it fails if product code imports the research package, if a policy folder holds anything but the policy text, or if the console exposes a page beyond the six product pages.

Record: [ADR-022, Product and research are separate packages](https://github.com/bhanuponguru/WealthPilot/blob/cs5903-final-2026/docs/Architecture_Decision_Records.md#adr-022-product-and-research-are-separate-packages).
