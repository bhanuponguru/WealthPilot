# WealthPilot

An underwriting assistant for small-business loans. It reads an applicant's financial statements, computes credit ratios, scores default risk, applies your bank's credit policy as written,
researches the borrower and drafts a credit memo, then stops for a human decision. Every decision is recorded in a tamper-evident audit log.

* **Policy-driven.** The credit policy is a Markdown document you maintain; the assistant quotes the sentence behind every rule verdict.
* **Deterministic where it matters.** Ratios, risk scores and the recommendation come from calculation tools and a fixed decision rule, not from the language model.
* **A person always decides.** Every case ends at an approval gate, checked against the policy's delegation of authority.
* **Fails safe.** A run that loses a tool or check is flagged degraded and capped at a refer recommendation.
* **Protects applicants.** Names, addresses and ZIP codes are removed from everything the language model reads.

## Status

A complete decision-support prototype, evaluated on synthetic applicants and public loan outcomes. It is **not** validated on real documents, has no
authentication, and its research sources other than the sanctions list are mocks. See [limitations](docs/administration/limitations.md) and the
[open issues](https://github.com/bhanuponguru/WealthPilot/issues).

| Document | Location |
|---|---|
| Project report | [`docs/Project_Report.pdf`](docs/Project_Report.pdf) (source: [`docs/Project_Report.md`](docs/Project_Report.md)) |
| Architecture decision records | [`docs/Architecture_Decision_Records.md`](docs/Architecture_Decision_Records.md) |
| Extended writeup | [`writeup/WealthPilot-writeup.pdf`](writeup/WealthPilot-writeup.pdf) |
| Documentation source | [`docs/`](docs/index.md) (MkDocs) |
| Final revision | tag `cs5903-final-2026` |

## Architecture

One Docker image runs every WealthPilot service. The **console** hosts the web interface and the underwriting workflow (a deterministic LangGraph graph with two human pause points).
It calls three **tool servers** over the Model Context Protocol (`fincalc`: ratios, scorecard, default-risk score; `policydocs`: policy search; `research`: sanctions screening and borrower research).
All model traffic passes through a **gateway** library (shared cache, adaptive rate limit, retry, fallback, fault injection) that calls a hosted NVIDIA NIM API for chat, vision and reranking
and a local **Ollama** service for embeddings. **Postgres with pgvector** holds workflow state, memory, policy vectors, the cache and the audit log; **MLflow** records one trace per case.
A diagram and the design rationale are in the [project report](docs/Project_Report.pdf) and [system design](docs/architecture/system-design.md).

## Prerequisites

| Requirement | Version or detail |
|---|---|
| Docker Engine with the Compose plugin | 24 or later (developed on 29.10.0) |
| Memory and disk | about 4 GB of memory available to Docker (the stack uses about 1.2 GB); about 6 GB of disk |
| Internet access | At first start (images, embedding model, sanctions list) and at run time (hosted model API) |
| A model API key | An NVIDIA NIM key from build.nvidia.com. The free tier works but is slow and rate limited |
| For development only | Python 3.12 and [uv](https://docs.astral.sh/uv/); dependencies are pinned in `uv.lock` (for example langgraph 1.2.20, mlflow 3.18.0, streamlit 1.67.0) |

## Run it

```bash
git clone https://github.com/bhanuponguru/WealthPilot.git && cd WealthPilot
git checkout cs5903-final-2026
export NVIDIA_API_KEY=<your key>          # or copy .env.example to .env and fill it in
docker compose up -d --build
```

Open **http://127.0.0.1:8501**. The first start takes several minutes (images, embedding model, sanctions list, policy index). The console has no login; it is published on the loopback
address only. Read [Security and access](docs/administration/security.md) before exposing it.

```bash
docker compose exec console wealthpilot doctor     # check every dependency; prints the fix for anything missing
docker compose logs -f                             # follow the logs of all services
docker compose down                                # stop, keeping all data
docker compose down -v                             # stop and DELETE all data (database, embeddings, uploads, traces)
```

**Database setup and seed data.** There is no manual migration step. The first start creates the schema, the one-shot `bootstrap` service downloads the OFAC sanctions list, and the credit policies in
`policies/` are indexed. The trained risk model (`artifacts/`) ships with the repository. To rebuild an index after editing a policy, run `docker compose exec console wealthpilot ingest-policy`
and then `docker compose restart mcp console`. Optional sample applicants for the demonstration tab need generated data: `make demo-data`, then `WEALTHPILOT_DEMO=1 docker compose up -d`.

### Environment variables

Set them in the shell or in a `.env` file (see [`.env.example`](.env.example), which lists every variable with a safe default and contains no secrets).

| Variable | Purpose | Default |
|---|---|---|
| `NVIDIA_API_KEY` (or `NVIDIA_NIM_API_KEY`) | Hosted model API key (required) | none |
| `CHAT_MODEL`, `VLM_MODEL`, `RERANK_MODEL`, `EMBED_MODEL` | Models | see `.env.example` |
| `NIM_RPM_BUDGET`, `NIM_TIMEOUT_S`, `NIM_THINKING`, `NIM_CACHE_ENABLED` | Gateway behaviour | `15`, `45`, `false`, `true` |
| `POSTGRES_PASSWORD` | Database password; change before first start | `wealthpilot` |
| `CONSOLE_PORT` | Host port of the console | `8501` |
| `WEALTHPILOT_DEMO` | `1` adds the sample-applicant tab | `0` |

The full list is in [Configuration](docs/get-started/configuration.md).

## Try it: example input and expected output

[`examples/`](examples/README.md) holds two synthetic applicants with their PDFs and the values to enter. Submit `examples/C004` under the **strict** policy in **New case**.
The expected reference outcome is **decline**, risk grade **B**, approval tier **Senior Credit Officer**; under the **lenient** policy the same applicant is **approve** at tier **Analyst**. A run takes
five to ten minutes on the free model tier. The case then waits in the **Inbox** for a decision, and **History** shows the recorded decision with the audit chain verified. Model runs are not
bit-for-bit repeatable, so compare the recommendation, grade and tier. `examples/C007` was used in no experiment and serves as an unseen case. More detail:
[Your first case](docs/get-started/first-case.md).

## Tests

```bash
uv sync --all-packages --group dev          # install development dependencies
make dev-services                           # database from Compose; run Ollama on the host (live tests only)
uv run pytest -q -m "not live"              # offline suite: expect "61 passed" (log: tests/logs/offline_tests.txt)
uv run pytest -q -m live                    # needs the running stack and the model API (contract, gateway, console end to end)
# or, against the deployed containers (stack up; sample data generated):
make demo-data && docker compose up -d --force-recreate mcp console && make test-live-docker   # log: tests/logs/live_tests.txt
```

| Test file | Covers |
|---|---|
| `tests/test_unit.py` | Credit math, decision rule, degraded cap, reconciliation, redaction, audit chain, numeric verification, batched judging |
| `tests/test_boundary.py` | The product never imports the research package; policy folders hold only policy text; the console exposes only its six product pages |
| `tests/test_ui.py` | Console pages, forms, decision form, identity masking |
| `tests/test_mcp_contract.py`, `tests/test_gateway_live.py`, `tests/test_ui_live.py` | Live: tool servers, gateway retry and fallback, an end-to-end case with a human decision, runs surviving navigation |

## Evaluation

The evaluation lives in a separate package, [`research/`](research/REPORT.md): the synthetic-data generator (seed 7), the reference engine that holds the ground truth, the experiment scripts
and the raw results in [`research/results/`](research/results/). It depends on the product and never the reverse. Experiments need the running stack and a model key; the exact commands, inputs,
seeds and expected variation are in [Reproducing the experiments](docs/research/reproduce.md). Results with interpretation: [research overview](docs/research/index.md).

| Experiment | Script | Result file |
|---|---|---|
| E0 policy adherence | `research/experiments/e0_policy.py 12` | `research/results/e0_policy.md` |
| E1 document parsing | `research/experiments/e1_parsing.py 12` | `research/results/e1_parsing.md` |
| E2 policy retrieval | `research/experiments/e2_rag.py` | `research/results/e2_rag.md` |
| E3 fairness and compliance | `e3_fairness.py`, `e3_counterfactual.py 3` | `e3_fairness_ab.md`, `e3_counterfactual.md` |
| E4 reliability | `e4_reliability.py 4`, `e4_outcomes.py` | `e4_reliability.md` |

## Operating it

Start, stop and reset are above. Logs: `docker compose logs <service>` (services: `console`, `mcp`, `postgres`, `ollama`, `mlflow`, `bootstrap`). Health: `wealthpilot doctor` or the System page.
Backups, housekeeping and the troubleshooting table for common failures are in [Operations](docs/administration/operations.md) and
[Troubleshooting](docs/administration/troubleshooting.md). External dependencies: a model API account (free-tier rate limits and model availability change without notice), and internet access for the
sanctions list. The backup and restore commands have not been exercised end to end ([issue 4](https://github.com/bhanuponguru/WealthPilot/issues/4)).

## Repository layout

| Folder | Contents |
|---|---|
| `src/wealthpilot/`, `mcp_servers/` | The product: console, workflow, tool servers, model gateway, audit log |
| `policies/` | Credit policies, one folder each (policy text only) |
| `artifacts/` | The trained default-risk model and sector statistics |
| `config/` | Compliance profile |
| `examples/` | Two synthetic applicants with documents and expected outcomes |
| `research/` | The evaluation: data generator, reference engine, ground truth, experiments and results |
| `tests/` | Offline and live tests; logs in `tests/logs/` |
| `docs/` | Documentation source, the project report and the decision records |
| `writeup/` | The extended standalone writeup |

## Documentation

```bash
uv sync --group docs
make docs          # live preview at http://127.0.0.1:8000
make docs-build    # strict build into ./site
```

## Licence and attribution

The project is released under the [MIT licence](LICENSE). PyMuPDF, a dependency of the parsing pipeline, is licensed under AGPL-3.0 or a commercial licence; see the attribution
section of the [project report](docs/Project_Report.pdf) and [issue 5](https://github.com/bhanuponguru/WealthPilot/issues/5). No API keys or private data are committed; sample data is synthetic.
