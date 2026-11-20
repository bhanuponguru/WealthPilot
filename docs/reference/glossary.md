# Glossary

Definitions of the terms used throughout the documentation.

**Adverse action**
:   A decision unfavorable to an applicant, such as a decline. Fair-lending rules like ECOA and Regulation B require the principal reasons to be given. The credit memo validation requires adverse action reasons on every recommended decline.

**Adverse media**
:   News coverage of a business or its owner that is relevant to credit risk. Findings carry a severity of low, medium or high. Rule CP-11 of the bundled policies defines which severities are an exception.

**Approval gate**
:   The point at which the workflow pauses and waits for a person to decide. A second pause, document review, occurs earlier when the extracted documents have unresolved problems. Both pauses use the interrupt mechanism of the workflow library: the case state is saved and the run resumes, possibly in another process, when the person answers.

**Approver tier**
:   The authority level required to decide a case: Analyst, Senior Credit Officer or Credit Committee. The tier follows from the loan amount and from whether any rule is an exception, according to the delegation-of-authority rule (CP-13) of the policy. An approval below the required tier is rejected.

**Audit log**
:   The append-only record of every final decision. Each record contains the hash of the previous record, so any edit or deletion is detected when the chain is verified. See [Database](database.md#audit_log).

**BM25**
:   A classic keyword-ranking function. One of the two search methods combined in policy retrieval, the other being vector search.

**Case**
:   One loan application and its underwriting run, from intake to the final decision.

**Case state**
:   The structured record the workflow builds up for a case. See [Case state](case-state.md).

**Checkpoint**
:   A saved snapshot of the case state, written after every workflow step. Checkpoints let a paused case resume after a restart.

**Circuit breaker**
:   A protection that stops calls to a tool server or model after repeated failures and retries after a short wait. A case that runs while a component is unavailable becomes a degraded run.

**Collateral coverage**
:   The appraised collateral value divided by the requested loan amount.

**Compliance profile**
:   A configuration file listing the prohibited bases of discrimination and the terms scanned for in credit memos. The bundled profile follows the US ECOA and Regulation B. It is replaceable for other jurisdictions.

**Credit memo**
:   The structured write-up prepared for the approver: recommendation, summary, strengths, concerns, conditions, adverse action reasons and limitations. It explains the recommendation and does not change it.

**Credit policy**
:   A bank's lending rules written in prose, with numbered rules CP-1 and up. The product reads the policy text at run time and applies it as written. See [Policy rules](policy-rules.md).

**Current ratio**
:   Total current assets divided by total current liabilities, a measure of liquidity.

**Debt-to-equity ratio**
:   Total liabilities divided by total equity, a measure of leverage.

**Decision rule**
:   The fixed rule that turns rule statuses into a recommendation: any fail means decline, otherwise any exception or missing data means refer, otherwise approve. It is not decided by a language model. See [Policy rules](policy-rules.md#the-decision-rule).

**Degraded run**
:   A run in which a tool, model or check was unavailable. A degraded run never recommends approve or decline; it recommends refer, and the memo lists the limitations.

**Demonstration data**
:   Optional sample applicants, statements and mock news and registry sources, enabled with the `WEALTHPILOT_DEMO` environment variable. It lets the system be tried without real documents. It is off by default.

**Document review**
:   A pause of the workflow when the extracted statements fail the consistency checks. The reviewer accepts the values, corrects them or rejects the documents.

**DSCR**
:   Debt service coverage ratio. The cash flow available for debt service divided by the debt service, including the payment on the proposed loan. The exact definition is in [Policy rules](policy-rules.md#definitions).

**ECOA and Regulation B**
:   US fair-lending rules that prohibit discrimination on bases such as race, sex and marital status.

**Exception**
:   A rule status for a situation the policy text defines as requiring referral to the Credit Committee instead of a pass or a fail.

**Grade**
:   The internal risk rating from A (best) to E (worst). It combines the PD band and the scorecard class. Policies state which grades are acceptable (rule CP-12).

**Hybrid retrieval**
:   Policy search that combines keyword search (BM25) and vector search, merges the two rankings by reciprocal rank fusion and reorders the best candidates with a reranking model.

**Interrupt**
:   The workflow library's mechanism for pausing a run until external input arrives. See approval gate.

**Loan-to-revenue ratio**
:   The requested loan amount divided by the most recent annual revenue.

**Model Context Protocol (MCP)**
:   An open protocol for offering tools to applications that use language models. The three tool servers of the product speak it over HTTP.

**NAICS**
:   North American Industry Classification System. A code identifying a business's industry; its first two digits identify the sector.

**NIM**
:   NVIDIA Inference Microservices. The hosted model endpoints the product uses for chat, document vision and reranking. Requests go through the model gateway.

**OFAC SDN list**
:   The US Treasury's list of Specially Designated Nationals and blocked persons. The product downloads it and screens the applicant and the owner against it.

**Override**
:   A final decision that differs from the recommendation, such as an approval of a recommended decline. The reviewer's reason is recorded.

**PD (probability of default)**
:   The calibrated probability that a loan like the applicant's is charged off within five years, estimated by a model trained on public SBA 7(a) loan outcomes.

**PD band**
:   The class of a PD value: low (below 2.0 percent), moderate (below 3.5 percent), elevated (below 4.5 percent) or high.

**Policy check**
:   The evaluated result of one policy rule for one case: a status, a reason and the quoted evidence.

**Precedent**
:   A previously decided case that resembles the current one. Shown for information in the memo and never a basis for a decision.

**RAG (retrieval-augmented generation)**
:   Giving a model relevant retrieved text along with the question. Here the policy sections relevant to a rule are retrieved before the rule is judged.

**Recommendation**
:   The outcome the system proposes for a case: approve, decline or refer. It is advisory; a person makes the final decision.

**Reconciliation**
:   Deterministic consistency checks on extracted financial statements: the balance sheet balances, subtotals add up, net income ties to the income statement, and bank balances roll forward month to month.

**Redaction**
:   Removing the owner's name, the street address and the ZIP code from any text before a model sees it. Redaction is on by default.

**Refer**
:   A recommendation to escalate the case for human review instead of approving or declining it. It follows from an exception, missing data or a degraded run.

**Rerank**
:   Reordering a short list of retrieved passages with a model that scores each passage against the query.

**Scorecard**
:   A pass or fail test of DSCR, leverage and liquidity against the thresholds read from the policy. The number of tests passed gives the class strong (3), adequate (2) or weak (0 or 1).

**Sealed attributes**
:   The identity part of the case state: owner name, business name, gender, name origin and address. It is kept apart from the facts shown to models and is never placed in a prompt.

**SHAP**
:   A method that attributes a model's prediction to its input features. The product uses it to list the main factors that raise a case's default probability.

**Status (rule status)**
:   The result of a policy rule for a case: pass, fail, exception, not applicable or missing data. See [Policy rules](policy-rules.md#statuses).

**Thread**
:   The identifier of one underwriting run and its saved checkpoints. Resuming a case uses the same thread identifier.

**Tool server**
:   One of the three services (`fincalc`, `policydocs`, `research`) that provide the deterministic tools to the workflow. See [Tool reference](tool-reference.md).
