# Known limitations

WealthPilot supports an underwriter's work; it does not replace the underwriter. These are the limits to weigh before using it on real applications.
Limits of the evaluation itself are on [Limits of the evaluation](../research/limitations.md).

## Decision support, not decision making

| Limitation | Detail |
|---|---|
| **A person always decides** | Every case ends at an approval gate. The assistant never approves or declines on its own, and a run that lost a tool or check is capped at a *refer* recommendation. |
| **Policy reading can still be wrong** | The model occasionally misreads conditions such as "required only for loans above a size", and in one evaluated case invented an adverse-media finding. Numeric verification, the fixed decision rule and the memo validator contain these errors but do not remove them. The evidence quoted for every rule exists so a reviewer can check it. |
| **Results vary between runs** | Language models are not fully deterministic, even at temperature zero. An identical re-run can change an individual rule status. |
| **One example compliance profile** | The bundled prohibited-basis profile follows the style of a United States fair-lending regime. It is an example configuration, not legal advice and not a compliant implementation for any jurisdiction. |

## Data and models

| Limitation | Detail |
|---|---|
| **The default-risk model is trained on public loan data only** | It uses loan and business-profile attributes (no borrower financial statements), so statement ratios reach the decision through the policy and the scorecard, not through the model. |
| **Selective labels** | The training data contains only loans that were approved. The model says nothing about applicants a lender would have rejected. |
| **External research sources are placeholders** | Only the OFAC sanctions list is real. Adverse-media and business-registry lookups are integration points; the bundled providers are mocks that answer from optional demonstration data and otherwise return no results. Connect real providers before relying on those checks. |
| **Document understanding is validated on a limited set of layouts** | Uploads are checked for being a readable PDF of sensible size, not for being financial statements. Unusual layouts may fail the consistency checks and pause for document review. Digit errors in scanned documents are detected but not corrected automatically. |
| **Language model service** | The system calls a hosted model service. Availability, speed and rate limits depend on the account and the model; the free tier is slow. See [Model gateway and reliability](../architecture/model-gateway.md). |

## Deployment

| Limitation | Detail |
|---|---|
| **No built-in authentication** | Anyone who can reach the console can create cases and record decisions. Run it on a trusted network or behind an authenticating reverse proxy; see [Security and access](security.md). |
| **Reviewer identity is declared** | The name and authority tier set in the sidebar are written to the audit log, but nothing verifies who entered them. The approval-tier check compares the declared tier with the policy's requirement. |
| **Single node, no job queue** | Runs execute on a worker inside the console process. Leaving a page does not stop a run, but restarting the console interrupts runs in flight; they appear as *Interrupted* and are resumed from their last saved step with **Continue the run**. There is no horizontal scaling or multi-tenancy. |
| **The audit log is tamper-evident, not tamper-proof** | Anyone with database administrator access can rewrite the whole chain. Anchoring the latest hash outside the database would close that gap. |
| **Uploaded documents are stored unencrypted** | PDFs are kept in the data volume with ordinary file permissions. Apply disk or volume encryption as your policy requires. |
| **Names are masked on review screens by design** | Owner names are replaced (for example `[OWNER] Auto Inc.`) so a reviewer decides on the same facts as the model. A case is identified by its number, industry and loan amount. The identity can be revealed per case on the Application tab. |
