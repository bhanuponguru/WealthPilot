# Tool servers

Credit math, policy search and borrower research are exposed as Model Context Protocol (MCP) tools, served by three small
applications over streamable HTTP. The workflow consumes them through an MCP client.

| Server | Port | Purpose |
|---|---|---|
| `fincalc` | 8101 | Deterministic credit math and default-probability scoring |
| `policydocs` | 8102 | Policy search, rule lookup and similar-case memory |
| `research` | 8103 | Sanctions screening, adverse media, business registry and sector statistics |

In the Docker deployment the three servers run as separate processes inside the `mcp` service. Their ports are reachable from the
other services but are not published on the host. Outside Docker, `wealthpilot mcp-up` starts them. Each server is its own operating
system process, so they can fail and restart independently of the workflow.

## Why tool servers

* **Deterministic boundary.** The language model never does the arithmetic. It calls `fincalc`. The same pure functions power the
  tools and the workflow's own checks, so they cannot drift apart.
* **Isolation.** Heavy dependencies, such as the gradient-boosted model and SHAP in `fincalc` or the vector index in `policydocs`,
  stay out of the console process.
* **Replaceable.** Any MCP-compatible client can use the servers. The workflow depends only on tool names and JSON schemas.

## Tools

The complete signatures are in the [Tool reference](../reference/tool-reference.md). Summary:

=== "fincalc"

    `compute_ratios` · `amortize` · `trend` · `stress_test` · `compare` · `scorecard` · `grade` · `score_pd`

=== "policydocs"

    `list_rules` · `search_policy` · `get_rule` · `similar_precedents`

=== "research"

    `ofac_screen` · `adverse_media` · `registry_lookup` · `industry_default_stats`

## Data sources

| Tool | Source |
|---|---|
| `ofac_screen` | The public OFAC sanctions list, downloaded by the `bootstrap` service into the `data` volume, plus an optional additional watchlist file in the demonstration data. Matching is fuzzy, with a minimum score of 92. |
| `industry_default_stats` | A statistics file shipped in `artifacts/`, computed from the SBA 7(a) data. |
| `adverse_media` | An integration point for an external news provider. The bundled implementation is a mock that reads the optional demonstration data. |
| `registry_lookup` | An integration point for a business registry. The bundled implementation is a mock that reads the optional demonstration data. |
| `search_policy`, `get_rule`, `list_rules` | The credit policies in `policies/`, indexed in Postgres. |
| `similar_precedents` | The precedents index in Postgres. |

!!! warning "Behavior without data"
    Without demonstration data, the adverse-media and registry tools report no results. Without the sanctions list, screening finds
    no matches and the case is treated as having no sanctions match. The System page of the console flags a missing sanctions list as an
    optional check that has failed. Replace the mock providers before using the system on real cases, and make sure `bootstrap`
    completed. See [Known limitations](../administration/limitations.md).

## How the workflow calls the tools

The workflow loads the tools server by server at the start of a run. A server that is down at that moment is recorded as unavailable
instead of blocking the others. Results arrive as MCP content blocks that the workflow converts back into structured values.

!!! note "Tools return objects, never bare lists"
    An MCP server that returns a list sends one content block per item, which makes single-item lists ambiguous. Tools that return
    collections therefore wrap them in an object, for example a list of rules under a rules key.

### Two ways tools are used

| Use | Where |
|---|---|
| Direct, deterministic calls from code | Ratios, trend, stress test, default probability, scorecard, grade, sanctions screening, registry lookup and rule search. These are the authoritative results. |
| Agent tools | The financial analyst's language model may call extra what-if tools. These calls never overwrite the authoritative values. |

## Failure handling

Each tool call is attempted up to three times with a short backoff, behind an asynchronous circuit breaker per server. The breaker
opens after three failures and stays open for 20 s. If the call still fails, the workflow step catches the failure and:

* marks the run as degraded and records the reason, so the final recommendation is capped at refer. See
  [The degraded-run cap](decision-rule.md#the-degraded-run-cap),
* leaves the affected output empty, for example no ratios or a sanctions status of "not performed", so downstream rules become
  missing data,
* never crashes the run.

The [reliability evaluation](../research/e4-reliability.md) measures this behavior under injected outages.

## Contract tests

The contract tests load every tool through a real MCP client against running servers and check the tool inventory, agreement between
`fincalc` and the shared credit-math functions, default-probability scoring, policy search returning the right rule text, and each
research tool. They are marked as live tests. See the [Developer guide](development.md#tests).
