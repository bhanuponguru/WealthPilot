# Troubleshooting

Start with the diagnosis commands, then look for the symptom below.

## Quick diagnosis

```bash
docker compose ps                                   # state and health of every service
docker compose exec console wealthpilot doctor      # checks each dependency and prints the fix for anything missing
docker compose logs --tail 50 mcp                   # recent output of the tool servers (also: console, mlflow, postgres)
docker compose exec console wealthpilot audit-verify
```

The same checks appear in the console: the sidebar shows a one-line service status, and **System > Health** lists every component with the command that fixes it.

## Start-up problems

??? failure "The console container keeps waiting, or `mcp` is unhealthy"
    The tool servers start only after the database is healthy, the embedding model has been pulled and the first-start preparation has finished. The first start downloads the embedding model and
    indexes the credit policies, which can take a few minutes. Follow `docker compose logs -f ollama-pull bootstrap mcp`.

??? failure "`bootstrap` reports that the sanctions list could not be fetched"
    The container needs internet access on first start to download the OFAC list. Start still proceeds; screening finds no matches until the list exists. Run `docker compose run --rm bootstrap`
    once connectivity is available, and restart `mcp`.

??? failure "Everything is up but runs fail with an API key error"
    No key reached the containers. Export `NVIDIA_API_KEY` (or `NVIDIA_NIM_API_KEY`) in the shell that runs Compose, or put it in a `.env` file next to `docker-compose.yml`, then run
    `docker compose up -d`. A blank value is treated as missing.

??? failure "Port already in use"
    Another process holds 8501 or 5432. Set `CONSOLE_PORT` or `POSTGRES_PORT` in `.env`, or stop the other process.

??? failure "Out of memory, services restarting"
    The stack needs roughly 4 GB of memory. The tool-server container (which loads the risk model and the retrieval stack) is the largest consumer. Close other workloads or raise the memory available to Docker.

## Console problems

??? failure "A page says the database is not reachable"
    Check `docker compose ps postgres`. After the database is healthy, press **R** in the browser.

??? failure "**Run underwriting** shows a red message"
    A pre-run check found a missing dependency (embeddings, model API key or risk model) and shows the fix. Resolve it and submit again.

??? warning "An orange warning says the run will be degraded"
    The tool servers are not reachable. The run is allowed to proceed but its recommendation is capped at *refer*. Restore them with `docker compose up -d mcp`.

??? question "A case I started is not listed under Needs attention"
    That filter shows cases waiting for a person, running, or failed. A decided case is under **Decided**; **All** shows every case.

??? failure "A case shows *Stopped (error)* or *Interrupted*"
    Open it in **Cases**. The message states what failed (usually a missing service). Fix that and press **Continue the run**; the run resumes from its last saved step.

??? failure "Upload rejected"
    The message names the reason: not a readable PDF, empty, over 25 MB, or over 40 pages. For a scanned PDF above the limit, reduce its resolution.

??? question "The decision form says to enter a name or id"
    Fill in **Signed in as** in the sidebar once per browser session; the form is pre-filled from it.

??? question "I changed code or settings and the console shows the old behaviour"
    Restart the service: `docker compose restart console` (or `mcp`). A running server keeps loaded modules and configuration until it restarts.

## Model service problems

??? failure "Runs are very slow, or many calls fail with 429"
    The model service throttles per model and per key. The gateway slows itself down automatically; **System > Model calls** shows the current request rate, and a value near 6 per minute means the service is throttling.
    Wait for it to recover, lower `NIM_RPM_BUDGET`, avoid running several large jobs at once, and rely on the response cache for repeated work.

??? failure "404 Not Found or 410 Gone for a model"
    The model is not available to your account. Choose another with `CHAT_MODEL` (see [Configuration](../get-started/configuration.md)). A model that answers a trivial prompt may still fail on tool calls or
    long structured outputs, so test a real case after changing it.

??? failure "Empty replies or invalid JSON from the model"
    Some models return nothing, or degrade on long structured output, under load. The gateway retries and never caches empty replies. If a model keeps failing, switch `CHAT_MODEL`.

??? failure "Calls time out"
    The per-request limit is `NIM_TIMEOUT_S` (45 seconds by default). Long extractions on a throttled model can exceed it; increase it or retry later.

## Behaviour that looks wrong but is not

??? question "The case paused at document review"
    The extracted figures failed the consistency checks even after an automatic repair, so a person must accept, correct or reject them. This is more frequent with scanned documents.

??? question "The recommendation is *refer* although every rule passed"
    Either the run was degraded (a tool or check was unavailable) or a rule ended as an exception or with missing data. Open the case: a banner lists the degradation reasons, and the Policy checklist shows each status.

??? question "A case was declined that I expected to be approved"
    The decision rule declines when any rule fails. Read the Policy checklist and compare the quoted evidence with the policy text. If a status is wrong, the model misread the rule: record your own decision
    and consider rewording the rule (see [Managing credit policies](policies.md)).

??? question "The first run of a case takes minutes and a repeat takes seconds"
    Repeats are served from the response cache. Changing the prompt, the policy or the model produces fresh calls.

??? failure "`audit-verify` reports `ok: false`"
    A record of the audit log was edited or deleted. The report names the first inconsistent record. Restore the database from a backup taken before the change.

## Resetting

| Symptom | Action |
|---|---|
| Stale or unwanted cached model replies | `docker compose exec postgres psql -U wealthpilot -c "TRUNCATE nim_cache;"` |
| Request rate stuck low | **System > Model calls > Reset the rate limiter** |
| Policy search out of date after editing a policy | `docker compose exec console wealthpilot ingest-policy`, then `docker compose restart mcp console` |
| A service in a bad state | `docker compose restart <service>` |
| Start over, **deleting all cases, memory and the audit log** | `docker compose down -v`, then `docker compose up -d` |
