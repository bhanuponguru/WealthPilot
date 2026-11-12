# MCP tools

Sixteen tools on three servers (streamable HTTP at `http://127.0.0.1:<port>/mcp`). Tools return JSON objects; collections are wrapped in a key
(`rules`, `results`, `precedents`) so a single-item list is never ambiguous.

## `fincalc` — port 8101

Deterministic credit math. All functions are the same pure functions in `wealthpilot.finance` that the reference engine and tests use.

### `compute_ratios`

| Argument | Type | Notes |
|---|---|---|
| `statements` | object | **one** fiscal year (the latest). Keys used: `revenue`, `cogs`, `net_income`, `interest_expense`, `depreciation`, `current_portion_ltd`, `total_liabilities`, `total_equity`, `total_current_assets`, `total_current_liabilities` |
| `loan_amount` | number | requested amount |
| `term_months` | integer | requested term |
| `collateral_value` | number, optional | appraised collateral |

Returns `cash_flow_available`, `debt_service`, `dscr`, `debt_to_equity`, `current_ratio`, `loan_to_revenue`, `collateral_coverage`, `gross_margin`, `net_margin`
(`null` where a denominator is zero or an input is missing).

```text
DSCR = (net income + interest expense + depreciation)
       / (interest expense + current portion of long-term debt + annual payment on the proposed loan)
```

The proposed loan is amortised monthly at an assumed **9 %** over the requested term.

### `amortize`
`(loan_amount, annual_rate, term_months)` → `{monthly_payment, annual_payment}`. `annual_rate` is a fraction (`0.09`).

### `trend`
`(values: list[number])` — oldest to newest → `{yoy_growth: [..], direction: "improving" | "declining" | "flat"}` (a direction needs every year-on-year change beyond ±2 %).

### `stress_test`
`(statements, loan_amount, term_months, revenue_drop = 0.10)` → `{revenue_drop, stressed_dscr}`: revenue falls and the lost sales lose their gross margin.

### `compare`
`(value | null, op, threshold)` with `op` in `>=, <=, >, <, ==` → `{result: true | false | null, reason: null | "missing_data"}`. Use for every policy threshold check.

### `scorecard`
`(ratios, min_dscr, max_debt_to_equity, min_current_ratio)` → `{tests: {dscr, debt_to_equity, current_ratio}, passed, class: "strong" | "adequate" | "weak"}`.

### `grade`
`(pd, scorecard_class)` → `{pd_band, scorecard_class, grade: "A".."E"}`. See [the decision rule](../concepts/decision-rule.md#risk-grade).

### `score_pd`

| Argument | Type |
|---|---|
| `profile` | object: `state`, `business_type`, `fixed_or_variable`, `jobs_supported`, `franchise` |
| `loan_amount`, `term_months` | number, integer |
| `years_in_business` | number |
| `naics` | string (6-digit NAICS) |
| `has_collateral` | boolean |

Returns `{pd, model_version, pd_band, reasons: [{feature, reason, shap, value}]}` — a calibrated 5-year default probability and the top risk-increasing SHAP factors.

## `policydocs` — port 8102

### `list_rules`
`(policy_id)` → `{"rules": [{rule_id, title}, ...]}`.

### `search_policy`
`(query, policy_id, k = 4)` → `{"results": [{rank, rule_ids, title, text}], "degraded": bool}`. Hybrid BM25 + vector retrieval over the structure-aware chunks, then NIM rerank.
`degraded: true` means the reranker was unavailable and the fused order was kept.

### `get_rule`
`(policy_id, rule_id)` → `{rule_id, title, text}`, or `{"error": "..."}` for an unknown rule.

### `similar_precedents`
`(summary, k = 3)` → `{"precedents": [{case_id, summary, decision, grade, similarity}]}`. Informational only; never a basis for a decision.

## `research` — port 8103

### `ofac_screen`
`(name)` → `{name, match_count, matches: [{list, name, type, program, score}]}`. Fuzzy token-sort match against the OFAC SDN list (`list: "OFAC-SDN"`) and a synthetic watchlist
(`"SYNTH-WATCHLIST"`); only scores ≥ 92 are returned.

### `adverse_media`
`(subject, owner = "")` → `{subject, article_count, max_severity: "low" | "medium" | "high" | null, articles: [{headline, severity, date, source}]}`. **Mock** corpus.

### `registry_lookup`
`(business_name, state = "")` → `{found: true, status, incorporation_year, state}` or `{found: false}`. **Mock** registry.

### `industry_default_stats`
`(naics2)` → `{naics2, default_rate, n, portfolio_rate}` — 5-year default rate for the 2-digit sector in the SBA data (`n` loans), or `default_rate: null` if unknown.

## Calling from Python

```python
from wealthpilot.mcp_client import load_tools, call

tools = await load_tools()                                   # {name: LangChain tool}
await call(tools, "compare", value=1.22, op=">=", threshold=1.30)   # {'result': False, 'reason': None}
```

`call(tools, tool_name, /, **args)` takes the tool name positionally, so tool arguments named `name` do not collide.
