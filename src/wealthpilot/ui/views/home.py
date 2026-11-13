"""Overview page: are the services up, what is waiting for me, and where do I start."""

from __future__ import annotations

import streamlit as st

from ...graph import cases
from ..common import STATUS_LABEL, cached_health, friendly_error, require_db


def render() -> None:
    st.title("📊 WealthPilot")
    st.markdown("**A multi-agent assistant for SME loan underwriting.** It reads the applicant's documents, applies your credit policy exactly as written, "
                "checks its own numbers, drafts a credit memo — and then **stops for a human decision**.")

    checks = cached_health()
    required_bad = [c for c in checks if not c.ok and c.required]
    if required_bad:
        st.error("Some services need attention before you can underwrite: " + ", ".join(f"**{c.name}**" for c in required_bad) + ". See the **System** page for the fix commands.")
    else:
        st.success("All required services are running.")

    st.markdown("#### What needs you")
    if not require_db():
        return
    try:
        counts = cases.counts()
    except Exception as e:  # noqa: BLE001
        st.warning(friendly_error(e))
        counts = {}
    cols = st.columns(4)
    cols[0].metric(STATUS_LABEL["awaiting_approval"], counts.get("awaiting_approval", 0))
    cols[1].metric(STATUS_LABEL["awaiting_doc_review"], counts.get("awaiting_doc_review", 0))
    cols[2].metric(STATUS_LABEL["decided"], counts.get("decided", 0))
    cols[3].metric(STATUS_LABEL["error"], counts.get("error", 0))
    waiting = counts.get("awaiting_approval", 0) + counts.get("awaiting_doc_review", 0)
    if waiting:
        st.info(f"**{waiting} case(s)** are waiting for a human. Open the **Cases** page to review them.")
        try:
            recent = cases.list_cases(["awaiting_approval", "awaiting_doc_review"], limit=5)
            for r in recent:
                st.markdown(f"- `{r['case_id']}` · {r['business_label']} · {STATUS_LABEL[r['status']]} · recommendation **{(r['recommendation'] or '—').upper()}**")
        except Exception:  # noqa: BLE001
            pass

    st.markdown("#### How it works")
    a, b, c = st.columns(3)
    a.markdown("**1 · Underwrite**\n\nChoose a sample applicant or enter a new application with PDF statements. The agents parse the documents, compute ratios, "
               "screen the borrower, score risk and apply the policy.")
    b.markdown("**2 · Review**\n\nOpen the case: read the memo, the policy checklist with quoted evidence, the financials and the risk factors. "
               "Anything the system was unsure of is flagged.")
    c.markdown("**3 · Decide**\n\nApprove, decline or ask for a revision. You need the authority tier the policy requires, and every decision "
               "is written to a tamper-evident audit log.")
    st.markdown("#### Pages")
    st.caption("**Underwrite** start a case · **Cases** review and decide · **History** audit trail · **Policies** read the rules and test retrieval · "
               "**Results** the experiments · **System** diagnostics")
