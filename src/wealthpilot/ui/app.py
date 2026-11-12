"""Streamlit approval console.  Run: uv run streamlit run src/wealthpilot/ui/app.py
(needs: docker compose up -d postgres, the MCP servers (`uv run wealthpilot mcp-up`), and a NIM key)."""

from __future__ import annotations

import asyncio

import pandas as pd
import streamlit as st

from wealthpilot.compliance import audit
from wealthpilot.graph.builder import make_input, session
from wealthpilot.nim.store import pool
from wealthpilot.synth.applicants import load

st.set_page_config(page_title="WealthPilot", page_icon="📊", layout="wide")
TIERS = ["Analyst", "Senior Credit Officer", "Credit Committee"]
STATUS_ICON = {"pass": "✅", "fail": "❌", "exception": "⚠️", "not_applicable": "➖", "missing_data": "❓"}


def run_async(coro):
    return asyncio.run(coro)


async def _start(rec, policy, variant, redaction, thread, on_update):
    async with session() as runner:
        return await runner.start(make_input(rec, policy, variant, redaction), thread, on_update)


async def _resume(thread, value):
    async with session() as runner:
        return await runner.resume(thread, value)


async def _snapshot(thread):
    async with session() as runner:
        return await runner.snapshot(thread)


def render_case(snap: dict) -> None:
    v = snap["values"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommendation", (v.get("recommendation") or "—").upper())
    c2.metric("Risk grade", (v.get("grade") or {}).get("grade", "—"))
    c3.metric("5-yr PD", f"{(v.get('risk') or {}).get('pd', 0):.1%}" if v.get("risk") else "—")
    c4.metric("Required approver", v.get("required_tier") or "—")
    if v.get("degraded"):
        st.warning("⚠️ DEGRADED RUN — some tools were unavailable; the recommendation is capped at REFER. " + "; ".join(v.get("degraded_reasons") or []))
    if v.get("validator_issues"):
        st.error("Memo validator issues: " + "; ".join(v["validator_issues"]))
    t_memo, t_ratios, t_risk, t_policy, t_research, t_trace = st.tabs(["Memo", "Ratios", "Risk (SHAP)", "Policy checklist", "Research", "Trace"])
    with t_memo:
        m = v.get("memo") or {}
        st.write(m.get("summary", ""))
        for title, key in (("Strengths", "strengths"), ("Concerns", "concerns"), ("Conditions", "conditions"), ("Limitations", "limitations")):
            if m.get(key):
                st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in m[key]))
        if m.get("adverse_action_reasons"):
            st.markdown("**Adverse-action reasons**\n" + "\n".join(f"- ({r.get('rule_id')}) {r.get('reason')}" for r in m["adverse_action_reasons"]))
    with t_ratios:
        st.json(v.get("ratios") or {})
        st.write((v.get("analysis") or {}).get("narrative", ""))
    with t_risk:
        rk = v.get("risk") or {}
        if rk.get("reasons"):
            st.bar_chart(pd.DataFrame(rk["reasons"]).set_index("reason")["shap"])
        st.caption(f"model {rk.get('model_version')} · band {rk.get('pd_band')}")
    with t_policy:
        rows = [{"": STATUS_ICON.get(c["status"], ""), "rule": c["rule_id"], "title": c.get("title"), "status": c["status"], "reason": c.get("reason"),
                 "evidence": c.get("evidence"), "citation": c.get("citation")} for c in v.get("policy_checks", [])]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    with t_research:
        st.json(v.get("research") or {})
    with t_trace:
        st.dataframe(pd.DataFrame(v.get("trace", [])), width="stretch", hide_index=True)


st.title("📊 WealthPilot — SME loan underwriting")
tab_case, tab_hist = st.tabs(["Case console", "Decision history & audit"])

with tab_case:
    apps = load()
    with st.sidebar:
        st.header("New case")
        cid = st.selectbox("Applicant case", [a["case_id"] for a in apps])
        policy = st.radio("Credit policy", ["strict", "lenient"], horizontal=True)
        variant = st.radio("Documents", ["clean", "noisy", "scanned"], horizontal=True)
        redaction = st.toggle("Redact protected attributes", value=True)
        go = st.button("Run underwriting", type="primary", width="stretch")
    if go:
        rec = next(a for a in apps if a["case_id"] == cid)
        thread = f"{cid}-ui-{pd.Timestamp.now().strftime('%H%M%S')}"
        st.session_state["thread"] = thread
        with st.status("Running agents…", expanded=True) as status:
            snap = run_async(_start(rec, policy, variant, redaction, thread, lambda ev: status.write("✓ " + ", ".join(k for k in ev if k != "__interrupt__"))))
            status.update(label="Paused for human review" if snap["interrupt"] else "Finished", state="complete")
        st.session_state["snap"] = snap
    snap = st.session_state.get("snap")
    if snap:
        render_case(snap)
        intr = snap.get("interrupt")
        if intr and intr.get("type") == "approval":
            st.divider()
            st.subheader("Human decision")
            if intr.get("error"):
                st.error(intr["error"])
            with st.form("approval"):
                decision = st.radio("Decision", ["approve", "decline", "revise"], horizontal=True)
                tier = st.selectbox("Your authority tier", TIERS, index=TIERS.index(intr.get("required_tier") or "Credit Committee"))
                approver = st.text_input("Approver id", "analyst-1")
                reason = st.text_area("Reason / comments (required for override or revise)")
                if st.form_submit_button("Submit decision"):
                    st.session_state["snap"] = run_async(_resume(st.session_state["thread"], {"decision": decision, "approver_tier": tier, "approver_id": approver, "reason": reason}))
                    st.rerun()
        elif intr and intr.get("type") == "doc_review":
            st.warning("Document problems need review")
            st.json({"reconciliation_issues": intr.get("reconciliation_issues"), "bank_issues": intr.get("bank_issues")})
            act = st.radio("Action", ["accept", "reject"], horizontal=True)
            if st.button("Submit document review"):
                st.session_state["snap"] = run_async(_resume(st.session_state["thread"], {"action": act}))
                st.rerun()
        elif snap.get("done") and snap["values"].get("final"):
            st.success("Decision recorded")
            st.json(snap["values"]["final"])

with tab_hist:
    ver = audit.verify()
    st.success(f"Audit chain intact ({ver['records']} records)") if ver["ok"] else st.error(f"Audit chain BROKEN at record {ver['first_bad_id']}")
    with pool().connection() as c:
        rows = c.execute("SELECT ts, case_id, event, payload FROM audit_log ORDER BY id DESC LIMIT 50").fetchall()
    st.dataframe(pd.DataFrame([{"time": r[0], "case": r[1], "event": r[2], "decision": r[3].get("decision"), "recommendation": r[3].get("recommendation"),
                                "override": r[3].get("override"), "grade": r[3].get("grade")} for r in rows]), width="stretch", hide_index=True)
