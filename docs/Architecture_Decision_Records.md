# Architecture Decision Records

This is the single decision log for WealthPilot. Each record covers one decision that shaped the design or the methodology. Choices about the console, tooling and operations are summarized on the
[design decisions](architecture/decisions.md) page and are not repeated here. Superseded records are kept next to the records that replaced them. Records follow one template:

| Field | Content |
|---|---|
| ID, title | `ADR-nnn` and a short title |
| Status and scope | Accepted or Superseded; the milestone and components affected; which record it supersedes or is superseded by |
| Context | The problem and the constraints that forced a decision |
| Options | At least two credible options, including keeping the existing approach where one existed |
| Decision and rationale | The selected option. Statements marked *(measured)* rest on an experiment in this repository; statements marked *(judgment)* do not |
| Consequences | Benefits, costs, rejected capabilities and rollback implications |
| Evidence | Commit, tests, result files or measurements |
| Revisit when | A measurable circumstance that should reopen the decision |

**Milestone key.** M0 setup and checks; M1 synthetic world and reference engine; M2 risk model; M3 tool servers; M4 model gateway and
reliability; M5 parsing; M6 workflow graph; M7 console; M8 experiments; P1 product packaging after M8 (console rework, product and
research split, container deployment, documentation).

**Commit key.** Links name the commit that implemented a decision: [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b)
(M0 to M8 build), [`01fc64d`](https://github.com/bhanuponguru/WealthPilot/commit/01fc64d) (console),
[`be1d4f4`](https://github.com/bhanuponguru/WealthPilot/commit/be1d4f4) (model probe tooling),
[`a5d090c`](https://github.com/bhanuponguru/WealthPilot/commit/a5d090c) (console rework, background runs),
[`aa187e7`](https://github.com/bhanuponguru/WealthPilot/commit/aa187e7) (product and research split, containers) and
[`5c77bab`](https://github.com/bhanuponguru/WealthPilot/commit/5c77bab) (documentation). Relative links on this page resolve against
the same revision when viewed on GitHub.

**Index.**

| ID | Title | Status |
|---|---|---|
| [ADR-001](#adr-001-methodology-record) | Methodology record | Accepted |
| [ADR-002](#adr-002-deterministic-routing-instead-of-a-model-supervisor) | Deterministic routing instead of a model supervisor | Accepted |
| [ADR-003](#adr-003-tools-are-served-by-three-mcp-servers) | Tools are served by three MCP servers | Accepted |
| [ADR-004](#adr-004-the-language-model-reads-code-decides) | The language model reads; code decides | Accepted |
| [ADR-005](#adr-005-the-policy-is-data) | The policy is data | Accepted |
| [ADR-006](#adr-006-pass-or-fail-labels-from-the-model) | Pass or fail labels from the model | Superseded by ADR-007 |
| [ADR-007](#adr-007-boolean-answers-mapped-to-statuses-by-code) | Boolean answers mapped to statuses by code | Accepted |
| [ADR-008](#adr-008-one-tool-using-agent-loop-per-rule) | One tool-using agent loop per rule | Superseded by ADR-009 |
| [ADR-009](#adr-009-batched-rule-judging-with-retrieval-in-code) | Batched rule judging with retrieval in code | Accepted |
| [ADR-010](#adr-010-verify-the-models-arithmetic) | Verify the model's arithmetic | Accepted |
| [ADR-011](#adr-011-one-shared-gateway-backed-by-postgres) | One shared gateway backed by Postgres | Accepted |
| [ADR-012](#adr-012-default-chat-model-and-an-empty-fallback) | Default chat model and an empty fallback | Accepted |
| [ADR-013](#adr-013-layout-reconstruction-before-extraction) | Layout reconstruction before extraction | Accepted |
| [ADR-014](#adr-014-hybrid-retrieval-with-a-reranker-and-structure-aware-chunks) | Hybrid retrieval with a reranker and structure-aware chunks | Accepted |
| [ADR-015](#adr-015-the-degraded-cap-applied-only-to-approval) | The degraded cap applied only to approval | Superseded by ADR-016 |
| [ADR-016](#adr-016-degraded-means-refer-in-both-directions) | Degraded means refer, in both directions | Accepted |
| [ADR-017](#adr-017-realized-loan-term-as-a-model-feature) | Realized loan term as a model feature | Superseded by ADR-018 |
| [ADR-018](#adr-018-a-fixed-five-year-label-and-no-term-feature) | A fixed five-year label and no term feature | Accepted |
| [ADR-019](#adr-019-human-approval-for-every-case) | Human approval for every case | Accepted |
| [ADR-020](#adr-020-substring-redaction) | Substring redaction | Superseded by ADR-021 |
| [ADR-021](#adr-021-whole-word-redaction-instead-of-prompt-instructions) | Whole-word redaction instead of prompt instructions | Accepted |
| [ADR-022](#adr-022-product-and-research-are-separate-packages) | Product and research are separate packages | Accepted |

---

## ADR-001: Methodology record

**Status and scope.** Accepted. Whole project; methodology.

**Statement.** The project methodology was not formally recorded at the 9 October 2026 checkpoint. This record is written at final
submission, with the repository history as its only source, and is not backdated. The methodology summarized below is the one that the
repository shows was followed; it was not reaffirmed or changed through a recorded checkpoint.

**Methodology followed.**

1. Build a deterministic, policy-driven underwriting workflow on a language-model gateway (ADR-002, ADR-004, ADR-005).
2. Evaluate it against ground truth that the system under test cannot see: a reference engine over synthetic applicants, real SBA 7(a)
   outcomes for the risk model, and fault injection for reliability (experiments E0 to E4).
3. Report every result with its sample size and a confidence interval where one is meaningful, and keep superseded runs beside the current ones.
4. Change the design when an experiment exposes a defect, and record the change as a new decision that supersedes the old one
   (ADR-006, ADR-008, ADR-015, ADR-017, ADR-020).

**Options considered.** (a) Record a reaffirmation retroactively. Rejected: no evidence exists, and the guide forbids backdating.
(b) State the gap and document the methodology as practiced (selected).

**Consequences.** Methodology changes after the build are visible only as superseded records in this log, not as checkpoint approvals.

**Evidence.** Commit history from [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b) to
[`5c77bab`](https://github.com/bhanuponguru/WealthPilot/commit/5c77bab); [research results](../research/results/) with preserved
superseded runs.

**Revisit when.** Any fundamental change of approach (model, evaluation design or architecture) after submission.

---

## ADR-002: Deterministic routing instead of a model supervisor

**Status and scope.** Accepted. M6; workflow graph and agents.

**Context.** A multi-agent system needs something to choose the next step. The audience (credit officers, auditors) needs control flow
that is repeatable and explainable, and the free-tier model service makes every extra model call slow.

**Options.** (a) A language-model supervisor that picks the next agent. (b) A fixed graph whose branches are code conditions over typed
state, with loop counters (selected). (c) A free-form agent team with shared chat history.

**Decision and rationale.** Option (b). Routing is testable without a model, repeats from run to run and adds no routing calls
*(judgment)*. Conformance of routing and loop caps is covered by unit tests *(measured)*.

**Consequences.** The six agents are roles with fixed responsibilities, not planners. New behavior needs a graph change, not a prompt
change. Rolling back to a supervisor would need a new routing node and would give up reproducible control flow.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [workflow](architecture/workflow.md);
[agents](architecture/agents.md); [`tests/test_unit.py`](../tests/test_unit.py).

**Revisit when.** More than 10 % of cases in a measured sample need a step the fixed graph cannot express.

---

## ADR-003: Tools are served by three MCP servers

**Status and scope.** Accepted. M3; `mcp_servers/`, workflow tool access.

**Context.** The workflow needs deterministic calculations, policy search and borrower research. The tools must be independently
testable, replaceable (the research sources are mocks) and fail independently so that reliability can be measured.

**Options.** (a) Plain Python functions called in-process. (b) Three FastMCP servers over streamable HTTP, called through the
LangChain MCP adapter (selected). (c) One combined server.

**Decision and rationale.** Option (b). A network boundary gives a real failure mode (a tool server that is down) that E4 can inject, lets
a mock research server be swapped for a real provider, and exposes a standard tool contract *(judgment)*. Three servers keep
calculations, policy search and research failure domains separate *(judgment)*.

**Consequences.** Every tool call crosses the network, which adds latency and a startup dependency. In the container deployment
the three servers share one container. In-process calls would be simpler but would remove the fault boundary.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b);
[tool servers](architecture/tool-servers.md); [tool reference](reference/tool-reference.md);
[`tests/test_mcp_contract.py`](../tests/test_mcp_contract.py) starts each server and calls every tool.

**Revisit when.** Tool-call overhead (not measured separately so far) exceeds 5 % of the time of a case, or a tool needs to run on a different host with different trust.

---

## ADR-004: The language model reads; code decides

**Status and scope.** Accepted. M6; all decision-bearing nodes.

**Context.** Early runs produced confident errors: a rule marked failed beside an explanation that it was satisfied, and a comparison
stating that 132,000 exceeds 150,000.

**Options.** (a) Let the model decide and justify (the common pattern). (b) Constrain prompts and trust the answer. (c) Use the model
only to read documents and policy text and to write prose; decide in code (selected).

**Decision and rationale.** Option (c). The recommendation comes from a fixed decision rule over rule statuses, ratios and thresholds
are compared by code, the approver tier is chosen by code from extracted limits, and sanctions matches are classified by code. This
removes the observed failure classes or turns them into missing data, which leads to referral *(judgment, with the effect of the numeric
check measured in ADR-010)*.

**Consequences.** Every outcome can be reproduced from recorded rule statuses. Model quality limits how many rules can be read, not
what the decision is. The model cannot compensate for a wrong threshold extraction.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [decision rule](architecture/decision-rule.md);
[E0 results](../research/results/e0_policy.md).

**Revisit when.** A measured sample shows rule-reading accuracy below 90 % under both reference policies, which would make the
referral rate impractical.

---

## ADR-005: The policy is data

**Status and scope.** Accepted. M1, M3; `policies/`, policy search, evaluation design.

**Context.** A bank's credit policy is prose and changes. The evaluation question is whether the system applies a policy it is given,
which is meaningless if the system can read an answer key.

**Options.** (a) Encode the policy in code. (b) A structured rule file (YAML) as the system's input. (c) Markdown prose with stable rule
ids as the only input; the system extracts thresholds from the text; the machine-readable key lives only in the research package
(selected).

**Decision and rationale.** Option (c). Reading prose is the capability being delivered and measured. Swapping policies becomes a file
change, not a release *(judgment)*. Thresholds were read correctly from the text in 100 % of E0 cases *(measured)*.

**Consequences.** Policies must follow conventions for rule ids and for the thresholds that feed the scorecard. The system cannot resolve
ambiguity that the policy leaves open.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [policy retrieval](architecture/policy-retrieval.md);
[managing policies](administration/policies.md); [`tests/test_boundary.py`](../tests/test_boundary.py) fails if a policy folder holds
anything but the policy text.

**Revisit when.** A third policy of different structure drops threshold-extraction accuracy below 95 %.

---

## ADR-006: Pass or fail labels from the model

**Status and scope.** Superseded by ADR-007. M6; policy node.

**Context.** The first design asked the model to label each rule `pass`, `fail`, `exception` or `n/a`.

**Options.** (a) Ask for the label (selected at the time). (b) Ask boolean questions about the case (ADR-007).

**Decision and rationale.** Option (a), as the most direct way to read a rule *(judgment)*.

**Consequences.** Superseded after development testing showed the model contradicting itself on prohibition-style rules, where "pass"
depends on a double negative.

**Evidence.** Design notes in the original plan; replaced in [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b).

**Revisit when.** Not applicable; kept for history.

---

## ADR-007: Boolean answers mapped to statuses by code

**Status and scope.** Accepted. M6; policy node. Supersedes ADR-006.

**Context.** Pass or fail labels depend on how a rule is phrased; questions about the case do not.

**Options.** (a) Keep labels and add a consistency check. (b) Ask whether the rule applies, whether the case complies and whether the
situation is an exception, and let code derive the status (selected).

**Decision and rationale.** Option (b). Statuses are consistent with the answers by construction *(judgment)*. Rule-level accuracy in
the final run was 97.2 % under the strict policy and 94.4 % under the lenient policy (288 judgements) *(measured)*.

**Consequences.** One more question per rule inside the same batched call (ADR-009). Rules whose answer cannot be read become missing
data and are referred.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [decision rule](architecture/decision-rule.md#rule-statuses);
[E0 results](../research/results/e0_policy.md).

**Revisit when.** A model change alters per-rule accuracy by more than 5 points in either direction.

---

## ADR-008: One tool-using agent loop per rule

**Status and scope.** Superseded by ADR-009. M6; policy node.

**Context.** The first design gave each rule its own tool-using agent that searched the policy and judged the rule.

**Options.** (a) Per-rule agent loops (selected at the time). (b) Retrieval in code and batched judging (ADR-009).

**Decision and rationale.** Option (a), because tool use lets the model correct itself *(judgment)*.

**Consequences.** The first complete evaluation run needed about 50 model calls per case. Under the rate limit it ran at about 14 minutes
per case, and the shared cache replayed empty replies, so most mismatches were missing-data results (132 of 183). The run measured an
infrastructure defect rather than policy reading.

**Evidence.** [`_first_attempt`](../research/results/_first_attempt/) (strict 50 %, lenient 33 % decision accuracy).

**Revisit when.** Not applicable; kept for history.

---

## ADR-009: Batched rule judging with retrieval in code

**Status and scope.** Accepted. M6; policy node. Supersedes ADR-008.

**Context.** Per-rule loops multiplied model calls under a rate-limited free tier.

**Options.** (a) Keep per-rule agents and raise the rate budget. (b) Code retrieves passages for every rule; one model call judges four
rules (selected).

**Decision and rationale.** Option (b). Far fewer calls per case, and retrieval always happens because code performs it *(judgment)*.
The final E0 run used 131 uncached model calls for 24 cases with the response cache on *(measured)*, against about 50 per case before.

**Consequences.** The model cannot forget to look, and has fewer chances to self-correct, which ADR-010 compensates for.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b);
[policy retrieval](architecture/policy-retrieval.md#how-rules-are-judged); [E0 results](../research/results/e0_policy.md).

**Revisit when.** Batch-position effects appear (a rule is judged differently depending on its neighbors) in a controlled comparison.

---

## ADR-010: Verify the model's arithmetic

**Status and scope.** Accepted. M6; policy node.

**Context.** Numeric comparison against thresholds was a frequent class of model error.

**Options.** (a) Trust the model's verdict. (b) Each answer lists the comparisons it relied on; code re-evaluates them; a contradiction
triggers one targeted re-ask and a persistent contradiction becomes missing data (selected).

**Decision and rationale.** Option (b). A verified wrong answer is corrected, and an unverifiable one becomes a referral *(judgment)*.
In E0, adding this step raised strict-policy decision accuracy from 91.7 % to 100 % and lenient-policy accuracy from 66.7 % to 91.7 %;
policy-flip agreement rose from 33 % to 83 % *(measured, n = 12 per policy; the intervals overlap, so the result indicates a mechanism and
not a precise effect)*.

**Consequences.** Inconsistent answers are referred, not decided.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b);
[baseline run](../research/results/ablation_no_numeric_verify/e0_policy.md); [final run](../research/results/e0_policy.md).

**Revisit when.** The re-ask step is triggered in more than 20 % of rule judgements, which would suggest changing the prompt or model.

---

## ADR-011: One shared gateway backed by Postgres

**Status and scope.** Accepted. M4; model gateway.

**Context.** The workflow process and the policy tool server both call model services and must respect one request budget.

**Options.** (a) A separate gateway service. (b) A library loaded by each process with shared state in Postgres (selected). (c) Per-process
limits.

**Decision and rationale.** Option (b). One request budget, one response cache and one call log across processes, without another
service to run, and uniform fault injection *(judgment)*.

**Consequences.** The database is on the path of every model call. Cache hits also hide model nondeterminism; experiments that need
fresh calls (E4) disable the cache.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [model gateway](architecture/model-gateway.md);
[`tests/test_gateway_live.py`](../tests/test_gateway_live.py).

**Revisit when.** A deployment needs more than one console host or more than 10 requests per second through the gateway.

---

## ADR-012: Default chat model and an empty fallback

**Status and scope.** Accepted. M4, P1; model gateway, configuration. Replaces the original plan of a 550B model as primary.

**Context.** The model catalog contains many entries that are retired or unavailable for the account, and availability changes. The
default must be a model that answers reliably and calls tools correctly.

**Options.** (a) `nvidia/nemotron-3.5-lightning-30b-a3b`. (b) `poolside/laguna-xs-2.1`. (c) The 550B model `nvidia/nemotron-3-ultra-550b-a55b` as primary, the original plan (rejected: it returned `503` responses and timeouts, and the order was flipped during the build).

**Decision and rationale.** Option (a) as default, with no fallback unless configured. A probe of 54 chat models found 11 that answered
both a tool-call and a plain probe correctly *(measured)*. A reduced two-case E0 gave both (a) and (b) 100 % decision accuracy under both
policies (confidence interval 34 to 100 %), so the comparison cannot rank them *(measured)*. The default stays because it is the model
under which every experiment was run *(judgment)*. An unconfigured fallback avoids silently trading a visible failure for a wrong answer
*(judgment)*.

**Consequences.** All accuracy results apply to one model family. The model identifier is configuration, so a change needs no code
change, but it invalidates the reported numbers until the experiments are rerun.

**Evidence.** [`be1d4f4`](https://github.com/bhanuponguru/WealthPilot/commit/be1d4f4);
[probe results](../research/results/nim_probe.json); [model comparison](../research/results/model_compare/);
[research overview](research/index.md#selecting-the-language-model).

**Revisit when.** The default model becomes unavailable for more than a day, or a full-size E0 (at least 50 cases) shows another model
more than 5 points better in decision accuracy.

---

## ADR-013: Layout reconstruction before extraction

**Status and scope.** Accepted. M5; parsing.

**Context.** A model reading flattened table text can assign values of one fiscal year to another when headers differ. Reconciliation
cannot detect it, because each year's totals still balance.

**Options.** (a) Instruct the model to be careful. (b) Add a repair step after extraction. (c) Rebuild tables from word coordinates so each
row states its values by year before the model sees them (selected).

**Decision and rationale.** Option (c). On noisy-layout statements, field accuracy was 80.3 % with raw text, 99.5 % with layout
reconstruction and 100 % with reconstruction plus the repair step; a canonical-label baseline without a model reached 36.7 %
*(measured, 12 documents, 608 fields per cell)*.

**Consequences.** Text PDFs are handled deterministically up to label mapping. The reconstruction assumes aligned numeric columns, so
other layout families are untested.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [document parsing](architecture/document-parsing.md);
[E1 results](../research/results/e1_parsing.md).

**Revisit when.** Accuracy on a held-out set of real statements falls below 90 % of fields.

---

## ADR-014: Hybrid retrieval with a reranker and structure-aware chunks

**Status and scope.** Accepted. M3, M8; policy search.

**Context.** The system must find the policy rule that answers a question, and the first retrieved passage is the one the model is most
likely to use.

**Options.** (a) BM25 only. (b) Dense vectors only. (c) Hybrid fusion of both with reciprocal rank fusion. (d) Hybrid plus a hosted
reranker (selected). Chunking: fixed-size or by policy section (selected).

**Decision and rationale.** Option (d) with section chunks. Recall at rank 1 over 104 queries was 79.8 % for BM25, 74.0 % for dense,
76.9 % for hybrid and 97.1 % for hybrid with the reranker; fixed-size chunks with the reranker reached 92.3 % *(measured, 104 phrasings of
13 rules, which are not independent samples)*.

**Consequences.** Each retrieval costs a reranker call on the hosted service. If the reranker is down, search degrades to hybrid and the
run is flagged.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [E2 results](../research/results/e2_rag.md);
[policy retrieval](architecture/policy-retrieval.md).

**Revisit when.** A policy corpus of more than 50 rules shows recall@1 below 90 %, or the reranker is retired.

---

## ADR-015: The degraded cap applied only to approval

**Status and scope.** Superseded by ADR-016. M6; decision rule.

**Context.** A run with an unavailable tool or check must not be approved on incomplete evidence.

**Options.** (a) Cap only approval at referral (selected at the time). (b) Cap both approval and decline (ADR-016).

**Decision and rationale.** Option (a), because approving on incomplete checks is the unsafe direction *(judgment)*.

**Consequences.** The fault-injection experiment showed that a degraded run could still be declined: four cases whose correct outcome
is approve were declined because "sanctions screening not performed" was sometimes judged a failure. A tool outage became an adverse
action without a real basis. Superseded.

**Evidence.** [`ablation_degraded_may_decline`](../research/results/ablation_degraded_may_decline/e4_reliability.md).

**Revisit when.** Not applicable; kept for history.

---

## ADR-016: Degraded means refer, in both directions

**Status and scope.** Accepted. M6, M8; decision rule. Supersedes ADR-015.

**Context.** A check that could not be performed can be misread as a failure, and an incomplete check can be misread as a pass.

**Options.** (a) Cap approval only (ADR-015). (b) Cap both approval and decline at referral (selected). (c) Retry until the tool recovers.

**Decision and rationale.** Option (b). Across the three fault profiles with degraded tools, all 11 degraded runs were referred, and the
full set of 28 fault-injected runs had 0 unsafe approvals and 0 wrongful declines *(measured, 4 cases per profile)*. Under option (a) the
same profiles produced 4 wrongful declines in total and 2 of 4 correct decisions each.

**Consequences.** Outages produce referrals and visible limitations instead of wrong decisions. The cost is a lower rate of automated
correct decisions under outage (0 of 4 in two profiles), which is the intended trade.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [decision rule](architecture/decision-rule.md#the-degraded-run-cap);
[E4 results](../research/results/e4_reliability.md).

**Revisit when.** A real deployment shows referrals caused by degraded runs above 20 % of cases.

---

## ADR-017: Realized loan term as a model feature

**Status and scope.** Superseded by ADR-018. M2; risk model.

**Context.** The first risk model used the loan term from the SBA file among its features.

**Options.** (a) Include the term (selected at the time). (b) Exclude it and fix the label horizon (ADR-018).

**Decision and rationale.** Option (a), as an ordinary loan attribute *(judgment)*.

**Consequences.** The term field records the realized term for charged-off loans, which reveals the outcome. The term alone scored an
AUC of 0.95, which is a label leak, not skill. Superseded during M2.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [risk model](architecture/risk-model.md#the-label).

**Revisit when.** Not applicable; kept for history.

---

## ADR-018: A fixed five-year label and no term feature

**Status and scope.** Accepted. M2; risk model. Supersedes ADR-017.

**Context.** The default-risk model needs a label that is not censored and features that do not reveal it.

**Options.** (a) Label from the final status and keep all features. (b) Label as "charged off within five years of approval", exclude
the term, and split by approval year (selected).

**Decision and rationale.** Option (b). A fixed horizon avoids right-censoring for the approval years used. Training on fiscal years 2010
to 2015, calibrating on 2016 and testing on 2017 to 2019 gave a test AUC of 0.68, Brier score 0.0404 and n = 155,941 *(measured)*. The
model is modest, and the figure is honest.

**Consequences.** The model uses loan and business-profile features only; it cannot use the parsed financial ratios, which the SBA file
does not contain. The file holds only approved loans, so selective labels bias the model.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [risk model](architecture/risk-model.md);
[`artifacts/pd_metrics.json`](../artifacts/pd_metrics.json).

**Revisit when.** Borrower financials paired with outcomes become available, or test AUC on a newer cohort drops below 0.65.

---

## ADR-019: Human approval for every case

**Status and scope.** Accepted. M6; approval gate, console, audit log.

**Context.** Credit decisions are consequential and regulated.

**Options.** (a) Automatic decisions for clear cases. (b) A human gate for every case, with the approver's tier checked against the
policy's own delegation-of-authority rule (selected).

**Decision and rationale.** Option (b). The system prepares a verified recommendation and does not take the decision *(judgment)*.

**Consequences.** Throughput is bounded by reviewers. Every decision has a named human and a tier in the hash-chained audit log. There
is no automatic path to roll back to.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [compliance](architecture/compliance.md#human-approval);
[`tests/test_unit.py`](../tests/test_unit.py) covers the audit chain.

**Revisit when.** A governance owner approves an automatic path for a defined low-risk band, with an audited false-approval rate.

---

## ADR-020: Substring redaction

**Status and scope.** Superseded by ADR-021. M6, M8; redaction.

**Context.** Identity must not reach a model prompt.

**Options.** (a) Remove identity tokens by substring match (selected at the time). (b) Whole-word match (ADR-021).

**Decision and rationale.** Option (a), as the simplest removal *(judgment)*.

**Consequences.** The counterfactual experiment found leaks that substring matching missed: 3 of 84 model requests (3.6 %) still contained
an identity token with redaction on.

**Evidence.** [`ablation_naive_redaction`](../research/results/ablation_naive_redaction/e3_counterfactual.md).

**Revisit when.** Not applicable; kept for history.

---

## ADR-021: Whole-word redaction instead of prompt instructions

**Status and scope.** Accepted. M6, M8; redaction, memo scan. Supersedes ADR-020.

**Context.** An instruction in a prompt such as "do not consider gender" cannot be verified.

**Options.** (a) Prompt instructions only. (b) Substring redaction (ADR-020). (c) Strip identity from every text with whole-word matching,
and scan memos for prohibited language (selected).

**Decision and rationale.** Option (c). With redaction on, 0 of 84 model requests contained an identity token, against 69 of 88 with
redaction off; no decision changed under identity swaps in either setting (0 of 6) *(measured, 3 cases, 6 counterfactuals)*. A rerun of the
new redaction over the 135 texts sent in E0, E1 and E4 produced identical output to the old one, so the earlier experiments are not
affected.

**Consequences.** Scanned pages cannot be redacted by text matching. The sample is small, so small identity effects cannot be excluded.

**Evidence.** [`7ef716b`](https://github.com/bhanuponguru/WealthPilot/commit/7ef716b); [compliance](architecture/compliance.md#redaction);
[E3 counterfactual results](../research/results/e3_counterfactual.md).

**Revisit when.** A leak is observed with redaction on in production traces, or scanned statements are added to the counterfactual set.

---

## ADR-022: Product and research are separate packages

**Status and scope.** Accepted. P1; repository layout, packaging.

**Context.** The system was evaluated with synthetic applicants, a reference engine that holds ground truth and a set of experiments.
Mixing them into the deployed product would blur what is delivered and risk exposing answer keys to the system under test.

**Options.** (a) One package. (b) Two packages in one workspace; the research package depends on the product, never the reverse
(selected). (c) Two repositories.

**Decision and rationale.** Option (b). The product image contains no experiment code and the measurements stay honest *(judgment)*. A
test enforces the boundary: it fails if product code imports the research package, if a policy folder holds anything but the policy text,
or if the console exposes a page beyond the six product pages *(measured)*.

**Consequences.** Demonstration data is produced by the research package and read by the product as plain files, off by default.
Experiments run from a separate image target under their own Compose profile.

**Evidence.** [`aa187e7`](https://github.com/bhanuponguru/WealthPilot/commit/aa187e7); [`tests/test_boundary.py`](../tests/test_boundary.py);
[developer guide](architecture/development.md).

**Revisit when.** A second consumer of the research code appears, which would justify a separate repository.
