# Command-line interface

The `wealthpilot` command is a [Typer](https://typer.tiangolo.com/) app (`wealthpilot.cli`).

```bash
uv run wealthpilot --help
```

| Command | Purpose |
|---|---|
| [`run`](#run) | Underwrite one synthetic case until it needs a human |
| [`approve`](#approve) | Resume a paused case with a human decision |
| [`show`](#show) | Show the current state of a case thread |
| [`ingest-policy`](#ingest-policy) | Rebuild the policy RAG indexes |
| [`train-pd`](#train-pd) | Train the SBA probability-of-default model |
| [`audit-verify`](#audit-verify) | Verify the hash-chained audit log |
| [`mcp-up`](#mcp-up) | Start the three MCP servers |
| [`ui`](#ui) | Launch the Streamlit web console |
| [`doctor`](#doctor) | Check every service and artifact and print the fix for anything missing |

!!! info "Prerequisites"
    `run`, `approve`, `show` and `ui` need Postgres, Ollama, the MCP servers and a NIM key (`doctor` tells you what is missing). `train-pd` needs the SBA CSV. `audit-verify` and
    `ingest-policy` need Postgres (and Ollama for the latter).

## `run`

```bash
uv run wealthpilot run CASE_ID [--policy strict|lenient] [--variant clean|noisy|scanned]
                               [--redaction | --no-redaction] [--thread NAME]
```

| Option | Default | Meaning |
|---|---|---|
| `CASE_ID` | — | a synthetic applicant, `C001`…`C080` |
| `--policy` | `strict` | policy id; any directory under `data/policies/` |
| `--variant` | `clean` | which rendered PDFs to read |
| `--redaction / --no-redaction` | on | redact identity from text sent to the LLM |
| `--thread` | the case id | checkpoint id — **use a fresh value per run** |

Prints each node as it finishes, then the recommendation, required approver, grade and the per-rule checklist, and tells you how to resume.

## `approve`

```bash
uv run wealthpilot approve THREAD --decision approve|decline|revise --tier "Analyst|Senior Credit Officer|Credit Committee"
                                  [--approver ID] [--reason TEXT]
```

Resumes the paused thread. A tier below the required one is rejected (the command reports it is still waiting). On success it prints the final record, including
`override` if you contradicted the recommendation.

## `show`

```bash
uv run wealthpilot show THREAD
```

Prints the current state: recommendation, tier, grade, degraded flag, the checklist, and whether the thread is waiting for input or finished.

## `ingest-policy`

```bash
uv run wealthpilot ingest-policy
```

Re-embeds and re-indexes both bundled policies under both chunking strategies. Run it after editing a `policy.md`. For a *new* policy id see
[Writing a new policy](new-policy.md#3-index-it).

## `train-pd`

```bash
uv run wealthpilot train-pd
```

Trains the LightGBM model on the SBA data (about 30 s to 3 min), saves `models/pd_model.joblib` and `models/pd_metrics.json`, and — if MLflow is reachable —
logs the run and registers `wealthpilot-pd`. Prints the metrics JSON.

## `audit-verify`

```bash
uv run wealthpilot audit-verify
# {"ok": true, "records": 17, "first_bad_id": null}
```

Exit code `0` if the chain is intact, `1` if not (with the first bad record id).

## `mcp-up`

```bash
uv run wealthpilot mcp-up
```

Starts `fincalc` (8101), `policydocs` (8102) and `research` (8103) as separate processes and waits; **Ctrl-C** stops all three.

## `ui`

```bash
uv run wealthpilot ui [--port 8501] [--host 127.0.0.1] [--headless]
```

Launches the [web console](console.md). `--headless` does not open a browser tab. Keep the default host: the console has no login. The command also passes the 25 MB upload limit that matches the form's validation.

## `doctor`

```bash
uv run wealthpilot doctor
```

Checks Postgres, Ollama (and the embedding model), the three MCP servers, the NIM key (presence only), the risk model, the synthetic data, the OFAC list and MLflow. Prints one line per component and, for anything wrong, the command that fixes it:

```text
 ✓ Postgres                 reachable
 ✓ Ollama (embeddings)      ready
 ✗ MCP: fincalc             port 8101 closed
     fix: uv run wealthpilot mcp-up
 ...
Not ready: ...
```

Exit code `0` when everything *required* is ready, `1` otherwise (MLflow and the synthetic data are optional).

## Tips

* **Repeating a run is nearly free**: identical prompts are served from the [cache](../concepts/nim-gateway.md#response-cache).
* **Compare policies** by running the same case with `--policy strict` and `--policy lenient` on different threads.
* **See what the model saw** by looking at the case's [MLflow trace](../concepts/observability.md#mlflow-traces).
* **Set a deterministic budget** for slow days with `NIM_RPM_BUDGET=10`.
