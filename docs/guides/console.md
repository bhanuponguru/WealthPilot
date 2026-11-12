# Approval console

A [Streamlit](https://streamlit.io/) app for reviewing evidence and recording decisions (`src/wealthpilot/ui/app.py`).

```bash
uv run streamlit run src/wealthpilot/ui/app.py        # http://localhost:8501
```

Requires Postgres, the MCP servers, Ollama and a NIM key (the same as `wealthpilot run`).

## Case console tab

**Sidebar — new case**

| Control | Meaning |
|---|---|
| Applicant case | which synthetic applicant (`C001`…) |
| Credit policy | `strict` or `lenient` |
| Documents | `clean`, `noisy` or `scanned` |
| Redact protected attributes | on by default; off lets the model see identity details |
| **Run underwriting** | starts the graph; a live status box lists each node as it completes |

**Header metrics:** the recommendation, risk grade, 5-year PD and required approver. A yellow banner appears if the run is **degraded**, and a red one
shows memo-validator issues.

**Evidence tabs**

| Tab | Shows |
|---|---|
| Memo | summary, strengths, concerns, conditions, limitations and adverse-action reasons |
| Ratios | the computed ratios and the analyst's narrative |
| Risk (SHAP) | a bar chart of the top risk-increasing factors, with model version and PD band |
| Policy checklist | every rule with its status, reason, quoted evidence and citation (`policy/rule`) |
| Research | sanctions status, adverse-media severity and summary, registry and sector rate |
| Trace | the step log with node timings |

**Human decision form** (appears when the graph is waiting at the approval gate):

* choose *approve*, *decline* or *revise*;
* choose **your authority tier** — the default is the required tier; a lower one is rejected with an explanation;
* enter your approver id and a reason (needed to explain an override or a revision).

If the graph is waiting at **document review** instead, the page shows the reconciliation issues and lets you *accept* or *reject* the documents.

When the case is finished, the final record is displayed.

## Decision history tab

Shows whether the **audit chain is intact** (a green banner, or a red one naming the first broken record) and the 50 most recent audit
entries: time, case, event, recommendation, decision, override flag and grade.

## Notes

* Each *Run underwriting* click starts a new thread named `<case>-ui-<time>`.
* The console opens a fresh session for each action, so it is safe to stop and restart the app while a case is paused — the paused state is in Postgres.
* Streamlit blocks while a run is in progress; a first run takes a few minutes on the free tier.
