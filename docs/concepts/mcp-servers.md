# MCP servers

Credit math, policy search and borrower research are exposed as **Model Context Protocol** tools, served by three small FastMCP applications
over streamable HTTP. The graph consumes them with `langchain-mcp-adapters`.

| Server | Port | Module | Purpose |
|---|---|---|---|
| `fincalc` | 8101 | `mcp_servers.fincalc.server` | deterministic credit math and PD scoring |
| `policydocs` | 8102 | `mcp_servers.policydocs.server` | policy search, rules and similar-case memory |
| `research` | 8103 | `mcp_servers.research.server` | sanctions, adverse media, registry and sector statistics |

Start all three with:

```bash
uv run wealthpilot mcp-up        # one process per server; Ctrl-C stops them all
```

Each server is a separate OS process, so they can fail, restart and be scaled independently of the graph — which is exactly what the
[reliability experiment](../experiments/e4-reliability.md) exploits.

## Why MCP for these tools?

* **Deterministic boundary.** The LLM never does the arithmetic; it calls `fincalc`. The same pure functions (`wealthpilot.finance`) power the tools,
  the reference engine and the unit tests, so they cannot drift apart.
* **Isolation.** Heavy dependencies (the LightGBM model and SHAP in `fincalc`, pgvector and BM25 in `policydocs`) stay out of the graph process.
* **Replaceable.** Any MCP-compatible client can use the servers; the graph depends only on tool names and JSON schemas.

## Tools

The complete signatures are in the [MCP tool reference](../reference/mcp-tools.md). Summary:

=== "fincalc"

    `compute_ratios` · `amortize` · `trend` · `stress_test` · `compare` · `scorecard` · `grade` · `score_pd`

=== "policydocs"

    `list_rules` · `search_policy` · `get_rule` · `similar_precedents`

=== "research"

    `ofac_screen` · `adverse_media` · `registry_lookup` · `industry_default_stats`

!!! info "Mock sources"
    `adverse_media` and `registry_lookup` read the synthetic world (`data/synthetic/`); they stand in for real news and registry providers and are
    labelled as mock in their tool descriptions. `ofac_screen` uses the real, public OFAC SDN list plus a small synthetic watchlist used to plant test hits.

## How the graph calls them

```python
from wealthpilot.graph.runtime import rt

ratios = await rt.call("compute_ratios", statements=latest, loan_amount=100_000, term_months=84)
```

`Runtime.connect()` loads tools **server by server**; a server that is down at start-up is recorded in `rt.unavailable` instead of blocking the others.
Results arrive as MCP content blocks; `parse_result` turns them back into Python objects.

!!! note "Tools return objects, never bare lists"
    FastMCP turns a returned list into *one content block per item*, which made single-item lists ambiguous. Tools that return collections therefore
    wrap them: `list_rules` returns `{"rules": [...]}`, `similar_precedents` returns `{"precedents": [...]}`.

### Two ways tools are used

| Use | Where |
|---|---|
| **Direct, deterministic calls from code** | ratios, trend, stress, PD, scorecard, grade, sanctions, registry, rule search — the authoritative results |
| **Agent tools** | the Analyst agent (`compute_ratios`, `stress_test`, `trend`) may call extra what-if tools; these never overwrite the authoritative values |

## Failure handling

`Runtime.call` retries three times with short backoff, behind an **async circuit breaker per server** (3 failures → open for 20 s). On failure it raises
`ToolUnavailable(server, tool, reason)`. Each node catches it and:

* sets `degraded = True` and appends a reason (so the final recommendation is capped at *refer* — see [the decision rule](decision-rule.md#the-degraded-run-cap)),
* leaves the affected output empty (e.g. `ratios = None`, `sanctions_status = "not_performed"`) so downstream rules become `missing_data`,
* never crashes the run.

## Contract tests

`tests/test_mcp_contract.py` starts nothing itself: with the servers running, it loads every tool through the real `MultiServerMCPClient` and checks
the tool inventory, that `fincalc` agrees with `wealthpilot.finance`, PD scoring, policy search returning the right rule text, and each research tool.
