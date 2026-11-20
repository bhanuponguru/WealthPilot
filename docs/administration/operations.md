# Operations

Day-to-day running of a WealthPilot installation: starting and stopping, health, backups, upgrades and housekeeping. All commands run from the folder that contains `docker-compose.yml`.

## Starting and stopping

| Task | Command |
|---|---|
| Start everything | `docker compose up -d` |
| Stop, keeping all data | `docker compose down` |
| Restart one service | `docker compose restart <service>` |
| Service state and health | `docker compose ps` |
| Follow a service's log | `docker compose logs -f <service>` |

Services: `postgres`, `ollama`, `mlflow`, `mcp` (the three tool servers), `console`; the one-shot jobs `ollama-pull` and `bootstrap` run at start-up and exit.

!!! danger "`down -v` deletes data"
    `docker compose down -v` removes the volumes: every case, the long-term memory, the audit log, uploaded documents and cached model replies. Use it only to start over.

## Health

* The console sidebar shows a one-line status, and **System > Health** lists each component with the command that fixes it.
* `docker compose exec console wealthpilot doctor` prints the same checks and exits with a non-zero status if something blocks underwriting.
* `docker compose exec console wealthpilot audit-verify` verifies the audit chain and exits non-zero if it is broken.

What to watch:

| Signal | Where | Healthy | Investigate when |
|---|---|---|---|
| Request rate to the model service | System > Model calls | at or near the configured budget | pinned near 6 per minute (the service is throttling) |
| Failed model calls | System > Model calls | few | a rising count for one model |
| Cache hits | System > Model calls | high on repeated work | zero on a repeated case |
| Audit chain | History page, `audit-verify` | intact | any break |
| Cases waiting | Inbox | few | many cases waiting for a decision |
| Failed or interrupted runs | Cases > Needs attention | none | a rising count |
| Degraded runs | case banner | rare | frequent: a tool server is down |

Traces of each run (one trace per case, tagged with case, policy and thread) are in the tracking server. It is reachable inside the Compose network at `http://mlflow:5000`; to browse it from the
host, publish port 5000 in the compose file.

## Backup and restore

All durable state is in the Postgres database (checkpoints, case index, long-term memory, policy vectors, response cache, audit log) plus the `data` volume (uploaded documents, sanctions list). Back up both.

```bash
# database
docker compose exec -T postgres pg_dump -U wealthpilot -Fc wealthpilot > wealthpilot-$(date +%F).dump

# uploaded documents
docker run --rm -v wealthpilot_data:/data -v "$PWD":/backup alpine tar czf /backup/data-$(date +%F).tar.gz -C /data .
```

Restore into a stopped console:

```bash
docker compose stop console mcp
docker compose exec -T postgres pg_restore -U wealthpilot -d wealthpilot --clean --if-exists < wealthpilot-YYYY-MM-DD.dump
docker compose up -d
```

After a restore, run `wealthpilot audit-verify`. The response cache can be omitted from backups: it only saves time and is rebuilt on demand.

## Upgrading

```bash
git pull
docker compose build
docker compose up -d
```

The database schema is created and extended by the application on first use, so no separate migration step is needed. Back up before upgrading. If the credit policies changed, re-index them
(see [Managing credit policies](policies.md)).

## Housekeeping

| Item | Growth | Action |
|---|---|---|
| Uploaded documents (`data` volume) | one folder per case | archive or delete per your retention schedule |
| Case checkpoints and the case index | grow with every run | delete old cases per your retention schedule; keep the audit log |
| Response cache (`nim_cache`) | grows with distinct model calls | `TRUNCATE nim_cache;` at any time |
| Model-call log (`nim_calls`) | one row per call | prune old rows if it grows large |
| Audit log | one row per decision | never prune; anchor its latest hash externally if you need stronger guarantees |

## Refreshing the sanctions list

The OFAC list is downloaded when the stack first starts. Refresh it on a schedule (daily is typical):

```bash
docker compose run --rm bootstrap wealthpilot fetch-ofac --force
docker compose restart mcp
```
