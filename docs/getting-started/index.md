# Getting started

This section takes you from a fresh checkout to an underwritten case.

| Step | Page | Time |
|---|---|---|
| 1 | [Prerequisites](prerequisites.md) — what you need installed and which accounts/keys | 5 min |
| 2 | [Installation](installation.md) — dependencies, services, data, the synthetic world | 20–30 min (mostly downloads and one training run) |
| 3 | [Quickstart](quickstart.md) — run a case, approve it, inspect the trace and the audit log | 10 min |
| 4 | [Configuration](configuration.md) — settings, precedence rules and model choices | reference |

!!! tip "Everything runs locally except the LLM calls"
    Postgres, MLflow, the three MCP servers and the embedding model all run on your machine. Only chat, vision and reranking
    calls go to NVIDIA's hosted NIM endpoints, using a free developer key.
