"""Underwrite page: run a synthetic applicant, or submit a new application with your own PDFs."""

from __future__ import annotations

import time

import streamlit as st

from ...config import PROJECT_ROOT
from ...graph.builder import make_input, make_input_from_applicant
from ...synth.render_docs import DOCS_DIR
from .. import forms
from ..common import case_detail, load_snapshot, preflight, start_case

POLICY_DIR = PROJECT_ROOT / "data" / "policies"


def policy_ids() -> list[str]:
    return sorted(p.name for p in POLICY_DIR.iterdir() if (p / "policy.md").exists())


def default_policy_index(ids: list[str]) -> int:
    """Pre-select the conservative `strict` policy (the one the documentation's walkthrough uses) when it exists."""
    return ids.index("strict") if "strict" in ids else 0


def _load_synthetic() -> list[dict]:
    try:
        from ...synth.applicants import load
        return load()
    except FileNotFoundError:
        return []


def _finish(snap: dict | None, thread_id: str) -> None:
    if snap is not None:
        st.session_state["active_thread"] = thread_id
        st.rerun()


def tab_sample() -> None:
    apps = _load_synthetic()
    if not apps:
        st.info("No synthetic applicants yet. Generate them with `uv run python -m wealthpilot.synth.applicants` and `uv run python -m wealthpilot.synth.render_docs`.")
        return
    labels = {a["case_id"]: f"{a['case_id']} · {a['business_name']} — {a['industry']['name']}" for a in apps}
    cid = st.selectbox("Applicant", list(labels), format_func=labels.get, key="sample-case")
    a = next(x for x in apps if x["case_id"] == cid)
    latest = a["statements"][max(a["statements"])]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Loan request", forms.money(a["loan_amount"]))
    c2.metric("Latest revenue", forms.money(latest["revenue"]))
    c3.metric("Years in business", a["years_in_business"])
    c4.metric("Statement years", len(a["statements"]))
    c1, c2, c3 = st.columns(3)
    policy = c1.radio("Credit policy", policy_ids(), index=default_policy_index(policy_ids()), horizontal=True, key="sample-policy")
    variant = c2.radio("Documents", ["clean", "noisy", "scanned"], horizontal=True, key="sample-variant",
                       help="Noisy = messy layouts and label synonyms. Scanned = image-only PDFs read by the vision model.")
    redaction = c3.toggle("Redact the owner's identity", value=True, key="sample-red", help="On: names, address and ZIP are removed from everything the model reads.")
    with st.expander("Download this applicant's documents (to try the upload flow)"):
        d = DOCS_DIR / cid / variant
        for fname, label in (("financials.pdf", "Financial statements"), ("bank_statement.pdf", "Bank statement")):
            f = d / fname
            if f.exists():
                st.download_button(f"⬇️ {label} ({variant})", f.read_bytes(), file_name=f"{cid}-{variant}-{fname}", mime="application/pdf", key=f"dl-{cid}-{variant}-{fname}")
    if st.button("▶ Run underwriting", type="primary", key="sample-run"):
        if preflight():
            thread = f"{cid}-ui-{time.strftime('%H%M%S')}"
            snap = start_case(make_input(a, policy, variant, redaction), thread, {"source": "synthetic", "variant": variant})
            _finish(snap, thread)


def tab_new() -> None:
    st.caption("Enter the application and upload the applicant's financial statements and bank statement as PDFs (text or scanned).")
    st.markdown("##### Business")
    c1, c2 = st.columns(2)
    business = c1.text_input("Business name", key="f-biz")
    owner = c2.text_input("Principal owner (first and last name)", key="f-owner",
                          help="Used for sanctions screening and for redaction. It is never shown to the models while redaction is on.")
    names = [i["name"] for i in forms.INDUSTRY_OPTIONS] + [forms.OTHER_INDUSTRY]
    industry = st.selectbox("Industry", names, key="f-ind")
    if industry == forms.OTHER_INDUSTRY:
        c1, c2 = st.columns([2, 1])
        industry_name = c1.text_input("Industry name", key="f-ind-name", help="Describe the primary activity; the policy agent reads this text (e.g. to apply prohibited-industry rules).")
        naics = c2.text_input("NAICS code (6 digits)", key="f-naics")
    else:
        opt = forms.industry_by_name(industry)
        industry_name, naics = opt["name"], opt["naics"]
        st.caption(f"NAICS {naics}")
    c1, c2, c3 = st.columns(3)
    years = c1.number_input("Years in business", min_value=0.0, max_value=150.0, value=5.0, step=0.5, key="f-years")
    btype = c2.selectbox("Legal form", forms.BUSINESS_TYPES, key="f-btype")
    jobs = c3.number_input("Jobs supported", min_value=0, max_value=5000, value=5, key="f-jobs")
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    street = c1.text_input("Street", key="f-street")
    city = c2.text_input("City", key="f-city")
    state = c3.selectbox("State", forms.STATES, index=forms.STATES.index("OH"), key="f-state")
    zipc = c4.text_input("ZIP", key="f-zip", max_chars=5)
    st.markdown("##### Loan request")
    c1, c2, c3 = st.columns(3)
    loan = c1.number_input("Loan amount ($)", min_value=0.0, value=150_000.0, step=5_000.0, key="f-loan")
    term = c2.number_input("Term (months)", min_value=6, max_value=360, value=84, step=6, key="f-term")
    purpose = c3.selectbox("Purpose", forms.PURPOSE_OPTIONS, key="f-purpose")
    c1, c2, c3, c4 = st.columns(4)
    collateral = c1.number_input("Collateral value ($)", min_value=0.0, value=0.0, step=5_000.0, key="f-coll")
    rate = c2.selectbox("Rate type", list(forms.RATE_TYPES), format_func=forms.RATE_TYPES.get, key="f-rate")
    guarantor = c3.checkbox("Personal guarantee provided", key="f-guar")
    franchise = c4.checkbox("Franchise", key="f-fran")
    st.markdown("##### Documents")
    c1, c2 = st.columns(2)
    fin = c1.file_uploader("Financial statements (PDF)", type=["pdf"], key="f-fin", help="Income statement and balance sheet; one to three fiscal years.")
    bank = c2.file_uploader("Bank statement (PDF)", type=["pdf"], key="f-bank", help="A 12-month summary with opening, deposits, withdrawals and closing balances.")
    c1, c2 = st.columns(2)
    policy = c1.radio("Credit policy", policy_ids(), index=default_policy_index(policy_ids()), horizontal=True, key="f-policy")
    redaction = c2.toggle("Redact the owner's identity", value=True, key="f-red")
    if st.button("▶ Run underwriting", type="primary", key="f-run"):
        form = {"business_name": business, "owner_name": owner, "industry_name": industry_name, "naics": naics, "years_in_business": years, "business_type": btype,
                "jobs_supported": jobs, "street": street, "city": city, "state": state, "zip": zipc, "loan_amount": loan, "term_months": term, "purpose": purpose,
                "collateral_value": collateral, "fixed_or_variable": rate, "guarantor_provided": guarantor, "franchise": franchise}
        errs = forms.validate_application(form)
        if fin is None or bank is None:
            errs.append("Upload both the financial statements and the bank statement.")
        if errs:
            st.error("Please fix:\n" + "\n".join(f"- {e}" for e in errs))
            return
        if not preflight():
            return
        case_id = forms.new_case_id()
        try:
            paths = forms.save_uploads(case_id, fin.getvalue(), bank.getvalue())
        except ValueError as e:
            st.error(str(e))
            return
        thread = f"{case_id}-ui"
        snap = start_case(make_input_from_applicant(forms.build_applicant(form, case_id), policy, paths, redaction), thread, {"source": "upload", "variant": "uploaded"})
        _finish(snap, thread)


def active_case() -> bool:
    """Show the case that was just run (or reopened). Returns True if one is being shown."""
    tid = st.session_state.get("active_thread")
    if not tid:
        return False
    snap = load_snapshot(tid)
    left, right = st.columns([5, 1])
    left.markdown("### Current case")
    if right.button("Dismiss", key="dismiss-active", help="Close this case view (the case stays in the Cases list)."):
        st.session_state.pop("active_thread")
        st.rerun()
    if snap is None:
        st.warning("That case has no saved state.")
        return True
    if case_detail(tid, snap) is not None:
        st.rerun()
    return True


def render() -> None:
    st.title("▶ Underwrite")
    st.caption("Start a case, watch the agents work, then review the evidence and make the decision. Runs take a few minutes on the free model tier; repeating an identical run is served from the cache in seconds.")
    showing = active_case()          # the case under review comes first; the entry form folds away
    with st.expander("Start a new case" if showing else "Start a case", expanded=not showing):
        t1, t2 = st.tabs(["Sample applicants", "New application"])
        with t1:
            tab_sample()
        with t2:
            tab_new()
