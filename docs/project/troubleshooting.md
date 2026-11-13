# Troubleshooting

## Quick diagnosis

```bash
ss -ltn | grep -E ':(5432|5000|8101|8102|8103|11434) '        # which services are listening?
uv run wealthpilot audit-verify                                # is Postgres reachable and the chain intact?
docker exec wealthpilot-postgres psql -U wealthpilot -d wealthpilot \
  -c "select left(error,70) err, model, count(*) from nim_calls where not ok group by 1,2 order by 3 desc limit 8"
docker exec wealthpilot-postgres psql -U wealthpilot -d wealthpilot -c "select round(rpm::numeric,1) from nim_bucket"
```

## Setup and connection problems

??? failure "`RuntimeError: NVIDIA API key not found`"
    Neither `.env` nor the shell environment has the key. Set `NVIDIA_API_KEY` **or** `NVIDIA_NIM_API_KEY`. A blank `.env` value is ignored, so it will not mask an exported key.
    See [Configuration](../getting-started/configuration.md#precedence).

??? failure "Connection refused on port 5432"
    Postgres is not running: `docker compose up -d postgres`. Check `docker ps`.

??? failure "Embedding errors, `Connection refused` on port 11434"
    Ollama is not running, or the model is missing: `ollama serve` and `ollama pull nomic-embed-text`.

??? failure "A run finishes immediately as *degraded*, with 'server was not reachable at startup'"
    The MCP servers were not running when the session started. Start them (`uv run wealthpilot mcp-up`), wait until ports 8101–8103 listen (the first start indexes the policies, ~30 s), then run again.

??? failure "`ModuleNotFoundError: mcp_servers`"
    Run the servers from the repository root (`wealthpilot mcp-up` does this itself).

??? failure "`FileNotFoundError: models/pd_model.joblib`"
    Train the model: `uv run wealthpilot train-pd` (needs the SBA CSV in `data/sba/raw/`).

??? failure "`ground_truth.json` missing, or experiments report no ground truth"
    Generate it after training: `uv run python -m wealthpilot.synth.groundtruth`.

??? failure "SBA CSV not found / wrong name"
    See [Installation](../getting-started/installation.md#5-download-the-public-data); update `SBA_CSV` in `risk/pd_model.py` if the as-of date in the file name changed.

??? warning "MLflow warnings, 'MLflow logging skipped'"
    MLflow is not running. That is **non-fatal**: tracing and experiment logging are best-effort. Start it with `make mlflow &` if you want traces.

## Console problems

??? failure "Every console page says "Postgres is not reachable""
    Start the database (`docker compose up -d postgres`) and press **R** in the browser. Run `uv run wealthpilot doctor` to see every component at once.

??? failure "The console starts but **Run underwriting** shows a red message about Ollama, the key or the risk model"
    The pre-flight check blocks a run that cannot work at all and shows the fix for each missing piece (`ollama pull nomic-embed-text`, export the key, `uv run wealthpilot train-pd`).

??? warning "An orange warning says the run will be degraded"
    One or more MCP servers are not reachable. The run is allowed but will recommend *refer*. Start them with `uv run wealthpilot mcp-up` and run the case again.

??? question "A case I started is missing from **Cases**"
    The default filter shows only cases *waiting for a human*. Widen the **Status** filter. Cases appear as soon as a run starts (status ⏳ Running).

??? failure "A case shows 🛑 Error in **Cases**"
    Select it: the message says what failed (usually a missing service). Fix that and run the case again from **Underwrite**.

??? failure "Upload rejected"
    The message names the reason: not a readable PDF, empty, over 25 MB, or over 40 pages. For a scanned PDF larger than 25 MB, reduce the resolution.

??? question "The uploader says 200 MB but the form rejects files over 25 MB"
    Start the console with `wealthpilot ui` (or from the project folder, so `.streamlit/config.toml` is read). Both set the 25 MB limit.

??? question "The page looks stuck after a click"
    Runs block the page while they work (the progress box shows each step). On the free model tier a first run can take several minutes. Closing the tab does not stop the run; reopen the case from **Cases** when it pauses.

## Model and rate-limit problems

??? failure "Calls are very slow; `[429] Too Many Requests` in `nim_calls`"
    The free NIM tier throttles **per model**. The adaptive limiter backs off automatically; check `SELECT rpm FROM nim_bucket` — a value near 6 means NIM is throttling the key.
    Wait, lower `NIM_RPM_BUDGET`, avoid running several heavy jobs at once, and rely on the cache for repeats.

??? failure "`[404] Not Found` / `[410] Gone` for a model"
    The model is not available to your account (the public catalog lists retired models). See [Probing which NIM models work](#probing-which-nim-models-work) and set `CHAT_MODEL`.

??? failure "`[502] empty response from model`"
    The model returned no content and no tool calls. The gateway retries and never caches such replies. If it persists for one model, switch models.

??? failure "Garbled output, `LLM did not return valid JSON`"
    A model degraded on long structured outputs (seen with the 550B model). Switch `CHAT_MODEL`; keep `CHAT_FALLBACK_MODEL` empty unless you have verified the fallback.

??? failure "Everything times out"
    The per-request timeout is `NIM_TIMEOUT_S` (45 s). Long extractions on a throttled model can exceed it; increase it, or retry later.

### Probing which NIM models work

```python
import time, httpx
from wealthpilot.config import get_settings
key = get_settings().nvidia_api_key.get_secret_value()

def probe(model: str) -> str:
    t0 = time.time()
    r = httpx.post("https://integrate.api.nvidia.com/v1/chat/completions",
                   headers={"Authorization": f"Bearer {key}"}, timeout=90,
                   json={"model": model, "messages": [{"role": "user", "content": "Say ok"}], "max_tokens": 8,
                         "chat_template_kwargs": {"enable_thinking": False}})
    return f"{r.status_code} {time.time()-t0:.1f}s"

print(probe("nvidia/nemotron-3.5-lightning-30b-a3b"))
```

A `200` is necessary but **not sufficient**: also test a tool call and a *long* structured output, which is where a degraded model shows up.

## Behaviour that surprises people

??? question "Re-running a case with the same thread id does nothing new"
    A finished thread's saved state is re-entered. Use a fresh `--thread` each time.

??? question "The graph paused at *document review* — is that a bug?"
    No. Reconciliation found inconsistent figures even after the repair attempt, so a person must `accept`, `correct` or `reject` the documents. It happens on some scanned documents and when model replies are corrupted.

??? question "The recommendation is *refer* although everything passed"
    The run was **degraded** (a tool or check was unavailable) or a rule was `missing_data`/`exception`. Look at `degraded_reasons` and the policy checklist.

??? question "A case I expected to be approved was declined"
    Read the checklist: the decision rule declines if **any** rule `fail`s. Compare `evidence` quotes with the policy text. If a status looks wrong, that is a model reading error — see [E0](../experiments/e0-policy-adherence.md#what-went-wrong-12-of-288-judgements).

??? question "The first run of a case takes minutes, the second seconds"
    The second run is served from the response cache. Changing a prompt or model changes the cache key and forces fresh calls.

??? question "`audit-verify` reports `ok: false`"
    A past `audit_log` row was edited or deleted. The reported `first_bad_id` is the first inconsistent record. The test suite temporarily modifies and restores a row; it should leave the chain valid.

## Resetting

| Symptom | Fix |
|---|---|
| Stale or poisoned cache | `TRUNCATE nim_cache;` |
| Limiter stuck low | `from wealthpilot.nim import store; store.reset_state()` |
| Policy index out of date | `uv run wealthpilot ingest-policy` |
| Port already in use | find it with `ss -ltnp`; stop the old process |
| Start from scratch | `docker compose down -v` (**deletes all data**), then reinstall from [Installation](../getting-started/installation.md#3-start-postgres) |
