# Limitations and future work

WealthPilot is a **research and teaching project**. These limits matter when interpreting its results or considering any real-world use.

## Scope and data

| Limitation | Detail |
|---|---|
| **Synthetic applicants and documents** | Formats, label noise, fraud patterns and financial structure are far simpler than reality. Real scans, handwriting, notes to the accounts and inconsistent templates are harder. |
| **Mock external sources** | Adverse media and the business registry read the synthetic world. Only the OFAC list is real. |
| **No real borrower financials in the risk model** | The SBA data has loan and business-profile fields only, so the PD model cannot use the parsed ratios; they enter through the policy and the scorecard. |
| **Selective labels** | The SBA data contains only *approved* loans, so the PD model and the fairness audit say nothing about applicants a lender would have rejected. |
| **Proxy groups, not protected classes** | The SBA file has no race, gender or ethnicity fields. The real-data fairness audit uses region, business age and legal form. |
| **One jurisdiction's example profile** | The compliance profile is an ECOA/Reg-B-*style* example, not legal advice or a compliant implementation. |

## Model and system

| Limitation | Detail |
|---|---|
| **One LLM family, one usable chat model** | Only `nemotron-3.5-lightning-30b` was dependable; results on other models will differ. The 550B model degraded to garbled output. |
| **Free-tier throughput** | 5–15 chat calls per minute; per-model throttling; model availability changed during development. This bounds experiment size. |
| **Remaining policy-reading errors** | The model still misreads "required only for loans above a size" conditions (7 of the 12 remaining mismatches in [E0](../experiments/e0-policy-adherence.md)) and once **invented an adverse-media finding**. The decision rule and verification contain these errors but do not eliminate them. |
| **Scanned documents** | Reconciliation *detects* OCR digit errors but automatic repair did not fix them; a human must. Identity in scanned images cannot be text-redacted. |
| **Nondeterminism** | Models vary run to run even at temperature 0 (a plain uncached re-run changed 1 of 24 rule statuses and once changed document extraction enough to fail reconciliation). |
| **The audit log is tamper-evident, not tamper-proof** | Someone with database administrator access can rewrite the whole chain; anchoring the head hash externally would fix that. |
| **Local, single-node deployment** | No authentication, multi-tenancy, queueing or horizontal scaling. Services bind to `127.0.0.1`. |

## The console

| Limitation | Detail |
|---|---|
| **No authentication or authorisation** | Anyone who can reach the port can underwrite and decide. The approver's tier and id are *declared* in the form, not verified. It binds to `127.0.0.1` by default; do not expose it. |
| **Single-process worker, no queue** | Runs execute on one background worker thread inside the console process, so leaving the page or closing the tab does not stop them. There is no durable job queue: restarting the console mid-run interrupts the run, which then shows as *Interrupted* and is continued from its last checkpoint by hand (**Continue the run**). Concurrent runs share the same model-rate budget. |
| **Reviewer identity is declared, not verified** | The sidebar's name and authority tier pre-fill the decision form and go into the audit log, but nothing proves who typed them. |
| **Masked names on the review screens** | By design the business name is shown with owner names masked (e.g. `[OWNER] Auto Inc.`); a case is identified by case number, industry and loan amount. Identity can be revealed per case on the *Application* tab. |
| **Document understanding is untested beyond the generated layouts** | Uploads are validated for being a readable PDF of sensible size, not for being financial statements. Unusual layouts may fail reconciliation and pause for document review. |
| **Identity attributes are minimal** | The new-application form never asks for gender or name origin (they are `unspecified`); only the owner's name and address are used, for screening and redaction. |
| **Uploads are stored unencrypted** | PDFs are written under `data/uploads/<case id>/` (git-ignored) with normal file permissions. |
| **Screenshots are generated, not tested pixel-for-pixel** | `scripts/capture_screenshots.py` documents what the pages look like at one viewport size; layout at other sizes is not verified. |

## Evaluation

| Limitation | Detail |
|---|---|
| **Small samples** | E0: 12 cases × 2 policies; E1: 12 cases; E3(c): 3 cases; E4: 4 cases per profile. Intervals are wide. |
| **Ground truth is ours** | The reference engine encodes our reading of the policy text; the policies and engine were written together. This measures consistent application of explicit rules, not discovery of ambiguity. |
| **Counterfactual "on" arm** | With redaction on and identical prompts, zero flips is guaranteed by the cache; the evidence is the leak rate and the uncached noise floor. |
| **Mixed code versions** | The system was hardened while experiments ran; see [which code produced which result](../experiments/index.md#which-code-produced-which-result). |
| **First-pass adverse-action completeness not measured** | It is enforced and unit-tested but its rate was not separately measured. |

## Future work

* **Larger and more adversarial evaluation** — more cases, more policy variants, ambiguous and contradictory policy text, real-world document samples.
* **Fix the CP-8 class of errors** — for example by extracting conditions as structured predicates (`loan_amount > 150000`) that code evaluates, extending the numeric-verification idea from *checking* comparisons to *performing* them.
* **Grounded facts** — verify that facts the model cites (such as an adverse-media severity) match the case data and flag hallucinated facts automatically.
* **A second model family** — measure how much of the behaviour is model-specific; revisit a fallback chain once a second dependable model exists.
* **Real data sources** — plug a real news and registry provider into the `research` MCP server (the interface is unchanged).
* **Stronger audit** — periodically anchor the audit chain's head hash in an external system.
* **Operational hardening** — authentication on the MCP servers and console (with *verified* approver identity and tier), a background task queue so runs do not block the page, and containerised MCP servers.
* **Active learning from overrides** — study (carefully, given bias risk) how human overrides could improve prompts or thresholds without feeding approver decisions back automatically.
* **Langfuse or OpenTelemetry export** — for teams with more memory budget.
