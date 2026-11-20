# Database

Every table the product creates, with its purpose, columns, retention and backup notes.

The product uses one PostgreSQL 16 database with the `pgvector` extension, provided by the `postgres` service. The default database name and user are both `wealthpilot`. The tables are created on first use, so a new deployment starts with an empty database and needs no migration step. The data lives in the `pgdata` volume.

The tables fall into three groups:

| Group | Tables |
|---|---|
| Cases and decisions | `case_runs`, `audit_log`, `precedents`, workflow tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `store`, `store_migrations`) |
| Policy retrieval | `policy_chunks` |
| Model gateway | `nim_cache`, `nim_bucket`, `nim_calls` |

!!! warning "The database contains personal data"
    The saved workflow state includes the owner's name, the business name, gender, name origin and address (the sealed part of the [case state](case-state.md)). Treat the database and its backups as sensitive. The other tables hold no identity fields: the case index and the audit log store only the redacted business label and decision facts.

## Cases and decisions

### case_runs

The case index. One row per underwriting run, so that the console can list, filter and reopen cases without reading every saved state. The row is created when a run starts and updated when it pauses, finishes or fails. The index is best-effort: a failure to write it never affects underwriting.

| Column | Type | Description |
|---|---|---|
| `thread_id` | text, primary key | Identifier of the run; also the key of its saved workflow state |
| `case_id` | text | Case identifier |
| `policy_id` | text | Credit policy applied |
| `variant` | text | Document layout of a demonstration case (`clean`, `noisy`, `scanned`), or `uploaded` for uploaded documents |
| `source` | text | `demo` for a demonstration applicant, `upload` for a case entered in the console |
| `redaction` | boolean | Whether redaction was on |
| `business_label` | text | Business name, redacted when redaction is on; never the owner's identity |
| `loan_amount` | double precision | Requested amount |
| `status` | text | `running`, `awaiting_doc_review`, `awaiting_approval`, `decided`, `finished` or `error` |
| `recommendation`, `decision`, `grade`, `required_tier` | text | Headline results mirrored from the case state |
| `degraded` | boolean | Whether the run was degraded |
| `error` | text | Error message when `status` is `error`; cleared on success |
| `created_at`, `updated_at` | timestamptz | Creation and last update time |

Status values: a case is `running` while a step executes, `awaiting_doc_review` or `awaiting_approval` while it waits for a person, `decided` when a final decision was recorded, `finished` when a run ended without a final record, and `error` when a run stopped with an error.

### audit_log

The tamper-evident decision log. Records are only appended. Each record stores the hash of the previous record, so editing or deleting any record breaks the chain. One `decision` record is written when a case is finalized.

| Column | Type | Description |
|---|---|---|
| `id` | bigserial, primary key | Sequence number |
| `ts` | timestamptz | Time of the record |
| `case_id` | text | Case identifier |
| `event` | text | Event type; `decision` |
| `payload` | jsonb | The [final record](case-state.md#final-record) plus the list of rule ids with their statuses |
| `prev_hash` | text | Hash of the preceding record; `GENESIS` for the first |
| `hash` | text | SHA-256 over the previous hash, case id, event and the canonical payload |

Writers take an exclusive table lock while extending the chain, so concurrent decisions cannot fork it. The command `wealthpilot audit-verify` and the History page of the console recompute the whole chain. See [Compliance](../architecture/compliance.md).

### precedents

The memory of decided cases, used to show similar earlier cases in the credit memo. A row is written when a case with a memo is finalized, except when its documents were rejected.

| Column | Type | Description |
|---|---|---|
| `case_id` | text, primary key | Case identifier |
| `summary` | text | Industry, loan amount, grade and memo summary |
| `decision`, `grade` | text | Final decision and risk grade |
| `embedding` | vector(768) | Embedding of the summary, produced locally by the `ollama` service |
| `created_at` | timestamptz | Time of the decision |

Retrieval is by cosine distance. The results are informational and are never a basis for a decision. See [Memory](../architecture/memory.md).

### Workflow tables

Created and migrated by the workflow library. They are created when the first session opens and are not modified by hand.

| Table | Holds |
|---|---|
| `checkpoints`, `checkpoint_blobs`, `checkpoint_writes` | The saved [case state](case-state.md) of every run after every step. A paused case resumes from here, also after a restart |
| `checkpoint_migrations` | Schema version of the checkpoint tables |
| `store` | Long-term memory as key-value documents: under the namespace `applicants`, the earlier decisions of each applicant; under `decisions`, the final record of each case |
| `store_migrations` | Schema version of the `store` table |

## Policy retrieval

### policy_chunks

The search index over the credit policies. Each policy is indexed twice, once per chunking strategy: `structure` splits the document into its sections, which is what the product uses to search and to look up rules, and `fixed` splits it into overlapping windows of fixed size.

| Column | Type | Description |
|---|---|---|
| `id` | serial, primary key | Row identifier |
| `policy_id` | text | Policy folder name, for example `strict` |
| `strategy` | text | `structure` or `fixed` |
| `chunk_idx` | integer | Position of the chunk within the policy |
| `rule_ids` | text[] | Rule ids the chunk covers |
| `title`, `text` | text | Section title and text |
| `embedding` | vector(768) | Embedding of the chunk, produced by the `ollama` service with the `nomic-embed-text` model |

The `policydocs` tool server indexes every policy folder that has no chunks yet when it starts. After a policy file changes, rebuild the index with `wealthpilot ingest-policy`, which replaces the chunks of each policy. See [Managing credit policies](../administration/policies.md).

## Model gateway

The model gateway stores its shared state in the database so that every process (console, tool servers, command line) uses the same cache and the same rate limit. See [Model gateway](../architecture/model-gateway.md).

### nim_cache

The response cache for model calls. A repeated identical call is answered from here without contacting the model provider.

| Column | Type | Description |
|---|---|---|
| `key` | text, primary key | SHA-256 over the call kind, model, parameters and payload |
| `kind` | text | `chat`, `embed` or `rerank` |
| `model` | text | Model name |
| `response` | jsonb | The serialized reply |
| `created_at` | timestamptz | Time the entry was stored |

Empty replies and corrupted replies are not stored. The cache is controlled by the setting `NIM_CACHE_ENABLED` (see [Configuration](../get-started/configuration.md)).

### nim_bucket

The shared, adaptive rate limiter. The table holds a single row.

| Column | Type | Description |
|---|---|---|
| `id` | integer, primary key | Always 1 |
| `tokens` | double precision | Request tokens currently available (capacity 5) |
| `updated_at` | timestamptz | Time of the last refill or use |
| `rpm` | double precision | Current allowed requests per minute; null means the configured budget `NIM_RPM_BUDGET` |

The rate drops when the provider answers that a limit was exceeded and recovers gradually after successful calls, never below 6 and never above the configured budget.

### nim_calls

The model call log: one row per call, cached or not. It is the source of the model call figures of the last 24 hours shown on the System page.

| Column | Type | Description |
|---|---|---|
| `id` | bigserial, primary key | Row identifier |
| `ts` | timestamptz | Time of the call |
| `kind` | text | `chat`, `embed` or `rerank` |
| `model` | text | Model name |
| `cached` | boolean | Served from `nim_cache` |
| `ok` | boolean | Whether the call succeeded |
| `latency_ms` | integer | Duration including waiting for the rate limiter and retries |
| `retries` | integer | Number of retries |
| `error` | text | First 300 characters of the error, on failure |
| `prompt_tokens`, `completion_tokens` | integer | Token counts, for chat calls |
| `tag` | text | Optional free-text label of the run that made the call; empty in ordinary operation |

## Retention

The product does not delete data on its own. Every table grows until it is cleaned up by an operator.

| Table | Growth | Cleanup |
|---|---|---|
| `case_runs`, `checkpoint*`, `store` | One run adds one index row and a set of checkpoints; the saved state is the largest item | Apply the retention period of the credit policy (7 or 5 years for the bundled policies) with a scheduled job of your own |
| `audit_log` | One row per decision | Do not delete rows: removing any record breaks the hash chain |
| `precedents` | One row per decided case | Optional |
| `policy_chunks` | Fixed by the number of policies | Rebuilt with `wealthpilot ingest-policy` |
| `nim_cache` | One row per distinct model call | Safe to empty with `TRUNCATE nim_cache;`. Later calls are served by the provider again |
| `nim_calls` | One row per model call | Safe to empty with `TRUNCATE nim_calls;`. The usage figures start again from zero |
| `nim_bucket` | One row | Do not delete |

## Backup and restore

Back up the database with a logical dump of the whole database, because the case index, the saved states and the audit log refer to each other:

```bash
docker compose exec -T postgres pg_dump -U wealthpilot wealthpilot | gzip > wealthpilot-$(date +%F).sql.gz
```

Replace the user and database name if `POSTGRES_USER` or `POSTGRES_DB` were changed. To restore into an empty database, start only the `postgres` service and load the dump:

```bash
gunzip -c wealthpilot-2026-11-20.sql.gz | docker compose exec -T postgres psql -U wealthpilot wealthpilot
```

After a restore, run `wealthpilot audit-verify` to confirm that the audit chain is intact, see [Command-line interface](../user-guide/cli.md#audit-verify). The `data` volume (uploaded documents, sanctions list, optional demonstration data) is separate from the database and has to be backed up as well if uploaded documents must be kept. See [Operations](../administration/operations.md).

Policy chunks and cache entries can be rebuilt and do not need to be restored. If they are missing, `wealthpilot ingest-policy` recreates the index.

## Useful queries

Run them with `docker compose exec postgres psql -U wealthpilot wealthpilot`.

```sql
-- Latest decisions
SELECT ts, case_id, payload->>'decision' AS decision, payload->>'override' AS override
FROM audit_log WHERE event = 'decision' ORDER BY id DESC LIMIT 20;

-- Cases waiting for a person
SELECT case_id, status, business_label, loan_amount FROM case_runs
WHERE status IN ('awaiting_doc_review', 'awaiting_approval') ORDER BY updated_at;

-- Current model request rate limit
SELECT rpm FROM nim_bucket;  -- null means the configured budget applies

-- Model call failures in the last day
SELECT kind, model, count(*) FROM nim_calls
WHERE NOT ok AND ts > now() - interval '1 day' GROUP BY 1, 2;
```
