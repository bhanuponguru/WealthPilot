# Observability

Three complementary views show what the system did.

| View | Where | Answers |
|---|---|---|
| Traces | The MLflow tracking server, experiment `wealthpilot-traces` | What happened inside this case, step by step? |
| Call log | The Postgres table `nim_calls`, summarized on the System page of the console | How many model calls, how slow, how many retries and failures? |
| Audit log | The Postgres table `audit_log`, shown on the History page of the console | Who decided what, and has the record been altered? |

## Traces

Tracing instruments every workflow run. Each run is wrapped in a parent span so that one case run is one trace, and the steps, model
calls and tool calls appear as spans beneath it. Traces carry tags:

| Tag | Example |
|---|---|
| Case id | `C004` |
| Policy id | `strict` |
| Thread id | `C004-ui-142530` |
| Redaction | `True` |

A full run produces a trace with dozens of spans. Resuming a paused case produces its own trace under the same tags.

Tracing is best effort. The workflow probes the tracking server before it starts and, if it is unreachable, runs without traces.
Underwriting never waits for MLflow.

In the Docker deployment the tracking server listens on port 5000 inside the Compose network and is not published on the host. See
[Operations](../administration/operations.md) for browsing it.

## The call log

Every call to the model API or the embeddings service is stored in `nim_calls`. Open a SQL session with
`docker compose exec postgres psql -U wealthpilot` and run queries such as these:

```sql
-- calls, failures and mean latency per model in the last hour
SELECT model, kind,
       count(*) FILTER (WHERE NOT cached) AS real_calls,
       count(*) FILTER (WHERE cached)     AS cache_hits,
       count(*) FILTER (WHERE NOT ok)     AS failed,
       round(avg(latency_ms) FILTER (WHERE NOT cached AND ok)) AS avg_ms
FROM nim_calls WHERE ts > now() - interval '1 hour' GROUP BY 1, 2 ORDER BY 3 DESC;

-- what is going wrong?
SELECT left(error, 80) AS error, model, count(*) FROM nim_calls WHERE NOT ok GROUP BY 1, 2 ORDER BY 3 DESC;
```

The current adaptive request rate is available with `SELECT rpm FROM nim_bucket;`. The System page of the console shows the same
figures with a 24-hour summary, and can reset the rate limiter.

!!! note "Latency includes waiting"
    The recorded latency is measured around the whole gateway call, so it includes time spent waiting for a rate-limiter token and any
    retry backoff, which is what a caller actually experiences.

## The audit log

See [The audit log](compliance.md#the-audit-log). Verify the chain with `wealthpilot audit-verify` or on the History page.

## Model registry

The default-probability model is registered as `wealthpilot-pd` in MLflow when it is trained. The file in `artifacts/` is the copy
the tool server serves, so scoring does not depend on the tracking server. See [Risk model](risk-model.md).

## Why MLflow

A self-hosted LLM-observability platform typically needs several supporting services, such as a column store, a cache, object storage
and separate web and worker processes. MLflow runs as a single process and covers tracing, the model registry and a web interface,
which keeps the deployment small. See [Design decisions](decisions.md#d7-mlflow-for-tracing-and-the-model-registry).
