# Memory

WealthPilot has three kinds of persistent memory, all in the single Postgres database.

| Tier | Scope | Mechanism | Used for |
|---|---|---|---|
| **Checkpoints** | one case run (`thread_id`) | LangGraph `AsyncPostgresSaver` | pause/resume at human gates, crash recovery |
| **Long-term key-value** | across cases | LangGraph `AsyncPostgresStore` | an applicant's decision history; the record of every decision |
| **Semantic precedents** | across cases | `precedents` table with `pgvector` | "similar past cases" in the memo |

## Checkpoints

After every superstep the graph state is saved. `human_approval` and `doc_review` pause with `interrupt()`; the process may exit, and a new
session resumes the same `thread_id`. Re-running a *finished* thread re-enters its saved state, so use a fresh thread id for each new run.

## Long-term store

| Namespace | Key | Value |
|---|---|---|
| `("applicants",)` | `applicant_id` — a SHA-1 prefix of owner name + business name | `{"decisions": [{case_id, decision, grade, decided_at}, ...]}` |
| `("decisions",)` | `case_id` | the full final record (recommendation, decision, override, approver, grade, PD, degraded flags, …) |

* At **`intake`**, the applicant's prior decisions are loaded into state and offered to the memo writer as context.
* At **`finalize`**, the decision is written to both namespaces.

!!! warning "History is context, not evidence"
    Prior decisions are passed to the memo writer for context only. They never feed the rule statuses or the decision rule, and approver
    feedback is **not** fed back into prompts — doing so could let past human bias drift into future recommendations.

## Semantic precedents

At `finalize`, a one-line summary of the case (`industry, loan amount, grade, memo summary`) is embedded and stored with its decision and grade.
The memo step calls `policydocs.similar_precedents` for up to **two** similar earlier cases and shows only their decision, grade and
similarity score to the model. Precedents are informational: they cannot change a recommendation.

## What is *not* remembered

* Raw prompts and model outputs are not stored as memory (they appear in [traces](observability.md) and the response cache).
* Protected attributes are kept in the sealed part of the case state and checkpoint, but are never placed in a prompt (while redaction is on).
  The precedents summary is built from the industry, loan amount, grade and the validated memo summary — it has no name or address fields, and
  with redaction on the memo validator rejects any memo containing identifying details.
