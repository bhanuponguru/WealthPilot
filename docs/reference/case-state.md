# Case state

The structured record the underwriting workflow builds up for one case.

Every agent and processing step writes typed results into the case state. The text of a model conversation stays private to the step that produced it and is not part of the state. The state is saved to the database after every step (see [Database](database.md)), which is what lets a paused case resume in a new process. The console and the `show` command read it to present a case.

Four fields merge writes from steps that run in parallel (the financial analysis and the credit research): `degraded` (logical OR) and `degraded_reasons`, `errors` and `trace` (lists are concatenated). All other fields are written by one step at a time. For the workflow see [The underwriting workflow](../architecture/workflow.md).

## Identity and inputs

| Field | Type | Meaning |
|---|---|---|
| `case_id` | string | Case identifier |
| `policy_id` | string | The credit policy applied, for example `strict` |
| `applicant_id` | string | Stable identifier derived from the owner and business name; links the case to the applicant's earlier decisions |
| `redaction` | boolean | Whether the owner's identity is removed from every text sent to a model |
| `application` | object | Facts that may be shown to models (see below) |
| `sealed` | object | Owner name, business name, gender, name origin and address. Never placed in a prompt |
| `doc_paths` | object | Locations of the two documents: `financials` and `bank` |
| `history` | list | Earlier decisions for the same applicant: case id, decision, grade and decision time |

The `application` object holds `business_label` (the business name, with the owner's identity redacted when redaction is on), `industry_name`, `naics`, `years_in_business`, `loan_amount`, `term_months`, `purpose`, `collateral_value`, `guarantor_provided` and `profile` (state, business type, fixed or variable rate, jobs supported, franchise flag).

## Documents

| Field | Type | Meaning |
|---|---|---|
| `extracted` | object | Statement values by fiscal year: `{year: {field: number}}`. Up to 19 fields per year: 7 income-statement and 12 balance-sheet items |
| `doc_kind` | string | `text` for a PDF with a text layer, `image` for a scanned document |
| `reconciliation_issues` | list | Consistency checks that still fail after the automatic repair attempt |
| `bank` | object | The monthly summary extracted from the bank statement: account holder, signatory and per-month opening balance, deposits, withdrawals and closing balance |
| `bank_issues` | list | Bank statement roll-forward problems |
| `doc_review` | object | The reviewer's decision on document problems: `action` (`accept`, `correct` or `reject`) and, for `correct`, the corrected values |

A non-empty `reconciliation_issues` or `bank_issues` list pauses the workflow for document review. See [Document parsing](../architecture/document-parsing.md).

## Analysis

| Field | Type | Meaning |
|---|---|---|
| `ratios` | object or null | Output of the ratio calculation for the latest fiscal year; null when it could not be computed |
| `analysis` | object | `fiscal_year`, `revenue_trend`, `stress` (DSCR after a 10 percent revenue drop), `narrative` and `estimated_fields` (values taken from the prior year, each labeled as estimated). When ratios could not be computed it holds `missing` (the absent fields) or `error` instead |
| `research` | object | The credit research result (see below) |
| `risk` | object or null | `pd` (5-year default probability), `pd_band`, `model_version` and `reasons` (the main risk-raising factors); null when the risk tool was unavailable |
| `thresholds` | object | Numeric thresholds read from the policy text: `min_dscr`, `max_debt_to_equity`, `min_current_ratio` |
| `policy_checks` | list | One entry per evaluated rule (see below) |
| `required_tier` | string | The lowest approval authority allowed to decide: `Analyst`, `Senior Credit Officer` or `Credit Committee` |
| `grade` | object or null | `pd_band`, `scorecard_class`, `grade` (`A` to `E`) and `scorecard` (the three tests); null when it could not be computed |
| `recommendation` | string | `approve`, `decline` or `refer`, derived from `policy_checks` by the fixed decision rule |

The `research` object holds:

| Key | Meaning |
|---|---|
| `sanctions_status` | `no_match`, `possible_match` (best score from 92 up to 97), `confirmed_match` (97 or above) or `not_performed` when the research tools were unavailable |
| `adverse_media_max_severity` | `low`, `medium`, `high`, or null when there is no finding |
| `articles` | Headlines of the adverse media found, with the owner's identity redacted |
| `registry` | The business registry result |
| `industry_default_rate` | The 5-year default rate of the borrower's sector |
| `summary` | Short summary of the findings |

### Policy check entry

`policy_checks` contains one entry for each of the rules CP-1 to CP-12 of the policy. CP-13 (approval authority) produces `required_tier` and is not listed.

```json
{
  "rule_id": "CP-8",
  "title": "Collateral",
  "status": "not_applicable",
  "reason": "The request is USD 100,000, at or below the USD 150,000 threshold.",
  "evidence": "\"For requests above USD 150,000 collateral coverage must be at least 1.00.\" Case: loan_amount = 100000.",
  "extracted_threshold": 1.0,
  "citation": "strict/CP-8",
  "numeric_check": "ok"
}
```

| Key | Meaning |
|---|---|
| `status` | `pass`, `fail`, `exception`, `not_applicable` or `missing_data`. See [Policy rules](policy-rules.md#statuses) |
| `reason` | One-sentence justification |
| `evidence` | The decisive policy sentence and the case values it was applied to |
| `extracted_threshold` | The main numeric threshold stated in the rule, or null |
| `citation` | Policy and rule, in the form `<policy>/<rule>` |
| `numeric_check` | Result of the deterministic re-check of the numeric comparisons: `ok`, `repaired` (a wrong comparison was corrected on a second attempt), `failed` (still inconsistent; the status becomes `missing_data`), `no_comparisons` or `none` (no usable answer) |
| `degraded` | Present and `true` when the policy tools were unavailable and the rule could not be assessed |

## Memo and decision

| Field | Type | Meaning |
|---|---|---|
| `memo` | object | The credit memo: `recommendation`, `summary`, `strengths`, `concerns`, `conditions`, `adverse_action_reasons` (rule id and plain-language reason) and `limitations` |
| `validator_issues` | list | Problems the memo validation found in the latest memo; empty when the memo passed |
| `human_decision` | object | The reviewer's decision: `decision` (`approve`, `decline` or `revise`), `approver_tier`, `approver_id` and `reason` |
| `final` | object | The final decision record, also written to the decision memory and the audit log |

### Final record

```json
{
  "case_id": "C004", "policy_id": "strict",
  "recommendation": "decline", "decision": "decline",
  "override": false, "override_reason": null,
  "approver": "sco-7", "approver_tier": "Senior Credit Officer", "required_tier": "Senior Credit Officer",
  "grade": "B", "pd": 0.0264,
  "degraded": false, "degraded_reasons": [], "documents_rejected": false,
  "decided_at": "2026-11-11T20:11:03"
}
```

`override` is `true` when the reviewer approved a recommended decline or declined a recommended approval; `override_reason` then carries the reviewer's reason. When the reviewer rejects the documents, the decision is `decline` and `documents_rejected` is `true`. When the revision limit is reached without a decision, the decision is `refer`.

## Control and diagnostics

| Field | Type | Meaning |
|---|---|---|
| `loops` | object | Counters that bound the repeat cycles: `policy` (recomputation after missing data, at most 1), `memo` (memo rewrites after failed validation) and `revise` (revisions requested by the reviewer, at most 2) |
| `degraded` | boolean | `true` when any tool, model or check was unavailable during the run |
| `degraded_reasons` | list | One entry per unavailable component |
| `errors` | list | Errors raised by steps, such as an unreadable document |
| `trace` | list | One entry per executed step, with the step name, a timestamp and step-specific details |
