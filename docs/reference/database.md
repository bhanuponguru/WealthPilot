# Database

One Postgres 16 database (`wealthpilot`) with the `pgvector` extension. Application tables are created on first use; LangGraph creates and migrates its own.

## Application tables

### `nim_cache`
Response cache for chat, vision, embedding and rerank calls.

| Column | Type | Notes |
|---|---|---|
| `key` | text, PK | `sha256(kind, model, params, payload)` |
| `kind` | text | `chat`, `embed`, `rerank` |
| `model` | text | |
| `response` | jsonb | serialised reply (`{"message": ...}` for chat, `{"v": [...]}` for embeddings, `{"scores": [...]}` for rerank) |
| `created_at` | timestamptz | |

Empty replies and injected garbage are never stored.

### `nim_bucket`
A single row (`id = 1`) holding the shared, adaptive token bucket.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | always 1 |
| `tokens` | double | tokens currently available (capacity 5) |
| `updated_at` | timestamptz | last refill/consume time |
| `rpm` | double | current allowed rate; `NULL` = use the configured ceiling |

### `nim_calls`
The call log (one row per call, cached or not).

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial, PK | |
| `ts` | timestamptz | |
| `kind` | text | `chat`, `embed`, `rerank` |
| `model` | text | |
| `cached` | boolean | served from the cache |
| `ok` | boolean | |
| `latency_ms` | int | includes limiter wait and retry backoff |
| `retries` | int | |
| `error` | text | first 300 characters, on failure |
| `prompt_tokens`, `completion_tokens` | int | chat only |
| `tag` | text | set with `run_tag(...)`: case id or experiment arm, e.g. `e0-strict-C004` |

### `audit_log`
Append-only, hash-chained decision log.

| Column | Type | Notes |
|---|---|---|
| `id` | bigserial, PK | |
| `ts` | timestamptz | |
| `case_id` | text | |
| `event` | text | e.g. `decision` |
| `payload` | jsonb | the final decision record + `(rule_id, status)` list |
| `prev_hash` | text | previous record's hash (`GENESIS` for the first) |
| `hash` | text | `sha256(prev_hash + case_id + event + canonical payload)` |

### `policy_chunks`
The policy RAG index.

| Column | Type | Notes |
|---|---|---|
| `id` | serial, PK | |
| `policy_id` | text | `strict`, `lenient`, … |
| `strategy` | text | `structure` or `fixed` |
| `chunk_idx` | int | order within the policy |
| `rule_ids` | text[] | rule ids the chunk covers |
| `title`, `text` | text | |
| `embedding` | `vector(768)` | `nomic-embed-text`, `search_document:` prefix |

### `precedents`
Semantic memory of decided cases.

| Column | Type | Notes |
|---|---|---|
| `case_id` | text, PK | |
| `summary` | text | industry, loan amount, grade and memo summary |
| `decision`, `grade` | text | |
| `embedding` | `vector(768)` | |
| `created_at` | timestamptz | |

### `case_runs`
The case index used by the console: one row per underwriting run. Written by `Runner` (start, pause/finish, error); best-effort.

| Column | Type | Notes |
|---|---|---|
| `thread_id` | text, PK | the checkpoint id |
| `case_id` | text | e.g. `C004` or `U20261113-142530` |
| `policy_id` | text | |
| `variant` | text | `clean`, `noisy`, `scanned` or `uploaded` |
| `source` | text | `synthetic` or `upload` |
| `redaction` | boolean | |
| `business_label` | text | **redacted** when redaction is on; never the owner's identity |
| `loan_amount` | double | |
| `status` | text | `running`, `awaiting_doc_review`, `awaiting_approval`, `decided`, `finished`, `error` |
| `recommendation`, `decision`, `grade`, `required_tier` | text | mirrored from the case state |
| `degraded` | boolean | |
| `error` | text | message when `status = 'error'`; cleared on success |
| `created_at`, `updated_at` | timestamptz | |

## LangGraph tables

Created by `langgraph-checkpoint-postgres` and `langgraph-store-postgres` (`setup()` runs on every session open and is idempotent).

| Table | Holds |
|---|---|
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations` | per-thread graph checkpoints (the paused state of every case) |
| `store`, `store_vectors` | the long-term key-value store (`("applicants",)` and `("decisions",)` namespaces); `store_vectors` is created by the library but unused here |

## Useful queries

```sql
-- decisions recorded so far
SELECT ts, case_id, payload->>'decision' AS decision, payload->>'override' AS override FROM audit_log WHERE event = 'decision' ORDER BY id DESC LIMIT 20;

-- every case thread that has saved state (use `wealthpilot show THREAD` to see whether it is paused)
SELECT DISTINCT thread_id FROM checkpoints ORDER BY 1;

-- how big is the cache?
SELECT kind, count(*), pg_size_pretty(sum(pg_column_size(response))) FROM nim_cache GROUP BY 1;
```

## Resetting

| Goal | Command |
|---|---|
| Drop cached model replies | `TRUNCATE nim_cache;` |
| Clear the call log | `TRUNCATE nim_calls;` |
| Rebuild the policy index | `uv run wealthpilot ingest-policy` |
| Wipe **everything** | `docker compose down -v` (deletes the volume) |
