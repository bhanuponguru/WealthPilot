"""Cases page: every underwriting case; open one to review the evidence and record the decision."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...graph import cases
from ..forms import money
from ..common import STATUS_LABEL, friendly_error, load_snapshot, open_case, require_db
from ..runner import manager

GROUPS = {
    "Needs attention": ["awaiting_approval", "awaiting_doc_review", "error", "running"],
    "Decided": ["decided", "finished"],
    "All": list(STATUS_LABEL),
}


def _list() -> None:
    st.title("Cases")
    c1, c2, c3 = st.columns([3, 3, 1], vertical_alignment="bottom")
    group = c1.segmented_control("Show", list(GROUPS), default="Needs attention", key="q-group", label_visibility="collapsed")
    search = c2.text_input("Search by business or case number", key="q-search", placeholder="Search by business or case number", label_visibility="collapsed")
    if c3.button("Refresh", icon=":material/refresh:", key="q-refresh", width="stretch"):
        load_snapshot.clear()
        st.rerun()
    try:
        rows = cases.list_cases(GROUPS[group or "Needs attention"], search)
    except Exception as e:  # noqa: BLE001
        st.error(friendly_error(e))
        return
    if not rows:
        st.info("No cases here." + (" Try the **All** filter." if group != "All" else " Start one from **New case**."))
        return
    active = set(manager().active_threads())
    df = pd.DataFrame(rows)
    status = [("Interrupted" if r["status"] == "running" and r["thread_id"] not in active else STATUS_LABEL[r["status"]]) for r in rows]
    view = pd.DataFrame({
        "Business": df["business_label"], "Case": df["case_id"], "Loan": df["loan_amount"].map(money), "Status": status,
        "Recommendation": df["recommendation"].fillna("").str.upper(), "Grade": df["grade"], "Decision": df["decision"].fillna("").str.upper(),
        "Flag": df["degraded"].map({True: "⚠️ degraded", False: ""}), "Updated": pd.to_datetime(df["updated_at"]).dt.strftime("%Y-%m-%d %H:%M"),
    })
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="q-table")
    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        st.session_state["case_open"] = rows[sel[0]]["thread_id"]
        st.rerun()
    st.caption("Select a row to open the case.")


def render() -> None:
    if not require_db():
        return
    tid = st.session_state.get("case_open")
    if not tid:
        _list()
        return
    if st.button("Back to all cases", icon=":material/arrow_back:", key="q-back"):
        st.session_state.pop("case_open")
        st.rerun()
    open_case(tid)
