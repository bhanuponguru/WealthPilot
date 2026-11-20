# Command-line interface

The `wealthpilot` command offers operator and scripting access to the product: running and resuming cases, maintaining the policy index and the sanctions list, verifying the audit log and checking the health of the deployment.

The [console](console.md) is the interface for reviewers. The command line is intended for operators and for automation. Cases are not entered or reviewed here, apart from `demo-run` and `approve`, which exist for scripted trials.

## Running commands

In the deployed stack, run a command inside the `console` service:

```bash
docker compose exec console wealthpilot <command>
```

In a local checkout with the dependencies installed, run it with `uv`:

```bash
uv run wealthpilot <command>
```

List all commands, or the options of one command:

```bash
docker compose exec console wealthpilot --help
docker compose exec console wealthpilot approve --help
```

The examples below show `docker compose exec console wealthpilot`; replace it with `uv run wealthpilot` for a local checkout. Commands read the same settings as the rest of the product (see [Configuration](../get-started/configuration.md)). Inside the Docker network they reach the other services by their service names, so a command run in the `console` service needs no extra setup.

## Commands

| Command | Purpose | Needs |
|---|---|---|
| [`doctor`](#doctor) | Check every service and data item and print the fix for anything missing | Nothing; reports what is missing |
| [`audit-verify`](#audit-verify) | Verify the hash-chained audit log | Postgres |
| [`ingest-policy`](#ingest-policy) | Rebuild the policy search index | Postgres, Ollama |
| [`fetch-ofac`](#fetch-ofac) | Download the OFAC sanctions list | Internet access |
| [`bootstrap`](#bootstrap) | Prepare a fresh deployment | Internet access (for the sanctions list) |
| [`demo-run`](#demo-run) | Run a sample applicant through the workflow | Demonstration data, all services, model API key |
| [`approve`](#approve) | Resume a paused case with a human decision | All services, model API key |
| [`show`](#show) | Show the state of a case | Postgres |
| [`train-pd`](#train-pd) | Train the default-risk model | The SBA 7(a) loan data file |
| [`ui`](#ui) | Start the console | All services |
| [`mcp-up`](#mcp-up) | Start the three tool servers | Postgres, Ollama |

Commands that start a case or resume one need the full stack (database, embedding service, tool servers) and a model API key (`NVIDIA_API_KEY` or `NVIDIA_NIM_API_KEY`). Run `doctor` first if unsure.

### Demonstration data

`demo-run` is the only command that needs optional demonstration data: sample applicants with ready-made statements, stored in the `data` volume. Set `WEALTHPILOT_DEMO=1` to offer the same applicants in the console. Without the data files the command reports `No such sample applicant` and exits with code 1. All other commands work without demonstration data. Cases with real documents are entered in the console. See [Deploy with Docker](../get-started/deploy.md#demonstration-mode) for how to enable the data.

## doctor

```bash
docker compose exec console wealthpilot doctor
```

Checks Postgres, the embedding service and its model, the three tool servers, the model API key (presence only, the key is not validated), the risk model, the sanctions list, the demonstration data (when enabled) and MLflow. It prints one line per component and, for anything wrong, the command that fixes it.

| Mark | Meaning |
|---|---|
| Check mark | Ready |
| Exclamation mark | Missing, but optional (the sanctions list, demonstration data, MLflow) |
| Cross | Missing and required |

The command ends with `Ready to underwrite.` or `Not ready:` followed by the failed required components.

| Exit code | Meaning |
|---|---|
| 0 | Postgres, the model API key, the risk model and the embedding service are all ready |
| 1 | At least one of those four is missing |

The tool servers and the optional items are reported but do not change the exit code, because a case can still run in a degraded state without them. Read the printed lines when a script needs to know the tool servers are up.

## audit-verify

```bash
docker compose exec console wealthpilot audit-verify
# {"ok": true, "records": 17, "first_bad_id": null}
```

Recomputes the whole hash chain of the audit log and prints the result as JSON: whether the chain is intact, the number of records and the id of the first inconsistent record.

| Exit code | Meaning |
|---|---|
| 0 | The chain is intact |
| 1 | A record was edited, removed or inserted; `first_bad_id` names the first inconsistent record |

Use the exit code to run the check on a schedule, for example from a cron job on the host. The History page of the console shows the same result. See [Compliance](../architecture/compliance.md) and [Troubleshooting](../administration/troubleshooting.md).

## ingest-policy

```bash
docker compose exec console wealthpilot ingest-policy
docker compose restart mcp console
```

Re-embeds and re-indexes every credit policy found in the `policies/` folder, once per chunking strategy, and prints the number of chunks written for each. Run it after editing a `policy.md`. The running services keep the old index in memory, so restart `mcp` and `console` afterwards. See [Managing credit policies](../administration/policies.md).

## fetch-ofac

```bash
docker compose exec console wealthpilot fetch-ofac [--force]
```

Downloads the OFAC Specially Designated Nationals list into the `data` volume, where sanctions screening reads it, and prints the file location and size. The download is skipped when the list is already present. `--force` downloads it again, which refreshes the list.

The command fails with a non-zero exit code when the download fails or the downloaded file looks incomplete.

## bootstrap

```bash
docker compose exec console wealthpilot bootstrap
```

Prepares a fresh deployment: creates the data folders and downloads the sanctions list if it is missing. The `bootstrap` service of the compose file runs it automatically at start. A failed download prints a warning and does not stop the start-up; screening then finds no matches until `fetch-ofac` succeeds. The exit code is 0 in both cases.

## demo-run

```bash
docker compose exec console wealthpilot demo-run CASE_ID [--policy strict|lenient]
                                                 [--variant clean|noisy|scanned]
                                                 [--redaction | --no-redaction] [--thread NAME]
```

Runs one sample applicant through the workflow until it needs a human, printing each step as it finishes, then the recommendation, the required approver, the grade and the checklist of rule statuses.

| Option | Default | Meaning |
|---|---|---|
| `CASE_ID` | required | Identifier of a sample applicant in the demonstration data |
| `--policy` | `strict` | Credit policy to apply: the name of a folder in `policies/` |
| `--variant` | `clean` | Layout of the statements to read: `clean`, `noisy` (varied labels) or `scanned` (images) |
| `--redaction` / `--no-redaction` | on | Remove the owner's identity from text sent to models |
| `--thread` | the case id | Identifier of the saved run. Use a new value to run the same case again |

The run pauses at the approval gate, or earlier at document review. Resume it with `approve`.

## approve

```bash
docker compose exec console wealthpilot approve THREAD --decision approve|decline|revise \
    --tier "Analyst|Senior Credit Officer|Credit Committee" [--approver ID] [--reason TEXT]
```

Resumes a paused case with a human decision and prints the result.

| Option | Default | Meaning |
|---|---|---|
| `THREAD` | required | The thread identifier of the paused run |
| `--decision` | required | `approve`, `decline`, or `revise` to send the memo back for a rewrite |
| `--tier` | required | The approval authority the decision is made under |
| `--approver` | `cli-user` | Identifier of the person deciding, recorded in the decision |
| `--reason` | empty | Reason; recorded as the override reason when the decision differs from the recommendation |

A tier below the required one is rejected: the command reports that the case is still waiting for input. On success it prints the final record, including `override` when the decision contradicts the recommendation. A paused case that is waiting for document review is resumed from the console.

## show

```bash
docker compose exec console wealthpilot show THREAD
```

Prints the current state of a run: the recommendation, the required approver, the grade, a degraded flag with its reasons, the checklist of rule statuses, and whether the run is waiting for input or finished. The command changes nothing.

## train-pd

```bash
uv run wealthpilot train-pd
```

Trains the default-risk model on the public SBA 7(a) loan data, writes `pd_model.joblib` and `pd_metrics.json` to the `artifacts/` folder, logs the run to MLflow when it is reachable and prints the metrics as JSON. The SBA data file has to be present in `data/sba/raw/`. Training takes from about half a minute to a few minutes.

The deployed product uses the model that ships in `artifacts/`; the command is only needed to rebuild it from a local checkout, after which the image is rebuilt. See [Risk model](../architecture/risk-model.md).

## ui

```bash
docker compose exec console wealthpilot ui [--port 8501] [--host 127.0.0.1] [--headless]
```

Starts the console. The `console` service runs it with `--host 0.0.0.0 --headless` already, so it is normally not run by hand. For a local checkout:

```bash
uv run wealthpilot ui --headless
```

| Option | Default | Meaning |
|---|---|---|
| `--port` | `8501` | Port to serve on |
| `--host` | `127.0.0.1` | Address to bind. The console has no login: keep the default or put an authenticating reverse proxy in front |
| `--headless` | off | Do not open a browser tab |

The command passes the 25 MB upload limit that matches the validation of the New case form. See [Using the console](console.md).

## mcp-up

```bash
uv run wealthpilot mcp-up
```

Starts the three tool servers as separate processes: `fincalc` on port 8101, `policydocs` on 8102 and `research` on 8103. The command keeps running; Ctrl-C stops all three. The `mcp` service runs this command, so it is only used by hand in a local checkout. See [Tool servers](../architecture/tool-servers.md).

## Exit codes

| Command | Exit code 0 | Exit code 1 |
|---|---|---|
| `doctor` | Required components ready | A required component is missing |
| `audit-verify` | Audit chain intact | Audit chain broken |
| `demo-run` | Run reached a pause or finished | Unknown sample applicant. Other failures also end with a non-zero code |
| `fetch-ofac` | List present | Download failed |
| `bootstrap` | Always, also when the download failed (a warning is printed) | Not used |
| Other commands | Command completed | Command failed with an error |
