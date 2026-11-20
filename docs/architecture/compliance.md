# Compliance and human approval

Four mechanisms keep the system accountable. Redaction keeps protected attributes away from models. The memo validator checks what
is written. The approval gate puts a person in charge of every decision. The audit log makes the record tamper-evident.

!!! note "The compliance profile is configuration"
    The file in `config/compliance_profiles/` is an example profile in the style of the US Equal Credit Opportunity Act and
    Regulation B. It lists prohibited bases, prohibited terms and the adverse-action requirement. The language scan uses the list of
    prohibited terms. The system is jurisdiction-agnostic: replace the profile to apply another jurisdiction's terms.

## Redaction

Redaction removes the owner's identity from any text before it reaches a language model.

| Replaced | With |
|---|---|
| Full name, "Last, First", "LAST, First", last name and first name | `[OWNER]` |
| Street address | `[ADDRESS]` |
| ZIP code | `[ZIP]` |

City and state are kept, because state is a legitimate model feature. Matching is whole-token and case-insensitive, so a first name
such as "Mark" does not alter the word "market", and a ZIP code does not match inside a longer number. Terms of two characters or fewer
are not replaced.

Redaction is applied to:

* the text of the financial and bank statements sent for extraction,
* the business label in the case facts, because the business name often contains the owner's surname,
* the research findings shown to the model.

The sealed part of the case state, which holds the owner's name, gender, name origin and address, is never placed in a prompt.
Sanctions screening needs the real names, so it runs inside the `research` tool server and only its classification reaches the model.

Redaction is on by default. The console exposes it as the option "Hide the owner's identity from the AI" under the advanced options
of New case, and the command that runs a sample applicant from the command line accepts `--no-redaction`. Turning it off is intended for controlled comparisons, such as the
[fairness evaluation](../research/e3-fairness.md). Scanned pages are sent to the vision model as images and cannot be redacted this way;
see [Known limitations](../administration/limitations.md).

## Language scan

The language scan searches text for prohibited-basis terms using whole-word, case-insensitive matching against the profile's list.
The list covers gender, sex, race, ethnicity, religion, national origin, marital status, pronouns such as "she" and "his", family
terms such as "husband" and "wife", and similar terms. Memo validation runs the scan on every memo and treats any hit as a validation
failure.

## Memo validation

The full list of checks is in [Memo validation](workflow.md#memo-validation). In short: the recommendation must match the decision
rule, every number must be traceable to the case facts, the memo must contain no prohibited language or identity details, a decline
needs adverse-action reasons that cite failed rules, and a degraded run needs a limitations section.

## Human approval

The human approval gate pauses the workflow with a payload that contains the memo, the policy checklist with citations, the ratios,
the risk factors, the grade, the research findings, any degraded reasons and any validator issues. It resumes with a decision:

| Field | Values |
|---|---|
| Decision | Approve, decline or revise |
| Approver tier | Analyst, Senior Credit Officer or Credit Committee |
| Approver id | The approver's name or identifier |
| Reason | Free text, kept on an override or a revision |

* **Tier enforcement.** The approver's tier must be at least the required tier. The required tier comes from the policy's
  delegation-of-authority rule, and is Credit Committee whenever an exception applies under policies that say so. A lower tier, or an
  invalid decision, is rejected and the gate asks again with an error message. The console form checks the same conditions before it
  submits, but the gate itself is the authority, so the rule holds for every client.
* **Revise.** A revision sends the case back to the memo writer with the reviewer's comments. Two revisions are allowed. A third
  request finalizes the case as a referral.
* **Override.** Approving when the recommendation was decline, or declining when it was approve, is recorded as an override together
  with the approver's reason.

A second gate, **document review**, appears only when document reconciliation fails after repair. The reviewer can accept the
extracted values, correct specific values by fiscal year and field, or reject the documents. Rejection closes the case as declined for
unusable documents.

## The audit log

Every decision is appended to the audit log, a table in Postgres. Each record's hash covers the previous record's hash:

```text
hash(n) = SHA-256( hash(n-1) + case id + event + canonical JSON of the payload )
```

Each record stores its predecessor's hash, so editing or deleting any past record breaks every later hash. The payload holds the
final decision record and the list of rule ids with their statuses. Appends are serialized with a table lock, so concurrent runs cannot
fork the chain.

Verify the chain from the command line, or on the History page of the console:

```bash
docker compose exec console wealthpilot audit-verify
# {"ok": true, "records": 17, "first_bad_id": null}      exit code 0
# {"ok": false, "records": 17, "first_bad_id": 9}        exit code 1
```

!!! warning "What the log does not do"
    A hash chain proves that the log was not altered after the fact. It does not prevent a database administrator from rewriting
    the entire chain. For stronger guarantees, anchor the latest hash in an external system.
