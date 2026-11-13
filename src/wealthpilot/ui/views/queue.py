"""Cases page: every underwriting run, filterable, with the review and decision screen for the selected case."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...graph import cases
from ..common import STATUS_LABEL, case_detail, friendly_error, load_snapshot, require_db

OPEN_STATUSES = ["awaiting_approval", "awaiting_doc_review"]


def render() -> None:
    st.title("🗂️ Cases")
    st.caption("All underwriting runs. Cases waiting for a human are listed first by default; select a row to review it.")
    if not require_db():
        return
    c1, c2, c3 = st.columns([3, 3, 1])
    chosen = c1.multiselect("Status", list(STATUS_LABEL), default=OPEN_STATUSES, format_func=STATUS_LABEL.get, key="q-status")
    search = c2.text_input("Search (case id, thread or business)", key="q-search")
    if c3.button("↻ Refresh", key="q-refresh"):
        load_snapshot.clear()
        st.rerun()
    try:
        rows = cases.list_cases(chosen or None, search)
    except Exception as e:  # noqa: BLE001
        st.error(friendly_error(e))
        return
    if not rows:
        st.info("No cases match. Start one on the **Underwrite** page, or widen the status filter.")
        return
    df = pd.DataFrame(rows)
    view = pd.DataFrame({
        "Status": df["status"].map(STATUS_LABEL), "Case": df["case_id"], "Business": df["business_label"], "Policy": df["policy_id"],
        "Loan ($)": df["loan_amount"], "Recommendation": df["recommendation"], "Grade": df["grade"], "Decision": df["decision"],
        "Degraded": df["degraded"].map({True: "⚠️", False: ""}), "Updated": pd.to_datetime(df["updated_at"]).dt.strftime("%Y-%m-%d %H:%M"), "Thread": df["thread_id"],
    })
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="q-table",
                      column_config={"Loan ($)": st.column_config.NumberColumn(format="$%d")})
    sel = ev.selection.rows if ev and ev.selection else []
    if not sel:
        st.caption("Select a case above to open it.")
        return
    row = rows[sel[0]]
    if row["status"] == "error":
        st.error(f"This run failed: {row.get('error') or 'unknown error'}")
    thread = row["thread_id"]
    st.divider()
    try:
        snap = load_snapshot(thread)
    except Exception as e:  # noqa: BLE001
        st.error(friendly_error(e))
        return
    if snap is None:
        st.warning("This case has no saved state (it may have failed before the first step).")
        return
    if case_detail(thread, snap) is not None:
        st.rerun()
