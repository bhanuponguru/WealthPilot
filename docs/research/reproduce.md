# Reproducing the experiments

This page describes how to regenerate the synthetic world and rerun each experiment. It is operational: it names the scripts and commands
of the research package. The package is not part of the deployed product.

## Prerequisites

* The product stack is running: `docker compose up -d` from the repository root. The experiments use its database, local embedding
  service and tool servers.
* A NVIDIA NIM API key is set as `NVIDIA_API_KEY` (or `NVIDIA_NIM_API_KEY`) in the shell or in `.env`. See
  [Configuration](../get-started/configuration.md).
* The one-shot bootstrap service has completed, so that the OFAC sanctions list is present. The generator needs it.
* The trained risk model is present in `artifacts/`. It ships with the repository and is used to compute the ground truth.

## Ways to run

### In the lab container (supported)

The `lab` service of the compose file contains the product and the research package. Run commands from the repository root:

```bash
docker compose --profile lab run --rm lab <command>
```

The working directory in the container is `research/`, so scripts are addressed as `experiments/<script>.py`. Results are written to
`research/results/` on the host (bind mount). Generated data is stored in volumes: demonstration data in `data` (under `demo/`, shared with the
product) and the ground truth and counterfactual documents in `labdata`.

Environment variables are passed with `-e`, for example `docker compose --profile lab run --rm -e NIM_RPM_BUDGET=15 lab <command>`.

### Locally

```bash
uv sync --all-packages --group dev
cd research/experiments
uv run python <script>.py [arguments]
```

The default compose file publishes only the console and Postgres on the host. A local run therefore needs Ollama, the tool servers
(`wealthpilot mcp-up`) and optionally MLflow running on the host, with `DATABASE_URL`, `OLLAMA_URL`, `MCP_HOST` and `MLFLOW_TRACKING_URI`
pointing to them. In the rest of this page, commands are given for the lab container; locally, replace
`docker compose --profile lab run --rm lab python experiments/<script>.py` with `uv run python <script>.py` run in `research/experiments/`, and
`python -m ...` with `uv run python -m ...`.

## Generate the synthetic world

Run the four generators in this order. Each step reads the output of the previous one.

```bash
docker compose --profile lab run --rm lab python -m wealthpilot_lab.synth.applicants   # 80 applicants (seed 7) and the synthetic watchlist
docker compose --profile lab run --rm lab python -m wealthpilot_lab.synth.render_docs  # PDFs: clean, noisy and scanned variants per applicant
docker compose --profile lab run --rm lab python -m wealthpilot_lab.synth.news         # mock adverse-media corpus
docker compose --profile lab run --rm lab python -m wealthpilot_lab.synth.groundtruth  # reference-engine truth under both policies
```

The first three write applicants, documents, news and the watchlist to the demonstration-data folder (`<data>/demo/`). The last writes
`ground_truth.json` to the research data folder and prints the outcome counts under each policy, which should match the table in
[The synthetic world](synthetic-data.md). To try the product with these files, set `WEALTHPILOT_DEMO=1` (see
[Configuration](../get-started/configuration.md)).

## Run the experiments

Run each command from the repository root with the stack up. Argument values are those used for the reported results.

| Experiment | Command | Outputs in `research/results/` |
|---|---|---|
| E0 policy adherence | `docker compose --profile lab run --rm lab python experiments/e0_policy.py 12` | `e0_policy.json`, `e0_policy.md` |
| E1 document parsing | `docker compose --profile lab run --rm lab python experiments/e1_parsing.py 12` | `e1_parsing.json`, `e1_parsing.md` |
| E2 policy retrieval | `docker compose --profile lab run --rm lab python experiments/e2_rag.py` | `e2_rag.json`, `e2_rag.md` |
| E3(a)(b) fairness audit | `docker compose --profile lab run --rm lab python experiments/e3_fairness.py` | `e3_fairness_ab.json`, `e3_fairness_ab.md` |
| E3(c)(d) counterfactuals | `docker compose --profile lab run --rm lab python experiments/e3_counterfactual.py 3` | `e3_counterfactual.json`, `e3_counterfactual.md` |
| E4 reliability | `docker compose --profile lab run --rm lab python experiments/e4_reliability.py 4` | `e4_reliability.json`, `e4_reliability.md` |

The argument of E0, E1, E3(c) and E4 is the number of cases. The script defaults differ from the reported runs (E1 defaults to 16 cases and
E3(c) to 4), so pass the values shown.

Notes per experiment:

* **E0.** Runs 12 cases under both policies, four at a time, and writes the per-rule table and every mismatch with the model's stated reason.
  Setting `E0_NAME` writes the results under another name instead of overwriting `e0_policy.*` (used for model comparison, below).
* **E1.** Uses every fifth applicant, from the first. Baselines need no model calls.
* **E2.** No arguments. Runs all 10 retrieval combinations over the 104 queries and indexes the policies if needed.
* **E3(a).** Needs the public SBA 7(a) FOIA file for fiscal years 2010 to 2019 (`data.sba.gov/dataset/7a-504-foia`) at
  `<data>/sba/raw/FOIA_7a_FY2010_FY2019_asof_260930.csv`. The file is not part of the image or the volumes. In the lab container, mount it from
  the host:

    ```bash
    docker compose --profile lab run --rm -v "$PWD/data/sba:/data/sba:ro" lab python experiments/e3_fairness.py
    ```

  E3(b) needs no model calls and no external data. Both parts run in the same command.
* **E3(c).** Renders counterfactual documents into the research data folder, runs every identity with redaction off and on, and then reruns the
  originals without the response cache to measure the noise floor.
* **E4.** Disables the response cache and enables the fallback model by itself. It runs all seven fault profiles on four cases and then the crash and
  resume test. To rerun only some profiles and merge them into the existing result, pass a comma-separated list as the second argument. Then
  classify the outcomes against the ground truth:

    ```bash
    docker compose --profile lab run --rm lab python experiments/e4_reliability.py 4 mcp_flaky,research_down,fincalc_down
    docker compose --profile lab run --rm lab python experiments/e4_outcomes.py
    ```

  The profile names are `none`, `429_storm`, `timeouts`, `malformed_output`, `mcp_flaky`, `research_down` and `fincalc_down`. The outcome
  classification is appended to `e4_reliability.json` and `e4_reliability.md` and must be rerun after every E4 run.

### Settings that affect the results

| Setting | Effect |
|---|---|
| `NIM_RPM_BUDGET` | Ceiling of the shared request-rate limiter. The default is 15. |
| `CHAT_MODEL` | Chat model for the run. The default is `nvidia/nemotron-3.5-lightning-30b-a3b`. |
| `CHAT_FALLBACK_MODEL` | Optional second chat model. Empty (disabled) by default; the accuracy experiments run without it. |
| `MLFLOW_DISABLE_AGENT_HINT=1` | Suppresses an MLflow hint in the output. Optional. |

Runs are logged to MLflow when it is reachable; a failure to log does not stop an experiment.

### Expected variation

A rerun produces the same mechanisms but not necessarily the same counts: models are nondeterministic even at temperature 0, and free-tier
availability changes. The response cache serves earlier replies for identical prompts, so a repeated E0, E1 or E2 run on the same database is
faster and mostly identical. To obtain fresh replies, empty the `nim_cache` table in the database before the run. On a throttled free tier an
uncached E0 run takes a long time (the reported run averaged about 400 s per case-run, four at a time). See
[Limitations of the evaluation](limitations.md).

## Select or compare language models

### Probe model availability

The probe sends a tool-calling request and a plain question to each tool-capable chat model in the provider catalog and writes
`research/results/nim_probe.json`.

```bash
docker compose --profile lab run --rm lab python scripts/probe_nim_models.py                              # every candidate
docker compose --profile lab run --rm lab python scripts/probe_nim_models.py --only poolside/laguna-xs-2.1  # a specific model
```

### Compare candidate models on a reduced E0

The comparison runs E0 on 2 cases under both policies for one model at a time, with `CHAT_MODEL` set to the candidate and `E0_NAME` set to a path under
`model_compare/`:

```bash
mkdir -p research/results/model_compare
docker compose --profile lab run --rm \
  -e CHAT_MODEL=poolside/laguna-xs-2.1 -e E0_NAME=model_compare/e0_poolside_laguna-xs-2_1 \
  lab python -W ignore experiments/e0_policy.py 2
```

Locally, `research/scripts/compare_models_e0.sh <n_cases> <model> [<model> ...]` runs the same comparison for several models in sequence and
writes `research/results/model_compare/`. The script calls `uv run` and is intended for a local checkout. The findings are summarized in
[Research overview](index.md#selecting-the-language-model).
