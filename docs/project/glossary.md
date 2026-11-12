# Glossary

**Adverse action**
:   A decision unfavourable to an applicant (decline or less favourable terms). Regulations such as ECOA/Regulation B require specific reasons to be given; WealthPilot's validator requires them on every decline.

**AIMD**
:   *Additive increase, multiplicative decrease* — the congestion-control rule used by the adaptive rate limiter: cut the rate sharply on a `429`, raise it slowly on success.

**Approver tier**
:   The authority level required to decide a case — *Analyst*, *Senior Credit Officer* or *Credit Committee* — taken from the policy's delegation-of-authority rule.

**BM25**
:   A classic lexical ranking function; one half of the hybrid retriever.

**Checkpoint / checkpointer**
:   A saved snapshot of the graph state; LangGraph's Postgres checkpointer lets a paused case resume in a new process.

**Collateral coverage**
:   Appraised collateral value divided by the loan amount.

**Credit memo**
:   The structured write-up (recommendation, strengths, concerns, conditions, adverse-action reasons, limitations) prepared for the human approver.

**Degraded run**
:   A run in which some tool, model or check was unavailable. It can never auto-decide; it recommends *refer*.

**Demographic parity difference (DPD)**
:   The largest difference in selection rate between groups.

**DSCR**
:   *Debt service coverage ratio* — cash available for debt service divided by debt service, including the proposed loan. See [Policy rules](../reference/policy-rules.md#definitions-identical-in-both-policies).

**ECOA / Regulation B**
:   US fair-lending rules that prohibit discrimination on certain bases (race, sex, marital status, …). The example compliance profile is modelled on them.

**Equalized odds difference (EOD)**
:   The largest difference in true-positive or false-positive rate between groups.

**FOIA (SBA 7(a))**
:   The public SBA dataset of 7(a) small-business loans used to train the default model.

**Grade**
:   The internal risk rating A (best) to E (worst), from the PD band and the scorecard class.

**Interrupt**
:   LangGraph's mechanism to pause a graph and wait for external input; used at the document-review and approval gates.

**MCP (Model Context Protocol)**
:   An open protocol for exposing tools to LLM applications. WealthPilot's three tool servers speak it over streamable HTTP.

**NAICS**
:   North American Industry Classification System code; the first two digits give the sector.

**NIM (NVIDIA Inference Microservices)**
:   NVIDIA's hosted model endpoints, used here for chat, vision and reranking.

**OFAC SDN list**
:   The US Treasury's *Specially Designated Nationals* sanctions list.

**PD (probability of default)**
:   Here, the calibrated probability that an SBA-style loan is charged off within five years.

**Policy flip agreement**
:   In E0: among cases whose correct decision differs between two policies, the fraction where the system changed its decision the correct way.

**Proxy group**
:   A grouping (such as region or business age) that is *not* a legally protected class but may correlate with one; used because the SBA data has no protected attributes.

**RAG**
:   *Retrieval-augmented generation* — retrieving relevant text and giving it to the model. Here, retrieving the policy rule before judging it.

**Reconciliation**
:   Deterministic consistency checks on extracted statements (the balance sheet balances, net income ties, bank balances roll forward).

**Redaction**
:   Removing the owner's identity from any text before a model sees it.

**Reference engine**
:   The deterministic implementation of a policy that produces the ground truth for experiments, reading a hidden answer key.

**Rerank**
:   Re-scoring a short list of retrieved passages with a cross-encoder to improve ordering.

**RRF (reciprocal rank fusion)**
:   A way to merge several rankings (here BM25 and vector search) by summing `1 / (k + rank)`.

**Scorecard**
:   Pass/fail on DSCR, leverage and liquidity using the thresholds extracted from the policy; yields *strong*, *adequate* or *weak*.

**Selective labels**
:   When outcomes are only observed for approved applicants, so models and audits cannot see what would have happened to rejected ones.

**Sealed attributes**
:   The part of the case state holding identity (name, gender, name origin, address) that is never placed in a prompt.

**SHAP**
:   A method to attribute a model's prediction to its features; used for human-readable risk factors.

**Thread (`thread_id`)**
:   The identifier of one graph run's checkpoints; resuming uses the same thread id.
