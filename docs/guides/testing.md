# Running the tests

There are **71 tests**: **56 run offline** with no services, and **15 are "live"** and need the real stack.

| File | Tests | Needs |
|---|---|---|
| `tests/test_unit.py` | 21 offline + 1 live | nothing (the live one needs Postgres) |
| `tests/test_ui.py` | 35 offline | nothing — services may be up or down |
| `tests/test_gateway_live.py` | 5 live | Postgres, Ollama, a NIM key |
| `tests/test_mcp_contract.py` | 5 live | the three MCP servers running |
| `tests/test_ui_live.py` | 4 live | the whole stack (`wealthpilot doctor` shows ready) |

```bash
uv run pytest -m "not live"          # 56 offline tests, about 15 seconds
uv run pytest -m live                # 15 live tests
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

### Console tests (offline)

| Area | What is verified |
|---|---|
| **Form validation** | a valid form passes; each invalid field (blank name, one-word owner, bad NAICS, tiny loan, bad term, bad ZIP, unknown state, negative collateral/years) is explained |
| **Applicant building** | identity never appears in the LLM-facing `application`; it is kept only in `sealed`; the same applicant gets the same memory key |
| **Uploads** | both PDFs are stored under the case id; empty, non-PDF and over-long files are rejected with a reason and **nothing is written** |
| **Export** | the memo Markdown has every section and no identity; the evidence JSON drops the sealed block; degraded runs are flagged |
| **Policy parsing** | the real strict policy yields CP-1…CP-13 with the right text |
| **Case index** | status mapping for every interrupt/done combination; index rows never contain identity |
| **Health** | a closed port is reported, not raised; only the essential checks are blocking |
| **Pages** | **every page renders without an exception whether or not Postgres, Ollama and the MCP servers are up**, and the full app renders with `st.navigation` |

## What the live tests cover

* **Gateway** — chat with tools and a cache hit that returns in under half a second; embeddings (768 dimensions) and rerank ordering; recovery
  from an injected `429`; fallback to a second model when the first returns `404`; the adaptive limiter's decrease, floor and ceiling.
* **MCP contract** — the tool inventory, `fincalc` agreeing with `wealthpilot.finance`, PD scoring, the policy tools returning the right rule text
  from both policies, and each research tool (OFAC match, adverse media, registry, sector stats).
* **Console** (`test_ui_live.py`) — drives the real pages with Streamlit's `AppTest`: run a sample case, see the recommendation and the case-index row (with no identity), try to decide with
  an *under-authorised* tier (blocked by the form, nothing sent), submit a valid decision (status becomes *decided*), refuse an override without a reason, check the Cases/History/System/Policies pages with data, and run
  a **new application with uploaded PDFs** end to end.
* **Audit chain** — tampering with a record is detected at exactly that record, and restoring it re-validates the chain. *(This test appends a few
  `pytest` rows to the audit log.)*

## Static checks

```bash
uv run ruff check src experiments mcp_servers tests --select F,E9    # pyflakes + syntax errors
```

## Documentation checks

```bash
uv run mkdocs build --strict                                   # fails on broken links and anchors
MERMAID_DIR=/path/to/mmd node scripts/check_mermaid.mjs docs   # validates every Mermaid diagram (the build does not)
```

`scripts/check_mermaid.mjs` explains how to install its two Node dependencies (`mermaid`, `jsdom`); they are not project dependencies. The documentation screenshots are produced by
`scripts/capture_screenshots.py` (see [The console (implementation)](../concepts/user-interface.md#testing)).

## Writing new tests

* Test **routing and mapping** logic offline — they are pure functions over state.
* To test code that calls the LLM, monkeypatch `llm_json` and the MCP helper as the batch-judge tests do.
* Anything that needs a model should be marked `@pytest.mark.live` and be tolerant of free-tier latency.
