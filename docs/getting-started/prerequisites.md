# Prerequisites

## Software

| Requirement | Version | Used for |
|---|---|---|
| Linux (or WSL2 on Windows) | any recent | the project was developed on WSL2 |
| [Python](https://www.python.org/) | 3.12 | runtime |
| [uv](https://docs.astral.sh/uv/) | recent | dependency and virtual-environment management |
| [Docker](https://docs.docker.com/get-docker/) with Compose v2 | recent | Postgres 16 with the pgvector extension |
| [Ollama](https://ollama.com/) | recent | local embedding model (`nomic-embed-text`) |

## Accounts and keys

**An NVIDIA NIM API key** — create one for free at [build.nvidia.com](https://build.nvidia.com/). It is used for chat,
vision and reranking calls.

!!! info "The key may be named either way"
    WealthPilot reads `NVIDIA_API_KEY` **or** `NVIDIA_NIM_API_KEY`, from `.env` or from your shell environment. See
    [Configuration](configuration.md#precedence) for the exact precedence rules.

## Hardware

| Resource | Minimum | Notes |
|---|---|---|
| RAM | ~6 GB | Developed on a 5.8 GB WSL2 VM. Postgres is capped at 768 MB in `docker-compose.yml`; MLflow, the three MCP servers and Ollama run alongside it. This is why MLflow replaced Langfuse (see [Design decisions](../project/decisions.md)). |
| Disk | ~2 GB | the SBA CSV is ~255 MB; the rendered synthetic PDFs are ~260 MB; models and the database add the rest |
| GPU | not needed | embeddings run on CPU; all large models are hosted |

## Network

Outbound HTTPS to:

- `integrate.api.nvidia.com` — NIM chat, vision and rerank endpoints
- `data.sba.gov` — the public SBA 7(a) loan dataset (one-time download)
- `sanctionslistservice.ofac.treas.gov` — the public OFAC sanctions list (one-time download)

## Free-tier expectations

!!! warning "Throughput is limited by the free NIM tier"
    During development the effective throughput was roughly **5–15 chat calls per minute**, limits applied **per model**, and
    several models listed in NVIDIA's public catalog were retired or unreliable. A single underwriting run therefore takes
    **1–7 minutes**, and the full experiment suite takes hours. The gateway's cache means a repeated run of the same case
    completes in seconds. See [NIM gateway](../concepts/nim-gateway.md) and [Troubleshooting](../project/troubleshooting.md).
