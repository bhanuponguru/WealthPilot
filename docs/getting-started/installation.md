# Installation

All commands are run from the repository root.

## 1. Install the Python environment

```bash
uv sync                      # runtime + dev dependencies
uv sync --group docs         # optional: add the documentation toolchain (mkdocs-material)
```

## 2. Provide your NIM key

Either export it in your shell (recommended — nothing to commit):

```bash
export NVIDIA_NIM_API_KEY="nvapi-..."
```

or copy the template and edit it:

```bash
cp .env.example .env         # then set NVIDIA_API_KEY=...
```

A non-blank value in `.env` wins over the shell environment; a blank value is ignored. See
[Configuration](configuration.md#precedence).

## 3. Start Postgres

```bash
docker compose up -d postgres      # or: make up
```

This starts `pgvector/pgvector:pg16` on `127.0.0.1:5432` (database, user and password are all `wealthpilot`; the data lives
in the `pgdata` Docker volume). The application creates its own tables on first use and enables the `vector` extension.

## 4. Pull the embedding model

```bash
ollama pull nomic-embed-text       # ~270 MB, 768-dimensional embeddings
```

!!! note "Why Ollama for embeddings?"
    None of the 12 NIM embedding models in the public catalog worked for the development account (all returned `404` or
    `410`). Embeddings run locally instead. See [Design decisions](../project/decisions.md).

## 5. Download the public data

```bash
mkdir -p data/sba/raw data/ofac

# SBA 7(a) loan outcomes, FY2010-FY2019 (~255 MB)
curl -L -o data/sba/raw/FOIA_7a_FY2010_FY2019_asof_260930.csv \
  https://data.sba.gov/sites/default/files/uploaded_resources/FOIA_7a_FY2010_FY2019_asof_260930.csv

# OFAC SDN sanctions list
curl -L -o data/ofac/sdn.csv \
  https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV
```

!!! tip "If the SBA file name has changed"
    The SBA publishes refreshed extracts with a new "as of" date in the name. The dataset page
    (`https://data.sba.gov/dataset/7a-504-foia`) lists the current links. If the file name differs, update `SBA_CSV` in
    `src/wealthpilot/risk/pd_model.py`.

## 6. Build the synthetic world

The synthetic applicants, their documents and the ground truth are generated deterministically (seeded).

```bash
uv run python -m wealthpilot.synth.applicants     # 80 applicants + a small synthetic sanctions watchlist
uv run python -m wealthpilot.synth.render_docs    # clean / noisy / scanned PDFs (~40 s, ~260 MB)
uv run python -m wealthpilot.synth.news           # mock adverse-media corpus
```

## 7. Train the risk model and build the ground truth

```bash
uv run wealthpilot train-pd                       # LightGBM on SBA outcomes (~30 s - 3 min)
uv run python -m wealthpilot.synth.groundtruth    # PD + reference-engine decisions under both policies
```

`train-pd` saves `models/pd_model.joblib` and — if an MLflow server is reachable — logs the run and registers the model
`wealthpilot-pd`. If MLflow is down it prints a warning and continues.

## 8. Start the supporting services

=== "MLflow (optional but recommended)"

    ```bash
    make mlflow &          # http://127.0.0.1:5000 , SQLite backend, local artifacts
    ```

=== "MCP servers (required for underwriting)"

    ```bash
    uv run wealthpilot mcp-up &       # fincalc :8101, policydocs :8102, research :8103
    ```

    On first start, `policydocs` embeds and indexes both policies (about 30 seconds). Wait until all three ports accept
    connections before running a case.

## 9. Verify

```bash
uv run pytest -m "not live"                      # offline unit tests (no services needed)
uv run pytest -m live                            # needs Postgres, Ollama, MCP servers and a NIM key
uv run wealthpilot audit-verify                  # {"ok": true, ...}
uv run wealthpilot doctor                        # every service and artifact, with the fix for anything missing
```

`doctor` is the quickest health check at any time: it lists Postgres, Ollama, the three MCP servers, the NIM key, the risk model, the data files and MLflow, and exits non-zero if something
required is missing.

## 10. Launch the web console

```bash
uv run wealthpilot ui                            # http://127.0.0.1:8501
```

!!! success "You are ready"
    Continue with the [Quickstart](quickstart.md) or go straight to [Using the web console](../guides/console.md).
