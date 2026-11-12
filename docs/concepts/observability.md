# Observability

There are four complementary views of what the system did.

| View | Where | Answers |
|---|---|---|
| **MLflow traces** | MLflow UI, experiment `wealthpilot-traces` | *What happened inside this case, step by step?* |
| **Call log** | Postgres table `nim_calls` | *How many model calls, how slow, how many retries, which fallbacks?* |
| **Experiment runs** | MLflow experiments `wealthpilot-E0-…` to `E4-…` | *How accurate/reliable was it across many cases?* |
| **Audit log** | Postgres table `audit_log` | *Who decided what, and has the record been altered?* |

## MLflow traces

`wealthpilot.observability.enable()` turns on `mlflow.langchain.autolog()` for every graph session, and each underwriting run is wrapped in a parent
span (`underwrite_case`) so that **one case = one trace**. Traces are tagged:

| Tag | Example |
|---|---|
| `case_id` | `C004` |
| `policy_id` | `strict` |
| `thread_id` | `demo-1` |
| `redaction` | `True` |

A full run produces a trace with dozens of spans (graph nodes, LLM calls, tool calls). Resuming a paused case produces its own trace under the same tags.

```python
import mlflow
mlflow.set_tracking_uri("http://127.0.0.1:5000")
exp = mlflow.get_experiment_by_name("wealthpilot-traces")
traces = mlflow.search_traces(experiment_ids=[exp.experiment_id], return_type="list")
```

Tracing is **best-effort**: if MLflow is down, underwriting proceeds untraced.

## The call log

Every NIM and Ollama call is stored in `nim_calls`. A few useful queries:

```sql
-- calls, failures and mean latency per model in the last hour
SELECT model, kind,
       count(*) FILTER (WHERE NOT cached) AS real_calls,
       count(*) FILTER (WHERE cached)     AS cache_hits,
       count(*) FILTER (WHERE NOT ok)     AS failed,
       round(avg(latency_ms) FILTER (WHERE NOT cached AND ok)) AS avg_ms
FROM nim_calls WHERE ts > now() - interval '1 hour' GROUP BY 1, 2 ORDER BY 3 DESC;

-- cost of one experiment arm
SELECT count(*), sum(prompt_tokens), sum(completion_tokens) FROM nim_calls WHERE tag LIKE 'e0-strict-%';

-- what is going wrong?
SELECT left(error, 80) AS error, model, count(*) FROM nim_calls WHERE NOT ok GROUP BY 1, 2 ORDER BY 3 DESC;
```

!!! tip "Latency includes waiting"
    `latency_ms` is measured around the whole gateway call, so it includes time spent waiting for a rate-limiter token and any retry
    backoff — which is what a caller actually experiences.

The current adaptive rate is `SELECT rpm FROM nim_bucket;`.

## Experiment runs

Each experiment arm is logged as an MLflow run with its parameters and headline metrics; tables and raw results are written to
`report/results/*.json` and `*.md`. The PD model is registered as `wealthpilot-pd`.

## Audit log

See [Compliance](compliance.md#the-audit-log). Verify the chain with `uv run wealthpilot audit-verify`.

## Starting and inspecting MLflow

```bash
make mlflow &                 # http://127.0.0.1:5000 ; SQLite backend (mlflow.db), artifacts in ./mlartifacts
```

!!! note "Why MLflow and not Langfuse?"
    Self-hosted Langfuse needs about six containers (ClickHouse, Postgres, Redis, object storage, web and worker) — too much for a 6 GB machine.
    MLflow runs as a single process and covers tracing, experiment tracking and the model registry. See [Design decisions](../project/decisions.md).
