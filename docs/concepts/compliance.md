# Compliance and human approval

Four mechanisms keep the system accountable: **redaction** keeps protected attributes away from models, the **memo validator** checks what
is written, the **approval gate** puts a person in charge of every decision, and the **audit log** makes the record tamper-evident.

!!! note "The compliance profile is configuration"
    `data/compliance_profiles/us_example.yaml` is an *example* (ECOA / Regulation B style): it lists prohibited bases, prohibited terms and
    adverse-action requirements. The system is policy-agnostic — swap the file for another jurisdiction's profile.

## Redaction

`wealthpilot.compliance.redaction.Redactor` removes the owner's identity before any text reaches an LLM.

| Replaced | With |
|---|---|
| full name, `Last, First`, `LAST, First`, last name, first name | `[OWNER]` |
| street address | `[ADDRESS]` |
| ZIP code | `[ZIP]` |

City and state are **kept** (state is a legitimate model feature). Matching is **whole-token and case-insensitive**.

!!! bug "A bug the fairness experiment found"
    The first version matched substrings. For an owner named *Mark* it rewrote "market" as "`[OWNER]`et", corrupting prompts, and made the
    leak meter report false leaks. Matching is now whole-word (`(?<![A-Za-z0-9])term(?![A-Za-z0-9])`) with a regression test. A direct
    comparison confirmed the bug did not affect the E0, E1 or E4 inputs (identical output on all 135 texts).

Where redaction is applied:

* document text sent for extraction (`parse`),
* the business label in the case facts (the business name often contains the owner's surname),
* research findings shown to the LLM.

`sealed` — the part of the case state that holds the owner's name, gender, name origin and address — is **never** placed in a prompt.
Sanctions screening needs the real names, so it runs inside the `research` MCP server and only its *classification* reaches the model.

Redaction can be turned off (`--no-redaction`) to run the counterfactual experiments.

## Language scan

`scan(text)` returns any prohibited-basis term found, using whole-word matching against the profile's list (gender, sex, race, ethnicity,
religion, national origin, marital status, pronouns such as *she/he/her/his*, family terms such as *husband/wife*, and similar). The memo validator
runs it on every memo and treats a hit as a validation failure.

## Memo validation

See [Memo validation](workflow.md#memo-validation) for the full list. In short: the recommendation must match the decision rule, every number
must be traceable to the case facts, no prohibited language or identity details, adverse-action reasons for declines, and a limitations section for
degraded runs.

## Human approval

`human_approval` pauses the graph with `interrupt()` and a payload containing the memo, the policy checklist with citations, ratios, risk factors,
grade, research findings, any degraded reasons and any validator issues. It resumes with:

```json
{
  "decision": "approve | decline | revise",
  "approver_tier": "Analyst | Senior Credit Officer | Credit Committee",
  "approver_id": "sco-7",
  "reason": "free text (kept on override or revise)"
}
```

* **Tier enforcement.** The approver's tier must be **at least** the required tier (computed from the policy's delegation-of-authority rule, or
  *Credit Committee* when any exception applies). A lower tier — or an invalid decision — is rejected and the gate asks again with an error message.
* **Revise.** `revise` sends the case back to the memo writer with the reviewer's comments; up to two revisions are allowed, after which the case
  is escalated (`refer`).
* **Override.** *approve* when the recommendation was *decline* (or vice versa) is recorded as an override with the approver's reason.

A second gate, **`doc_review`**, appears only when document reconciliation fails after repair. The reviewer can `accept`, `correct`
(supplying `{fiscal_year: {field: value}}`) or `reject` (the case is finalised as declined for unusable documents).

## The audit log

Every decision is appended to the Postgres table `audit_log` by `wealthpilot.compliance.audit`:

```text
hash_n = sha256( hash_(n-1) + case_id + event + canonical_json(payload) )
```

Each record stores its predecessor's hash, so **editing or deleting any past record breaks every later hash**. The payload holds the final
decision record plus the `(rule_id, status)` list.

```bash
uv run wealthpilot audit-verify
# {"ok": true, "records": 17, "first_bad_id": null}      exit code 0
# {"ok": false, "records": 17, "first_bad_id": 9}        exit code 1
```

Appends are serialised with a table lock so concurrent runs cannot fork the chain. A unit test tampers with a record and confirms
`verify()` reports exactly that record, then restores it.

!!! tip "What the log does *not* do"
    A hash chain proves the log was not altered *after the fact*; it does not prevent a database administrator from rewriting the whole chain.
    For stronger guarantees, anchor the latest hash somewhere external.
