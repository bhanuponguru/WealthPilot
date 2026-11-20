# Tool reference

The 16 tools exposed by the three tool servers: arguments, return values and behavior.

The servers run in the `mcp` service and speak the Model Context Protocol over streamable HTTP at `http://<host>:<port>/mcp`. They are internal to the deployment and not published outside the Docker network. Every tool returns a JSON object. Collections are wrapped in a named key (`rules`, `results`, `precedents`, `matches`, `articles`) so that a one-item list is never ambiguous. For the design of the servers see [Tool servers](../architecture/tool-servers.md).

| Server | Port | Tools |
|---|---|---|
| `fincalc` | 8101 | `compute_ratios`, `amortize`, `trend`, `stress_test`, `compare`, `scorecard`, `grade`, `score_pd` |
| `policydocs` | 8102 | `list_rules`, `search_policy`, `get_rule`, `similar_precedents` |
| `research` | 8103 | `ofac_screen`, `adverse_media`, `registry_lookup`, `industry_default_stats` |

## fincalc

Deterministic credit arithmetic and the default-risk model. The workflow never lets a language model do arithmetic: every ratio, comparison and grade comes from these tools.

### compute_ratios

Computes the credit ratios for one fiscal year and a loan request.

| Argument | Type | Description |
|---|---|---|
| `statements` | object | Statements of one fiscal year, normally the latest. Required keys: `revenue`, `cogs`, `net_income`, `interest_expense`, `depreciation`, `current_portion_ltd`, `total_liabilities`, `total_equity`, `total_current_assets`, `total_current_liabilities` |
| `loan_amount` | number | Requested amount |
| `term_months` | integer | Requested term in months |
| `collateral_value` | number, optional | Appraised collateral value |

Returns `cash_flow_available`, `debt_service`, `dscr`, `debt_to_equity`, `current_ratio`, `loan_to_revenue`, `collateral_coverage`, `gross_margin` and `net_margin`. A ratio is `null` when its denominator is zero or, for `collateral_coverage`, when no collateral value was given. Ratios are rounded to four decimals.

```text
DSCR = (net income + interest expense + depreciation)
       / (interest expense + current portion of long-term debt + annual payment on the proposed loan)
```

The proposed loan is amortized monthly at an assumed rate of 9 percent over the requested term. This is the definition used in both bundled policies.

### amortize

| Argument | Type | Description |
|---|---|---|
| `loan_amount` | number | Principal |
| `annual_rate` | number | Annual interest rate as a fraction, for example `0.09` |
| `term_months` | integer | Term in months |

Returns `monthly_payment` and `annual_payment` (twelve monthly payments), rounded to cents.

### trend

| Argument | Type | Description |
|---|---|---|
| `values` | list of numbers | A series ordered from oldest to newest, for example revenue by year |

Returns `yoy_growth`, the year-on-year growth rates (`null` where the earlier value is zero), and `direction`: `improving` when every change exceeds +2 percent, `declining` when every change is below -2 percent, otherwise `flat`.

### stress_test

| Argument | Type | Description |
|---|---|---|
| `statements` | object | Statements of one fiscal year, as for `compute_ratios` |
| `loan_amount` | number | Requested amount |
| `term_months` | integer | Requested term |
| `revenue_drop` | number, default `0.10` | Fraction by which revenue falls |

Returns `revenue_drop` and `stressed_dscr`. The lost sales are assumed to lose their gross margin, which reduces net income by the same amount.

### compare

| Argument | Type | Description |
|---|---|---|
| `value` | number or null | The value to test |
| `op` | string | One of `>=`, `<=`, `>`, `<`, `==` |
| `threshold` | number | The reference value |

Returns `{"result": true | false | null, "reason": null | "missing_data"}`. `result` is `null` with reason `missing_data` when `value` is `null`. An unsupported operator is an error. The tool is intended for every policy threshold check so that no comparison depends on a language model.

### scorecard

| Argument | Type | Description |
|---|---|---|
| `ratios` | object | The output of `compute_ratios` |
| `min_dscr` | number | Minimum DSCR, read from the policy |
| `max_debt_to_equity` | number | Maximum debt-to-equity, read from the policy |
| `min_current_ratio` | number | Minimum current ratio, read from the policy |

Returns `tests` (a Boolean per test: `dscr`, `debt_to_equity`, `current_ratio`), `passed` (number of tests passed) and `class`: `strong` (3 passed), `adequate` (2) or `weak` (0 or 1). A missing ratio fails its test. Debt-to-equity also fails when negative.

### grade

| Argument | Type | Description |
|---|---|---|
| `pd` | number | Probability of default as a fraction |
| `scorecard_class` | string | `strong`, `adequate` or `weak` |

Returns `pd_band` (`low`, `moderate`, `elevated` or `high`), `scorecard_class` and `grade` (`A` to `E`). The PD band sets the starting grade and the scorecard class moves it down by 0 (strong), 1 (adequate) or 2 (weak) steps, capped at `E`. The PD band limits are 2.0, 3.5 and 4.5 percent. See [The decision rule](../architecture/decision-rule.md).

### score_pd

Scores the 5-year probability of default with the model trained on public SBA 7(a) loan outcomes.

| Argument | Type | Description |
|---|---|---|
| `profile` | object | Keys `state`, `business_type`, `fixed_or_variable`, `jobs_supported`, `franchise` |
| `loan_amount` | number | Requested amount |
| `term_months` | integer | Requested term |
| `years_in_business` | number | Years since incorporation |
| `naics` | string | 6-digit NAICS code |
| `has_collateral` | boolean | Whether collateral is offered |

Returns `pd` (calibrated probability), `model_version`, `pd_band` and `reasons`: up to three factors that raise the risk, each with `feature`, a plain-language `reason`, `shap` (contribution) and `value`. The list is empty when no factor raises the risk. See [Risk model](../architecture/risk-model.md).

## policydocs

Retrieval over the credit policies and the memory of decided cases. The policy index is built by the `mcp` service on start and can be rebuilt with `wealthpilot ingest-policy`.

### list_rules

| Argument | Type | Description |
|---|---|---|
| `policy_id` | string | The policy folder name, for example `strict` |

Returns `{"rules": [{"rule_id", "title"}]}` for every `CP-<n>` section of the policy. The list is empty for an unknown or unindexed policy.

### search_policy

| Argument | Type | Description |
|---|---|---|
| `query` | string | What to look for |
| `policy_id` | string | The policy folder name |
| `k` | integer, default `4` | Number of passages to return |

Returns `{"results": [{"rank", "rule_ids", "title", "text"}], "degraded": boolean}`. Retrieval combines keyword (BM25) and vector search over the policy sections and reorders the best candidates with a reranking model. `degraded` is `true` when the reranker was unavailable and the combined order was kept. When the policy is not indexed, `results` is empty, `degraded` is `true` and a `note` explains why. See [Policy retrieval](../architecture/policy-retrieval.md).

### get_rule

| Argument | Type | Description |
|---|---|---|
| `policy_id` | string | The policy folder name |
| `rule_id` | string | For example `CP-3` |

Returns `{"rule_id", "title", "text"}`, or `{"error": "unknown rule ..."}` when the policy has no such rule.

### similar_precedents

| Argument | Type | Description |
|---|---|---|
| `summary` | string | Description of the case to match |
| `k` | integer, default `3` | Number of cases to return |

Returns `{"precedents": [{"case_id", "summary", "decision", "grade", "similarity"}]}`, ordered by semantic similarity to previously decided cases. The result is informational and is never a basis for a decision. See [Memory](../architecture/memory.md).

## research

Sanctions screening, adverse media, business registry and sector statistics.

### ofac_screen

| Argument | Type | Description |
|---|---|---|
| `name` | string | Person or company name |

Returns `{"name", "match_count", "matches": [{"list", "name", "type", "program", "score"}]}`. The name is matched fuzzily (token-sort similarity, 0 to 100) against the OFAC Specially Designated Nationals list downloaded into the `data` volume (`list: "OFAC-SDN"`) and, when demonstration data is enabled, against a sample watchlist (`list: "WATCHLIST"`). Only matches scoring 92 or higher are returned, at most three. Without the downloaded list the result is empty.

### adverse_media

| Argument | Type | Description |
|---|---|---|
| `subject` | string | Business name |
| `owner` | string, default empty | Owner name |

Returns `{"subject", "article_count", "max_severity", "articles": [{"headline", "severity", "date", "source"}]}`. `max_severity` is `low`, `medium`, `high` or `null` when no article was found.

This tool is a mock provider. It reads a sample news file from the demonstration data and returns empty results when that data is not present. It marks the place where a real news provider is integrated.

### registry_lookup

| Argument | Type | Description |
|---|---|---|
| `business_name` | string | Business name |
| `state` | string, default empty | Two-letter state code to restrict the match |

Returns `{"found": true, "status", "incorporation_year", "state"}` for a match, otherwise `{"found": false}`.

This tool is a mock provider. It matches against the sample applicants of the demonstration data and returns `{"found": false}` when that data is not present. It marks the place where a real business registry is integrated.

### industry_default_stats

| Argument | Type | Description |
|---|---|---|
| `naics2` | string | 2-digit NAICS sector |

Returns `{"naics2", "default_rate", "n", "portfolio_rate"}`: the 5-year default rate of SBA 7(a) loans approved in fiscal years 2010 to 2019 in that sector, the number of loans behind it, and the default rate across all sectors for comparison. For an unknown sector `default_rate` is `null` and `n` is `0`, and `portfolio_rate` is absent. The statistics ship with the product in `artifacts/industry_stats.json`.

!!! note "Mock providers and demonstration data"
    `adverse_media` and `registry_lookup` are the only tools that depend on optional demonstration data. Real deployments replace them with provider integrations that keep the same arguments and return values. Sanctions screening and sector statistics work without demonstration data.
