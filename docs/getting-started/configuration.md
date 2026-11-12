# Configuration

All settings live in one class, [`wealthpilot.config.Settings`](../reference/api.md), built on `pydantic-settings`. Every field can be
set with an environment variable of the same name (case-insensitive).

## Precedence

For every setting, the highest-priority source wins:

1. explicit arguments (used by tests)
2. the project's **`.env`** file
3. the **process / global environment**
4. the field default

!!! note "`.env` wins over the shell — deliberately"
    `pydantic-settings` normally lets the environment override `.env`. WealthPilot reverses that so a project-local `.env`
    reliably overrides whatever happens to be exported in your shell. A **blank** value (e.g. `NVIDIA_API_KEY=` copied from
    `.env.example`) counts as *unset* and falls through to the environment instead of masking it.

The NIM key has **no default**. If it is set in neither place, `get_settings()` raises a `RuntimeError` that names the variable and
the `.env` path. It may be named `NVIDIA_API_KEY` or `NVIDIA_NIM_API_KEY`.

## Settings reference

### Connections

| Variable | Default | Description |
|---|---|---|
| `NVIDIA_API_KEY` / `NVIDIA_NIM_API_KEY` | *(required)* | NIM developer key. Passed explicitly to every client (the LangChain package only auto-reads `NVIDIA_API_KEY`). |
| `DATABASE_URL` | `postgresql://wealthpilot:wealthpilot@127.0.0.1:5432/wealthpilot` | Postgres (checkpoints, memory, vectors, cache, audit log). |
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:5000` | MLflow server for traces, experiments and the model registry. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Local embedding server. |

### Models

| Variable | Default | Role |
|---|---|---|
| `CHAT_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Chat and tool calling (primary). |
| `CHAT_FALLBACK_MODEL` | *(empty — disabled)* | Optional second chat model used after the primary fails. |
| `VLM_MODEL` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | Vision model that reads scanned pages. |
| `RERANK_MODEL` | `nvidia/llama-nemotron-rerank-vl-1b-v2` | Passage reranker for policy RAG. |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model served by Ollama (768 dimensions). |

!!! warning "Model availability changes"
    NVIDIA's public catalog lists models that return `410 Gone` or `404` for a given account, and availability changed during
    development (the 550B model went from `503`s to empty replies to garbled text). **Verify a model before relying on it** — see
    [Troubleshooting](../project/troubleshooting.md#probing-which-nim-models-work). The fallback is empty by default for that reason.

### Gateway behaviour

| Variable | Default | Description |
|---|---|---|
| `NIM_RPM_BUDGET` | `15` | **Ceiling** of the shared, adaptive requests-per-minute limiter (it falls on `429`s and recovers). See [NIM gateway](../concepts/nim-gateway.md#adaptive-rate-limit). |
| `NIM_CACHE_ENABLED` | `true` | Response cache. Disable for experiments that must hit the network (E4 does). |
| `NIM_TIMEOUT_S` | `45` | Per-request read timeout in seconds (the library default of 60 delays failover). |
| `NIM_THINKING` | `false` | Whether reasoning models "think" before answering. Off gives ~3× lower latency and near-zero reasoning tokens; extended thinking made one extraction impractically slow (it was still running after four minutes). |

### Fault injection

Fault injection is configured with the `WP_CHAOS` environment variable (JSON) or programmatically — see
[NIM gateway](../concepts/nim-gateway.md#fault-injection).

## `.env.example`

```dotenv
# Copy to .env only if you want to override your shell environment.
# Precedence: .env (non-blank) > global environment > error.
NVIDIA_API_KEY=

POSTGRES_USER=wealthpilot
POSTGRES_PASSWORD=wealthpilot
DATABASE_URL=postgresql://wealthpilot:wealthpilot@127.0.0.1:5432/wealthpilot

MLFLOW_TRACKING_URI=http://127.0.0.1:5000

# Ceiling for the shared adaptive limiter (the free tier returned real 429s at 25-35)
NIM_RPM_BUDGET=15
```

## Ports used

| Port | Service |
|---|---|
| 5432 | Postgres |
| 5000 | MLflow |
| 8101 / 8102 / 8103 | MCP servers `fincalc` / `policydocs` / `research` |
| 11434 | Ollama |
| 8501 | Streamlit console (when running) |
