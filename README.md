# WealthPilot

An underwriting assistant for small-business loans. It reads an applicant's financial statements, computes credit ratios, scores default risk, applies your bank's credit policy as written,
researches the borrower and drafts a credit memo, then stops for a human decision. Every decision is recorded in a tamper-evident audit log.

* **Policy-driven.** The credit policy is a Markdown document you maintain; the assistant quotes the sentence behind every rule verdict.
* **Deterministic where it matters.** Ratios, risk scores and the recommendation come from calculation tools and a fixed decision rule, not from the language model.
* **A person always decides.** Every case ends at an approval gate, checked against the policy's delegation of authority.
* **Fails safe.** A run that loses a tool or check is flagged degraded and capped at a refer recommendation.
* **Protects applicants.** Names, addresses and ZIP codes are removed from everything the language model reads.

## Run it

Requires Docker with the Compose plugin and a model API key (an NVIDIA NIM key).

```bash
export NVIDIA_API_KEY=<your key>
docker compose up -d --build
```

Open **http://127.0.0.1:8501**. The first start takes several minutes (images, embedding model, sanctions list, policy index). The console has no login; it is published on the loopback
address only. Read the security notes in the documentation before exposing it.

```bash
docker compose exec console wealthpilot doctor     # check every dependency
docker compose down                                # stop, keeping all data
```

## Repository layout

| Folder | Contents |
|---|---|
| `src/wealthpilot/`, `mcp_servers/` | The product: console, workflow, tool servers, model gateway, audit log |
| `policies/` | Credit policies, one folder each (policy text only) |
| `artifacts/` | The trained default-risk model and sector statistics |
| `config/` | Compliance profile |
| `research/` | The evaluation: synthetic-data generator, reference engine, ground truth, experiments and results. A separate package that depends on the product, never the reverse |
| `docs/` | Documentation source (MkDocs) |

## Documentation

```bash
uv sync --group docs
make docs          # live preview at http://127.0.0.1:8000
make docs-build    # strict build into ./site
```

The documentation covers deployment, the console, administration, the architecture and design decisions, reference material, and the research report.

## Development

```bash
uv sync --all-packages --group dev
make dev-services      # database from Compose; run Ollama on the host
make test              # offline tests
make test-live         # tests against the running stack and the model service
```

See the developer guide in the documentation for the repository workflow.
