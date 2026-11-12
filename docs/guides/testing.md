# Running the tests

There are **32 tests**: **21 run offline** with no services, and **11 are "live"** and need the real stack.

| File | Tests | Needs |
|---|---|---|
| `tests/test_unit.py` | 21 offline + 1 live | nothing (the live one needs Postgres) |
| `tests/test_gateway_live.py` | 5 live | Postgres, Ollama, a NIM key |
| `tests/test_mcp_contract.py` | 5 live | the three MCP servers running |

```bash
uv run pytest -m "not live"          # 21 offline tests, a few seconds
uv run pytest -m live                # 11 live tests
uv run pytest                        # everything
```

The `live` marker is declared in `pyproject.toml`.

## What the offline tests cover

| Area | What is verified |
|---|---|
| **Credit math** | amortisation against a known value; the DSCR definition; ratios; `compare` including missing data; scorecard and the grade matrix |
| **Decision rule** | `fail → decline`, `exception/missing_data → refer`, `not_applicable` ignored; **degraded runs never auto-decide** (approve *and* decline → refer) |
| **Reference engine** | the lenient exception band for DSCR with collateral; the strict policy has none; policies disagree on enough cases |
| **Reconciliation** | a consistent set of statements passes; a broken balance sheet is flagged; bank roll-forward |
| **Redaction & compliance** | name, ZIP and business-name redaction; keeps city; **whole-word matching** ("market" is not touched for an owner named Mark); the prohibited-language scan |
| **Memo validator helpers** | unsupported numbers are detected while rule ids, years and small integers are exempt |
| **Routing** | every `route_after_*` predicate, including loop limits |
| **Status mapping** | the boolean answers → `pass / fail / exception / not_applicable / missing_data` |
| **Numeric verification** | wrong comparisons are caught (the exact `132000 > 150000` mistake); malformed entries are ignored |
| **Batch judge** (LLM and MCP mocked) | one LLM call for a correct batch; a targeted **re-ask** after a wrong comparison; `missing_data` if the re-ask is still wrong |
| **Configuration** | precedence `.env` > environment > error, blank values ignored, either key name |

## What the live tests cover

* **Gateway** — chat with tools and a cache hit that returns in under half a second; embeddings (768 dimensions) and rerank ordering; recovery
  from an injected `429`; fallback to a second model when the first returns `404`; the adaptive limiter's decrease, floor and ceiling.
* **MCP contract** — the tool inventory, `fincalc` agreeing with `wealthpilot.finance`, PD scoring, the policy tools returning the right rule text
  from both policies, and each research tool (OFAC match, adverse media, registry, sector stats).
* **Audit chain** — tampering with a record is detected at exactly that record, and restoring it re-validates the chain. *(This test appends a few
  `pytest` rows to the audit log.)*

## Static checks

```bash
uv run ruff check src experiments mcp_servers tests --select F,E9    # pyflakes + syntax errors
```

## Writing new tests

* Test **routing and mapping** logic offline — they are pure functions over state.
* To test code that calls the LLM, monkeypatch `llm_json` and the MCP helper as the batch-judge tests do.
* Anything that needs a model should be marked `@pytest.mark.live` and be tolerant of free-tier latency.
