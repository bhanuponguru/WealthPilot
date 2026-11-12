# Case state

The LangGraph state (`wealthpilot.graph.state.CaseState`) is a `TypedDict`. Agents write **typed results** here; their chat messages stay private to each call.
Fields marked *reducer* merge concurrent writes (the parallel `analyst` and `research` branches).

## Identity and inputs

| Field | Type | Description |
|---|---|---|
| `case_id` | str | case identifier, e.g. `C004` |
| `policy_id` | str | policy applied, e.g. `strict` |
| `applicant_id` | str | stable id (SHA-1 prefix of owner + business name) for long-term memory |
| `redaction` | bool | whether protected attributes are redacted from text sent to models |
| `application` | dict | **LLM-safe** facts: `business_label` (redacted if enabled), `industry_name`, `naics`, `years_in_business`, `loan_amount`, `term_months`, `purpose`, `collateral_value`, `guarantor_provided`, `profile` |
| `sealed` | dict | owner name, business name, gender, name origin, address — **never placed in a prompt** |
| `doc_paths` | dict | `{"financials": path, "bank": path}` |
| `history` | list | the applicant's prior decisions (long-term memory) |

## Documents

| Field | Description |
|---|---|
| `extracted` | `{fiscal_year: {field: number}}` — 19 fields per year |
| `doc_kind` | `text` or `image` |
| `reconciliation_issues` | failed consistency checks after repair |
| `bank`, `bank_issues` | extracted bank-statement summary and its roll-forward issues |
| `doc_review` | the human's document-review decision (`accept` / `correct` / `reject`) |

## Analysis

| Field | Description |
|---|---|
| `ratios` | output of `compute_ratios` (or `None` if it could not be computed) |
| `analysis` | fiscal year, revenue trend, 10 % stress result, narrative, fields estimated from the prior year |
| `research` | `sanctions_status`, `adverse_media_max_severity`, `articles` (redacted), `registry`, `industry_default_rate`, `summary` |
| `risk` | `pd`, `pd_band`, `model_version`, `reasons` (SHAP) |
| `thresholds` | numeric thresholds extracted from policy prose: `min_dscr`, `max_debt_to_equity`, `min_current_ratio` |
| `policy_checks` | list of rule results — see below |
| `required_tier` | `Analyst` · `Senior Credit Officer` · `Credit Committee` |
| `grade` | `{pd_band, scorecard_class, grade, scorecard}` or `None` |
| `recommendation` | `approve` · `decline` · `refer`, derived by code |

### A `policy_checks` entry (illustrative)

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

`status` is one of `pass`, `fail`, `exception`, `not_applicable`, `missing_data`. `numeric_check` is `ok`, `repaired`, `failed`, `no_comparisons` or `none`.
A check may also carry `degraded: true` when its tools were unavailable.

## Memo and decision

| Field | Description |
|---|---|
| `memo` | `recommendation`, `summary`, `strengths`, `concerns`, `conditions`, `adverse_action_reasons`, `limitations` |
| `validator_issues` | problems found by the memo validator |
| `human_decision` | `{decision, approver_tier, approver_id, reason}` |
| `final` | the finalised decision record (written to long-term memory and the audit log) |

## Control and diagnostics

| Field | Description |
|---|---|
| `loops` | counters: `policy`, `memo`, `revise` |
| `degraded` | *reducer* (logical OR) — any tool/check was unavailable |
| `degraded_reasons` | *reducer* (list concatenation) |
| `errors` | *reducer* (list concatenation) |
| `trace` | *reducer* (list concatenation) — step log with timestamps |

## The `final` record

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
