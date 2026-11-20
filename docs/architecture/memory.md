# Memory

WealthPilot keeps three kinds of persistent memory, all in the single Postgres database.

| Tier | Scope | Mechanism | Used for |
|---|---|---|---|
| Checkpoints | One case run | Workflow checkpointer in Postgres | Pausing and resuming at the human gates, crash recovery |
| Long-term store | Across cases | Key-value store in Postgres | An applicant's decision history and the record of every decision |
| Similar-case precedents | Across cases | Vector index in Postgres (pgvector) | The "similar past cases" shown to the memo writer |

Table definitions are in the [Database reference](../reference/database.md).

## Checkpoints

The case state is saved after every workflow step. The two human gates, document review and human approval, pause the workflow. The
process can then exit, and a later session resumes the same case run from the saved checkpoint, whether the pause lasts minutes or
days.

Each case run has a thread id. Re-running a finished thread re-enters its saved state, so every new run of a case uses a fresh
thread id. The console and the command-line interface create one automatically.

## Long-term store

| Namespace | Key | Value |
|---|---|---|
| Applicants | A short hash of the owner name and the business name | The applicant's prior decisions: case id, decision, grade and decision time |
| Decisions | Case id | The full final record: recommendation, decision, override flag, approver, grade, default probability and degraded flags |

* At intake, the applicant's prior decisions are loaded into the case state and offered to the memo writer as context.
* At finalization, the decision is written to both namespaces.

!!! warning "History is context, not evidence"
    Prior decisions are passed to the memo writer for context only. They never feed the rule statuses or the decision rule, and
    approver feedback is not fed back into prompts. Doing so could let past human bias drift into future recommendations.

## Similar-case precedents

At finalization, a one-line summary of the case (industry, loan amount, grade and the memo summary) is embedded and stored with its
decision and grade. When it drafts a memo, the workflow asks the policy tool server for up to two similar earlier cases and shows
the model only each case's decision, grade and similarity score. Precedents are informational and cannot change a recommendation.
Cases whose documents were rejected are not added.

## What is not remembered

* Raw prompts and model outputs are not stored as memory. They appear in [traces](observability.md) and in the response cache.
* Protected attributes are kept in the sealed part of the case state and its checkpoint, but are never placed in a prompt while
  redaction is on. The precedents summary is built from the industry, loan amount, grade and the validated memo summary. It has no
  name or address fields, and with redaction on the memo validator rejects any memo that contains identifying details.
