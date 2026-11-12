# Agents and tools

WealthPilot has **six agent roles**. "Agent" here means a graph node with a defined responsibility; they differ in how much of
the work an LLM does. The table is deliberately blunt about it.

| Role | Calls an LLM? | Calls tools? | Authoritative output comes from |
|---|---|---|---|
| [Parser](#parser) | yes (chat or vision) | no | LLM extraction, **verified by code** (reconciliation) |
| [Financial Analyst](#financial-analyst) | yes (narrative only) | yes (`fincalc` via MCP) | deterministic tool calls |
| [Credit Research](#credit-research) | only to summarise findings | yes (`research` via MCP) | deterministic tool calls and code |
| [Risk Scorer](#risk-scorer) | **no** | yes (`fincalc.score_pd`) | the trained model |
| [Policy / Compliance](#policy-compliance) | yes (judging rules) | yes (`policydocs`, `fincalc`) | LLM judgement, **verified by code** |
| [Memo Writer](#memo-writer) | yes | yes (`policydocs.similar_precedents`) | LLM prose, **validated by code** |

!!! info "No supervisor agent"
    The original design called for an LLM supervisor. It was replaced by deterministic routing: control flow became testable and
    repeatable, and it removed a source of nondeterminism from the experiments. See [Design decisions](../project/decisions.md).

## Parser

Turns two PDFs into numbers: the financial statements (income statement and balance sheet, one to three fiscal years) and a
12-month bank statement summary.

* **Text-layer PDFs** — words are re-assembled into tables by their coordinates so each row states its values *by year*; an LLM then maps
  row labels to 19 canonical fields.
* **Scanned PDFs** — each page is sent to the NIM vision model.
* The result is **reconciled** (balance sheet balances, net income ties, bank balances roll forward) and, if inconsistent, re-extracted
  once with the failures described to the model.

Full detail: [Document parsing](document-parsing.md).

## Financial Analyst

Calls three MCP tools directly and deterministically — `compute_ratios`, `trend` (revenue) and `stress_test` (10 % revenue drop) —
and then lets an agent (`langchain.agents.create_agent` with the `fincalc` tools) write a five-sentence narrative from those figures.
The **ratios in state are the deterministic results**; if the agent calls extra what-if tools, those do not overwrite them.

If the `policy` step later reports missing data, `analyst_retry` recomputes ratios using the prior year's value for any field missing in the
latest year, and records which fields were estimated.

## Credit Research

Runs five tool calls concurrently through the `research` MCP server:

| Call | Purpose |
|---|---|
| `ofac_screen(owner)` and `ofac_screen(business)` | fuzzy-match against the OFAC SDN list and a synthetic watchlist |
| `adverse_media(business, owner)` | mock media corpus, returns articles with a severity |
| `registry_lookup(business, state)` | mock business registry |
| `industry_default_stats(naics2)` | 5-year default rate for the SBA sector |

**Code, not the LLM, classifies sanctions matches:** a best score ≥ 97 is `confirmed_match`, 92–97 is `possible_match`, none is `no_match`.
The LLM never sees names. If there are articles or matches, one LLM call writes a two-sentence summary from the *redacted* findings.

## Risk Scorer

Makes one tool call: `fincalc.score_pd`, which returns a calibrated 5-year default probability, a PD band and the top risk-increasing
SHAP reasons. There is no LLM involved. See [Risk model](risk-model.md).

## Policy / Compliance

The agent whose accuracy the project exists to measure. It runs in two phases:

1. **`policy`** — rules CP-1…CP-11. For each rule the code retrieves passages through the `policydocs` MCP server (hybrid search + rerank);
   then **one LLM call judges four rules at a time**, answering plain boolean questions. Code maps the answers to a status and re-checks
   every numeric comparison the model claims to have made.
2. **`policy2`** — CP-12 (is the risk grade acceptable?), then the LLM *extracts* the delegation-of-authority limits from CP-13's text
   and **code** compares the loan amount against them to choose the approver tier.

Full detail: [Credit policy and RAG](policy-rag.md).

## Memo Writer

Produces a JSON credit memo (`recommendation`, `summary`, `strengths`, `concerns`, `conditions`, `adverse_action_reasons`,
`limitations`). It is given the already-derived recommendation and must explain it. Facts supplied to it include the policy-check
table, ratios, risk factors, research summary, the applicant's prior decisions and up to two similar past cases. Its output is then checked
by the [memo validator](workflow.md#memo-validation).

## Tools

Every tool is an MCP tool served by one of three processes. See [MCP servers](mcp-servers.md) for how they are called, and the
[tool reference](../reference/mcp-tools.md) for signatures.

| Server | Tools |
|---|---|
| `fincalc` | `compute_ratios`, `amortize`, `trend`, `stress_test`, `compare`, `scorecard`, `grade`, `score_pd` |
| `policydocs` | `list_rules`, `search_policy`, `get_rule`, `similar_precedents` |
| `research` | `ofac_screen`, `adverse_media`, `registry_lookup`, `industry_default_stats` |
