"""Inbox: what needs the reviewer's decision, what is still running, and what was decided recently."""

from __future__ import annotations

import streamlit as st

from ... import demo
from ...graph import cases
from .. import nav
from ..common import cached_health, friendly_error, require_db
from ..forms import money
from ..runner import manager

REC_BADGE = {"approve": ("APPROVE", "green"), "decline": ("DECLINE", "red"), "refer": ("REFER", "orange")}
WAITING = ["awaiting_approval", "awaiting_doc_review"]


def _case_card(r: dict, *, key: str, action: str = "Review") -> None:
    rec, color = REC_BADGE.get(r.get("recommendation") or "", ("", "gray"))
    with st.container(border=True):
        left, mid, right = st.columns([5, 3, 1.4], vertical_alignment="center")
        left.markdown(f"**{r['business_label'] or r['case_id']}**")
        left.caption(f"{money(r['loan_amount'])} · case {r['case_id']} · policy {r['policy_id']}")
        if r["status"] == "awaiting_doc_review":
            mid.badge("Documents need checking", color="orange", icon=":material/description:")
        elif rec:
            mid.badge(f"Recommends {rec.title()}" + (f" · grade {r['grade']}" if r.get("grade") else ""), color=color)
        if right.button(action, key=key, width="stretch"):
            nav.open_in_cases(r["thread_id"])


def render() -> None:
    top_l, top_r = st.columns([4, 1], vertical_alignment="center")
    top_l.title("Inbox")
    if top_r.button("New case", icon=":material/add_circle:", type="primary", width="stretch", key="inbox-new"):
        nav.go("new-case")

    problems = [c for c in cached_health() if not c.ok and c.required]
    if problems:
        st.error("Underwriting is unavailable right now: " + ", ".join(f"**{c.name}**" for c in problems) + " not ready.")
        if st.button("See how to fix this", key="inbox-fix"):
            nav.go("system")

    if not require_db():
        return
    try:
        waiting = cases.list_cases(WAITING, limit=50)
        running = cases.list_cases(["running"], limit=50)
        failed = cases.list_cases(["error"], limit=20)
        decided = cases.list_cases(["decided", "finished"], limit=5)
    except Exception as e:  # noqa: BLE001
        st.warning(friendly_error(e))
        return

    if not (waiting or running or failed or decided):
        st.info("No cases yet.")
        st.markdown("**Get started:** open **New case**, enter an application and upload the applicant's financial statements and bank statement as PDFs. "
                    "The assistant reads them, applies your credit policy, researches the borrower and drafts a credit memo. "
                    "Then it stops and waits for **your** decision.")
        if demo.enabled():
            st.caption("No application to hand? **New case → Try a sample applicant** runs one of the demonstration applicants.")
        return

    st.subheader(f"Needs your decision ({len(waiting)})")
    if waiting:
        for r in waiting:
            _case_card(r, key=f"inbox-{r['thread_id']}")
    else:
        st.caption("Nothing is waiting for you.")

    if failed or running:
        active = set(manager().active_threads())
        st.subheader("In progress")
        for r in running:
            interrupted = r["thread_id"] not in active
            with st.container(border=True):
                left, mid, right = st.columns([5, 3, 1.4], vertical_alignment="center")
                left.markdown(f"**{r['business_label'] or r['case_id']}**")
                left.caption(f"{money(r['loan_amount'])} · case {r['case_id']}")
                mid.badge("Interrupted" if interrupted else "Working…", color="orange" if interrupted else "blue")
                if right.button("Open", key=f"run-{r['thread_id']}", width="stretch"):
                    nav.open_in_cases(r["thread_id"])
        for r in failed:
            with st.container(border=True):
                left, mid, right = st.columns([5, 3, 1.4], vertical_alignment="center")
                left.markdown(f"**{r['business_label'] or r['case_id']}**")
                left.caption(f"{money(r['loan_amount'])} · case {r['case_id']}")
                mid.badge("Stopped with an error", color="red")
                if right.button("Open", key=f"err-{r['thread_id']}", width="stretch"):
                    nav.open_in_cases(r["thread_id"])

    if decided:
        st.subheader("Recently decided")
        for r in decided:
            d = (r.get("decision") or "").lower()
            with st.container(border=True):
                left, mid, right = st.columns([5, 3, 1.4], vertical_alignment="center")
                left.markdown(f"**{r['business_label'] or r['case_id']}**")
                left.caption(f"{money(r['loan_amount'])} · case {r['case_id']} · {r['updated_at']:%Y-%m-%d %H:%M}")
                mid.badge(d.title() or "Finished", color=REC_BADGE.get(d, ("", "gray"))[1])
                if right.button("View", key=f"done-{r['thread_id']}", width="stretch"):
                    nav.open_in_cases(r["thread_id"])
