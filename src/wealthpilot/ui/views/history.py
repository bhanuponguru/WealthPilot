"""History page: the decision log and the tamper-evident audit chain."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...compliance import audit
from ...nim.store import pool
from ..common import friendly_error, require_db


def _load(limit: int) -> list[tuple]:
    with pool().connection() as c:
        audit._init(c)
        return c.execute("SELECT id, ts, case_id, event, payload, hash FROM audit_log ORDER BY id DESC LIMIT %s", (limit,)).fetchall()


def render() -> None:
    st.title("📜 History and audit")
    st.caption("Every decision is appended to a hash-chained log: each record contains the hash of the one before it, so editing or deleting history is detectable.")
    if not require_db():
        return
    try:
        ver = audit.verify()
        rows = _load(2000)
    except Exception as e:  # noqa: BLE001
        st.error(friendly_error(e))
        return
    if ver["ok"]:
        st.success(f"✅ Audit chain intact — {ver['records']} records verified.")
    else:
        st.error(f"🛑 The audit chain is BROKEN at record {ver['first_bad_id']}. Records from there on cannot be trusted.")
    if not rows:
        st.info("No decisions recorded yet.")
        return
    df = pd.DataFrame([{"ID": r[0], "Time": r[1], "Case": r[2], "Event": r[3], "Recommendation": r[4].get("recommendation"), "Decision": r[4].get("decision"),
                        "Override": bool(r[4].get("override")), "Grade": r[4].get("grade"), "Approver": r[4].get("approver"), "Tier": r[4].get("approver_tier"),
                        "Degraded": bool(r[4].get("degraded"))} for r in rows])
    dec = df[df["Event"] == "decision"]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Decisions", len(dec))
    for col, name in ((c2, "approve"), (c3, "decline"), (c4, "refer")):
        col.metric(name.title(), int((dec["Decision"] == name).sum()))
    c5.metric("Overrides", int(dec["Override"].sum()), help="Human decision contradicted the system's recommendation.")
    f1, f2, f3 = st.columns(3)
    case = f1.text_input("Case id contains", key="h-case")
    decisions = f2.multiselect("Decision", sorted(dec["Decision"].dropna().unique()), key="h-dec")
    only_over = f3.checkbox("Overrides only", key="h-over")
    view = df
    if case:
        view = view[view["Case"].str.contains(case, case=False, na=False)]
    if decisions:
        view = view[view["Decision"].isin(decisions)]
    if only_over:
        view = view[view["Override"]]
    ev = st.dataframe(view, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="h-table")
    st.download_button("⬇️ Download as CSV", view.to_csv(index=False), file_name="decisions.csv", mime="text/csv")
    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        rid = int(view.iloc[sel[0]]["ID"])
        row = next(r for r in rows if r[0] == rid)
        st.markdown(f"##### Record {rid}")
        st.caption(f"hash `{row[5][:16]}…`")
        st.json(row[4])
