# Operations

Running, stopping and maintaining the stack.

## Starting

In this order:

```bash
docker compose up -d postgres            # 1. database           (make up)
ollama serve                             # 2. only if Ollama is not already running as a service
make mlflow &                            # 3. traces + registry  (optional; http://127.0.0.1:5000)
uv run wealthpilot mcp-up &              # 4. MCP servers 8101-8103 (wait ~30 s on first start: indexing)
uv run wealthpilot ui                    # 5. the web console, http://127.0.0.1:8501 (optional)
```

Check:

```bash
uv run wealthpilot doctor                # every service and artifact, with the fix for anything missing
ss -ltn | grep -E ':(5432|5000|8101|8102|8103|8501|11434) '
uv run wealthpilot audit-verify
```

## Stopping

```bash
# Web console: Ctrl-C in its terminal, or  pkill -f "streamlit run"
# MCP servers: Ctrl-C in their terminal, or
pkill -f "wealthpilot.mcp_up"; pkill -f "mcp_servers\."

# MLflow (also stop its background job workers)
pkill -f "mlflow server"; pkill -f "huey.bin.huey_consumer"

# Postgres - STOP keeps your data (the pgdata volume)
docker compose stop postgres
```

!!! danger "`down -v` deletes data"
    `docker compose down` removes the container but keeps the `pgdata` volume. `docker compose down -v` **also deletes the volume** — all checkpoints,
    memory, cache, policy vectors and the audit log.

## Resource use

Memory was not profiled in detail. What is known: Postgres is capped at 768 MB in `docker-compose.yml`, and the whole stack — Postgres, MLflow, the three MCP
servers, Ollama with `nomic-embed-text` and one graph process — ran comfortably inside a 5.8 GB WSL2 VM. `fincalc` is probably the heaviest MCP server because it loads
LightGBM and SHAP. Running several experiment processes at once is limited by the NIM free tier long before it is limited by memory.

## Maintenance tasks

=== "Clear the response cache"

    ```sql
    TRUNCATE nim_cache;       -- forces fresh model calls (e.g. after changing a prompt)
    ```

    Prompt changes automatically produce new cache keys, so this is rarely needed.

=== "Reset the rate limiter"

    ```python
    from wealthpilot.nim import store
    store.reset_state()                       # bucket full, rate back to the configured ceiling
    store.reset_state(clear_cache=True, clear_calls=True)
    ```

=== "Re-index the policies"

    ```bash
    uv run wealthpilot ingest-policy
    ```

=== "Retrain the risk model"

    ```bash
    uv run wealthpilot train-pd
    uv run python -m wealthpilot.synth.groundtruth     # ground truth depends on the model
    ```

=== "Back up the database"

    ```bash
    docker exec wealthpilot-postgres pg_dump -U wealthpilot wealthpilot | gzip > wealthpilot-$(date +%F).sql.gz
    ```

## Health signals

| Signal | Where | Healthy | Worry when |
|---|---|---|---|
| Current rate | `SELECT rpm FROM nim_bucket;` | at or near `NIM_RPM_BUDGET` | pinned at the floor (6) — NIM is throttling the key |
| Failures | `nim_calls` where `NOT ok` | few | many `[429]`, or `empty response` |
| Cache hits | `nim_calls` where `cached` | high on re-runs | zero on a repeated case (prompt changed) |
| Audit chain | `wealthpilot audit-verify` or the console's **History** page | `ok: true` | `ok: false` |
| Waiting cases | console **Inbox** / **Cases** | few | many cases stuck *awaiting approval* |
| Failed runs | console **Cases** (status *Stopped (error)*) | none | a rising count |
| Degraded runs | `state.degraded` / memo limitations | rare | frequent — a tool server is down |

## Upgrading dependencies

Versions are pinned in `uv.lock`. LangGraph, `langchain-mcp-adapters` and MLflow change their APIs between versions; after `uv lock --upgrade`,
run the full test suite (including `-m live`) before relying on the new versions.

## Security notes

* The NIM key is read from the environment or `.env` (git-ignored). It is passed explicitly to clients and is never logged.
* Postgres, MLflow and the MCP servers bind to `127.0.0.1` only. The default Postgres password is for local development — change it before exposing anything.
* Sealed identity attributes live in the case state and checkpoints; treat the database as sensitive.
