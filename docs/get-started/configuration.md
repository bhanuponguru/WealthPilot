# Configuration

WealthPilot is configured with environment variables. In the Docker deployment, set them in the shell that runs Compose or in a `.env` file next to `docker-compose.yml`; Compose passes the
relevant ones to each container. For a local (non-Docker) installation, the same names can also be set in a `.env` file in the project folder.

## Precedence (local installation)

When the application reads its own settings, the highest-priority source wins:

1. explicit arguments (used by tests),
2. the project's `.env` file,
3. the process environment,
4. the built-in default.

A blank value counts as unset, so an empty `NVIDIA_API_KEY=` copied from the example file does not mask a key exported in the shell. The model API key has no default; if none is found, the application
reports which variables it looked for.

## Model service

| Variable | Default | Description |
|---|---|---|
| `NVIDIA_API_KEY` or `NVIDIA_NIM_API_KEY` | none (required) | API key for the hosted model service. Either name works. |
| `CHAT_MODEL` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Chat and tool-calling model. |
| `CHAT_FALLBACK_MODEL` | empty (disabled) | Optional second chat model used after the primary fails. |
| `VLM_MODEL` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | Vision model that reads scanned pages. |
| `RERANK_MODEL` | `nvidia/llama-nemotron-rerank-vl-1b-v2` | Reranker for policy search. |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model served by the local embeddings service (768 dimensions). |

!!! warning "Check model availability"
    The service's public catalog lists models that a given account cannot call (they return 404 or 410), and availability changes over time. A model that answers a trivial prompt can still fail on tool calls or
    long structured output. After changing a model, run a real case. See [Troubleshooting](../administration/troubleshooting.md).

## Gateway behaviour

| Variable | Default | Description |
|---|---|---|
| `NIM_RPM_BUDGET` | `15` | Ceiling of the shared requests-per-minute limit. The effective rate falls automatically when the service throttles and recovers afterwards. |
| `NIM_CACHE_ENABLED` | `true` | Response cache for model calls. Disable to force every call to reach the service. |
| `NIM_TIMEOUT_S` | `45` | Per-request read timeout in seconds. |
| `NIM_THINKING` | `false` | Whether reasoning models use extended thinking. Off gives much lower latency. |
| `WP_CHAOS` | unset | JSON fault-injection profile for resilience testing, for example `{"p_429": 0.3, "p_timeout": 0.1}`. Do not set it in production. |

See [Model gateway and reliability](../architecture/model-gateway.md) for what each setting controls.

## Infrastructure

| Variable | Default (Docker) | Description |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `wealthpilot` | Database credentials. Change the password before first start. |
| `POSTGRES_PORT` | `5432` | Host port for the database (published on `127.0.0.1` only). |
| `CONSOLE_PORT` | `8501` | Host port for the console (published on `127.0.0.1` only). |
| `DATABASE_URL` | built from the values above | Connection string used by every service. |
| `OLLAMA_URL` | `http://ollama:11434` | Embeddings service. |
| `MLFLOW_TRACKING_URI` | `http://mlflow:5000` | Tracking server. Tracing is skipped, without failing runs, if it is unreachable. |
| `MCP_HOST` | `mcp` | Host name of the tool servers, as seen by the console and the workflow. |
| `MCP_BIND` | `0.0.0.0` in the tool-server container | Address the tool servers listen on. |

## Locations and modes

| Variable | Default (Docker) | Description |
|---|---|---|
| `WEALTHPILOT_DATA_DIR` | `/data` | Runtime data: uploaded documents, the sanctions list and optional demonstration data. |
| `WEALTHPILOT_POLICIES_DIR` | `/app/policies` | Credit policies, one folder each. Bind-mount your own to edit policies without rebuilding. |
| `WEALTHPILOT_ARTIFACTS_DIR` | `/app/artifacts` | The trained default-risk model and sector statistics. |
| `WEALTHPILOT_CONFIG_DIR` | `/app/config` | Compliance profile. |
| `WEALTHPILOT_DEMO_DIR` | `<data>/demo` | Demonstration data location. |
| `WEALTHPILOT_DEMO` | `0` | Set to `1` to offer sample applicants on the New case page. Requires demonstration data; see [Deploy with Docker](deploy.md#demonstration-mode). |

## Ports

| Port | Service | Published |
|---|---|---|
| 8501 | Console | `127.0.0.1` |
| 5432 | Database | `127.0.0.1` |
| 8101, 8102, 8103 | Tool servers: fincalc, policydocs, research | internal |
| 5000 | Tracking server | internal |
| 11434 | Embeddings service | internal |

## Example `.env`

```dotenv
NVIDIA_API_KEY=
POSTGRES_PASSWORD=change-me
CONSOLE_PORT=8501
NIM_RPM_BUDGET=15
# WEALTHPILOT_DEMO=1
```
