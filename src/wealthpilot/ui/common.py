"""Shared pieces of the Streamlit console: async bridge, health, progress streaming and the reusable case-detail view."""

from __future__ import annotations

import asyncio
import time

import pandas as pd
import streamlit as st

from .. import health
from ..graph import cases
from ..graph.builder import readonly_session, session
from .forms import TIERS, evidence_json, memo_to_markdown, money

RULE_ICON = {"pass": "✅", "fail": "❌", "exception": "⚠️", "not_applicable": "➖", "missing_data": "❓"}
STATUS_LABEL = {
    "running": "⏳ Running", "awaiting_doc_review": "📄 Awaiting document review", "awaiting_approval": "🧑‍⚖️ Awaiting approval",
    "decided": "✅ Decided", "finished": "✔️ Finished", "error": "🛑 Error",
}
REC_COLOR = {"approve": "green", "decline": "red", "refer": "orange"}
NODE_LABEL = {
    "intake": "Checked the application", "parse": "Read and verified the documents", "doc_review": "Document review requested",
    "analyst": "Computed ratios and stress test", "analyst_retry": "Recomputed ratios with prior-year fill", "research": "Screened sanctions, media and registry",
    "risk": "Scored default risk", "policy": "Applied credit-policy rules CP-1…CP-11", "grade": "Computed scorecard and risk grade",
    "policy2": "Applied CP-12 and chose the approver tier", "memo": "Drafted the credit memo", "memo_validator": "Validated the memo",
    "human_approval": "Waiting for a human decision", "finalize": "Recorded the decision",
}


# --------------------------------------------------------------------------- async bridge
def run_async(coro):
    """Streamlit scripts are synchronous; each action opens its own event loop and its own graph session."""
    return asyncio.run(coro)


async def _snapshot(thread_id: str) -> dict:
    async with readonly_session() as runner:
        return await runner.snapshot(thread_id)


async def _start(state_in: dict, thread_id: str, meta: dict, on_update):
    async with session() as runner:
        return await runner.start(state_in, thread_id, on_update, meta)


async def _resume(thread_id: str, value: dict):
    async with session() as runner:
        return await runner.resume(thread_id, value)


@st.cache_data(ttl=3, show_spinner=False)
def load_snapshot(thread_id: str) -> dict | None:
    """Saved state of a case thread (cheap, read-only). ``None`` if the thread has no saved state."""
    snap = run_async(_snapshot(thread_id))
    return snap if snap["values"] else None


def friendly_error(e: Exception) -> str:
    """Translate a low-level failure into what the user should do."""
    name, text = type(e).__name__, str(e)
    if "5432" in text or "OperationalError" in name or "PoolTimeout" in name or "connection failed" in text.lower():
        return "Postgres is not reachable. Start it with `docker compose up -d postgres`."
    if "NVIDIA API key" in text:
        return "No NVIDIA NIM key found. Export `NVIDIA_NIM_API_KEY` or set `NVIDIA_API_KEY` in `.env`, then restart the console."
    if "11434" in text or "ollama" in text.lower():
        return "Ollama is not reachable or the embedding model is missing. Run `ollama serve` and `ollama pull nomic-embed-text`."
    return f"{name}: {text[:300]}"


def show_table(df: pd.DataFrame, *, max_height: int = 640, **kwargs):
    """`st.dataframe` sized to its rows (up to `max_height`), so short tables are shown in full instead of scrolling inside a box."""
    kwargs.setdefault("width", "stretch")
    kwargs.setdefault("hide_index", True)
    return st.dataframe(df, height=min(max_height, 35 * (len(df) + 1) + 3), **kwargs)


# --------------------------------------------------------------------------- health
@st.cache_data(ttl=5, show_spinner=False)
def cached_health() -> list[health.Check]:
    return health.run_all()


def require_db() -> bool:
    """True if Postgres is reachable. Otherwise show the fix and return False, so a page never waits on a dead connection."""
    pg = next((c for c in cached_health() if c.name == "Postgres"), None)
    if pg is not None and not pg.ok:
        st.error(f"**Postgres is not reachable.** Start it with `{pg.fix}`, then press **R** to rerun.")
        return False
    return True


def preflight() -> bool:
    """Show blocking problems and return False if a run cannot work at all; warn (but allow) if the MCP servers are down."""
    checks = cached_health()
    bad = health.blocking(checks)
    for c in bad:
        st.error(f"**{c.name}:** {c.detail}.  Fix: `{c.fix}`")
    mcp_down = [c.name for c in checks if c.name.startswith("MCP") and not c.ok]
    if mcp_down and not bad:
        st.warning(f"{', '.join(mcp_down)} not reachable — the run will complete **degraded** (recommendation capped at REFER). Start them with `uv run wealthpilot mcp-up`.")
    return not bad


# --------------------------------------------------------------------------- running and resuming
def start_case(state_in: dict, thread_id: str, meta: dict) -> dict | None:
    """Run a case with live progress. Returns the final snapshot or None on failure."""
    t0 = time.time()
    with st.status("Running the underwriting agents…", expanded=True) as status:
        def on_update(ev: dict) -> None:
            for node in (k for k in ev if k != "__interrupt__"):
                status.write(f"✓ {NODE_LABEL.get(node, node)}  · {time.time() - t0:.0f}s")
        try:
            snap = run_async(_start(state_in, thread_id, meta, on_update))
        except Exception as e:  # noqa: BLE001
            status.update(label="The run failed", state="error")
            st.error(friendly_error(e))
            return None
        status.update(label="Paused for a human" if snap["interrupt"] else "Finished", state="complete")
    load_snapshot.clear()
    return snap


def resume_case(thread_id: str, value: dict) -> dict | None:
    with st.spinner("Recording the decision…"):
        try:
            snap = run_async(_resume(thread_id, value))
        except Exception as e:  # noqa: BLE001
            st.error(friendly_error(e))
            return None
    load_snapshot.clear()
    return snap


# --------------------------------------------------------------------------- case detail
def case_header(thread_id: str, v: dict, status: str) -> None:
    app = v.get("application") or {}
    st.subheader(f"{app.get('business_label', v.get('case_id', thread_id))}")
    st.caption(f"Case `{v.get('case_id')}` · thread `{thread_id}` · policy **{v.get('policy_id')}** · {STATUS_LABEL.get(status, status)} · "
               f"{money(app.get('loan_amount'))} over {app.get('term_months', '—')} months")
    c1, c2, c3, c4 = st.columns(4)
    rec = v.get("recommendation")
    c1.metric("Recommendation", (rec or "—").upper())
    c2.metric("Risk grade", (v.get("grade") or {}).get("grade", "—"))
    pd_ = (v.get("risk") or {}).get("pd")
    c3.metric("5-year default probability", f"{pd_:.1%}" if pd_ is not None else "—")
    c4.caption("Required approver")           # a metric tile truncates long tier names; plain text wraps instead
    c4.markdown(f"##### {v.get('required_tier') or '—'}")
    if v.get("degraded"):
        st.warning("**Degraded run** — some tools or checks were unavailable, so the recommendation is capped at REFER. " + "; ".join(v.get("degraded_reasons") or []))
    if v.get("validator_issues"):
        st.error("The memo validator found problems: " + "; ".join(v["validator_issues"]))
    if (v.get("doc_review") or {}).get("action") == "reject":
        st.error("The documents were rejected during review; the case was closed without a recommendation.")


def tab_memo(v: dict) -> None:
    m = v.get("memo") or {}
    if not m:
        st.info("No memo has been generated yet.")
        return
    st.markdown(m.get("summary", ""))
    left, right = st.columns(2)
    for col, title, key in ((left, "Strengths", "strengths"), (right, "Concerns", "concerns")):
        with col:
            if m.get(key):
                st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in m[key]))
    for title, key in (("Conditions", "conditions"), ("Limitations", "limitations")):
        if m.get(key):
            st.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in m[key]))
    if m.get("adverse_action_reasons"):
        st.markdown("**Adverse-action reasons**\n" + "\n".join(f"- *({r.get('rule_id')})* {r.get('reason')}" for r in m["adverse_action_reasons"]))


def tab_policy(v: dict) -> None:
    checks = v.get("policy_checks") or []
    if not checks:
        st.info("The policy rules have not been evaluated yet.")
        return
    counts = pd.Series([c["status"] for c in checks]).value_counts()
    st.caption("  ·  ".join(f"{RULE_ICON.get(k, '')} {k.replace('_', ' ')}: {n}" for k, n in counts.items()))
    df = pd.DataFrame([{"": RULE_ICON.get(c["status"], ""), "Rule": c["rule_id"], "Title": c.get("title"), "Status": c["status"].replace("_", " "),
                        "Reason": c.get("reason"), "Policy threshold read": c.get("extracted_threshold"), "Numeric check": c.get("numeric_check"),
                        "Citation": c.get("citation")} for c in checks])
    show_table(df)
    with st.expander("Evidence quoted from the policy text"):
        for c in checks:
            st.markdown(f"**{c['rule_id']} · {c.get('title', '')}** — {RULE_ICON.get(c['status'], '')} {c['status'].replace('_', ' ')}")
            st.caption(c.get("evidence") or "—")


def tab_financials(v: dict) -> None:
    ext = v.get("extracted") or {}
    if ext:
        st.markdown("**Extracted statements** (verified by reconciliation)")
        show_table(pd.DataFrame(ext).sort_index(axis=1), hide_index=False, max_height=760)
    issues = v.get("reconciliation_issues") or []
    if issues:
        st.warning("Reconciliation issues: " + "; ".join(f"FY{i.get('year', '?')} {i.get('check')}" for i in issues))
    elif ext:
        st.success("All consistency checks passed (balance sheet balances, net income ties).")
    r = v.get("ratios")
    if r:
        st.markdown("**Ratios** (most recent fiscal year)")
        th = v.get("thresholds") or {}
        rows = [("DSCR", r.get("dscr"), th.get("min_dscr"), "≥"), ("Debt-to-equity", r.get("debt_to_equity"), th.get("max_debt_to_equity"), "≤"),
                ("Current ratio", r.get("current_ratio"), th.get("min_current_ratio"), "≥"), ("Loan-to-revenue", r.get("loan_to_revenue"), None, ""),
                ("Collateral coverage", r.get("collateral_coverage"), None, ""), ("Gross margin", r.get("gross_margin"), None, ""), ("Net margin", r.get("net_margin"), None, "")]
        show_table(pd.DataFrame([{"Ratio": n, "Value": val, "Policy limit read": f"{op} {t}" if t is not None else "—"} for n, val, t, op in rows]))
    an = v.get("analysis") or {}
    if an.get("narrative"):
        st.markdown(f"**Analyst narrative:** {an['narrative']}")
    if an.get("stress"):
        st.caption(f"Stress test: a {an['stress'].get('revenue_drop', 0):.0%} revenue drop gives a DSCR of {an['stress'].get('stressed_dscr')}.")
    if an.get("estimated_fields"):
        st.warning("Some figures were estimated from the prior year: " + "; ".join(an["estimated_fields"]))
    bank = (v.get("bank") or {}).get("months")
    if bank:
        st.markdown("**Bank statement** (12-month summary)")
        b = pd.DataFrame(bank)
        st.line_chart(b.set_index("month")[["closing"]])
        if v.get("bank_issues"):
            st.warning(f"Bank roll-forward issues: {len(v['bank_issues'])}")


def tab_risk(v: dict) -> None:
    rk, g = v.get("risk") or {}, v.get("grade") or {}
    if not rk:
        st.info("Risk has not been scored yet.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Probability of default (5 yr)", f"{rk.get('pd', 0):.2%}")
    c2.metric("PD band", rk.get("pd_band", "—"))
    c3.metric("Grade", g.get("grade", "—"))
    if rk.get("reasons"):
        st.markdown("**Main risk-increasing factors** (SHAP)")
        st.bar_chart(pd.DataFrame(rk["reasons"]).set_index("reason")["shap"])
    sc = g.get("scorecard")
    if sc:
        st.markdown(f"**Scorecard:** {sc['class']} ({sc['passed']}/3 ratio tests passed, using the thresholds read from the policy)")
        show_table(pd.DataFrame([{"Test": k, "Passed": "✅" if ok else "❌"} for k, ok in sc["tests"].items()]))
    st.caption(f"Model `{rk.get('model_version')}` — trained on SBA 7(a) loan outcomes; profile features only (see the documentation's Risk model page).")


def tab_research(v: dict) -> None:
    rs = v.get("research") or {}
    if not rs:
        st.info("Research has not been run yet.")
        return
    status = rs.get("sanctions_status", "not_performed")
    {"no_match": st.success, "confirmed_match": st.error, "possible_match": st.warning}.get(status, st.warning)(f"Sanctions screening: **{status.replace('_', ' ')}**")
    sev = rs.get("adverse_media_max_severity")
    st.markdown(f"**Adverse media:** {sev or 'none found'}")
    for a in rs.get("articles") or []:
        st.markdown(f"- {a}")
    if rs.get("summary"):
        st.caption(rs["summary"])
    c1, c2 = st.columns(2)
    reg = rs.get("registry") or {}
    c1.metric("Registry", "found" if reg.get("found") else "not found", help="Mock registry backed by the synthetic world.")
    rate = rs.get("industry_default_rate")
    c2.metric("Sector 5-yr default rate (SBA)", f"{rate:.1%}" if rate is not None else "—")


def tab_application(thread_id: str, v: dict) -> None:
    app = v.get("application") or {}
    prof = app.get("profile") or {}
    rows = {"Industry": app.get("industry_name"), "NAICS": app.get("naics"), "Years in business": app.get("years_in_business"),
            "Loan amount": money(app.get("loan_amount")), "Term (months)": app.get("term_months"), "Purpose": app.get("purpose"),
            "Collateral value": money(app.get("collateral_value")), "Personal guarantee": "yes" if app.get("guarantor_provided") else "no",
            "State": prof.get("state"), "Legal form": prof.get("business_type"), "Rate type": prof.get("fixed_or_variable"),
            "Jobs supported": prof.get("jobs_supported"), "Franchise": "yes" if prof.get("franchise") else "no"}
    show_table(pd.DataFrame({"Fact": list(rows), "Value": [str(x) for x in rows.values()]}))
    st.caption("These are the facts the agents see. Redaction is **" + ("on" if v.get("redaction", True) else "off") + "**.")
    if v.get("history"):
        st.markdown("**Prior decisions for this applicant**")
        show_table(pd.DataFrame(v["history"]))
    with st.expander("🔒 Sealed identity (hidden from the agents)"):
        if st.checkbox("I need to see the applicant's identity (e.g. to verify the documents)", key=f"reveal-{thread_id}"):
            s = v.get("sealed") or {}
            st.json({"owner": s.get("owner_name"), "business": s.get("business_name"), "address": s.get("address")})
        else:
            st.caption("Hidden by default so the approver, like the model, decides on the facts.")


def tab_timeline(v: dict) -> None:
    tr = v.get("trace") or []
    if tr:
        t0 = tr[0].get("t", 0)
        df = pd.DataFrame([{"Step": NODE_LABEL.get(x["step"], x["step"]), "Node": x["step"], "Elapsed (s)": round(x.get("t", t0) - t0, 1),
                            "Details": ", ".join(f"{k}={val}" for k, val in x.items() if k not in ("step", "t"))} for x in tr])
        show_table(df)
    loops = v.get("loops")
    if loops:
        st.caption(f"Loop counters: {loops}")
    if v.get("errors"):
        st.error("Errors: " + "; ".join(map(str, v["errors"])))


def downloads(thread_id: str, v: dict) -> None:
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("⬇️ Memo (Markdown)", memo_to_markdown(v), file_name=f"memo-{v.get('case_id')}.md", mime="text/markdown", key=f"dl-memo-{thread_id}")
    c2.download_button("⬇️ Evidence (JSON)", evidence_json(v), file_name=f"evidence-{thread_id}.json", mime="application/json", key=f"dl-json-{thread_id}",
                       help="The full case state without the sealed identity block.")


def case_detail(thread_id: str, snap: dict, *, actions: bool = True) -> dict | None:
    """The full review screen for one case. Returns a new snapshot if the user acted (so the caller can rerun), else None."""
    v = snap["values"]
    status = cases.status_of(snap)
    case_header(thread_id, v, status)
    tabs = st.tabs(["Memo", "Policy checklist", "Financials", "Risk", "Research", "Application", "Timeline"])
    with tabs[0]:
        tab_memo(v)
    with tabs[1]:
        tab_policy(v)
    with tabs[2]:
        tab_financials(v)
    with tabs[3]:
        tab_risk(v)
    with tabs[4]:
        tab_research(v)
    with tabs[5]:
        tab_application(thread_id, v)
    with tabs[6]:
        tab_timeline(v)
    downloads(thread_id, v)
    st.divider()
    intr = snap.get("interrupt")
    if actions and intr and intr.get("type") == "approval":
        return approval_panel(thread_id, v, intr)
    if actions and intr and intr.get("type") == "doc_review":
        return doc_review_panel(thread_id, v, intr)
    if v.get("final"):
        f = v["final"]
        st.success(f"**Decision recorded: {f['decision'].upper()}**" + ("  — an override of the recommendation" if f.get("override") else ""))
        st.json(f)
    return None


# --------------------------------------------------------------------------- human gates
def approval_panel(thread_id: str, v: dict, intr: dict) -> dict | None:
    required = intr.get("required_tier") or "Credit Committee"
    rec = v.get("recommendation")
    st.subheader("🧑‍⚖️ Your decision")
    st.caption(f"The system recommends **{(rec or '—').upper()}**. The policy requires at least **{required}** authority to decide this case.")
    if intr.get("error"):
        st.error(intr["error"])
    with st.form(f"approval-{thread_id}"):
        c1, c2 = st.columns(2)
        # pre-select the recommendation for approve/decline; for REFER leave it blank so the approver is not nudged either way
        decision = c1.radio("Decision", ["approve", "decline", "revise"], index=["approve", "decline", "revise"].index(rec) if rec in ("approve", "decline") else None,
                            horizontal=True, help="*Revise* sends the memo back to the writer with your comments (up to two times).")
        tier = c2.selectbox("Your authority tier", TIERS, index=TIERS.index(required))
        approver = st.text_input("Approver id", value=st.session_state.get("approver_id", "approver-1"))
        reason = st.text_area("Reason / comments", help="Required when you override the recommendation or ask for a revision.")
        submitted = st.form_submit_button("Submit decision", type="primary")
    if not submitted:
        return None
    st.session_state["approver_id"] = approver
    if decision is None:
        st.error("Choose approve, decline or revise.")
        return None
    override = decision in ("approve", "decline") and rec in ("approve", "decline") and decision != rec
    if (override or decision == "revise") and not reason.strip():
        st.error("A reason is required when you override the recommendation or request a revision.")
        return None
    if TIERS.index(tier) < TIERS.index(required):
        st.error(f"Your tier ({tier}) is below the required tier ({required}). Choose a higher authority or escalate the case.")
        return None
    return resume_case(thread_id, {"decision": decision, "approver_tier": tier, "approver_id": approver.strip() or "approver", "reason": reason.strip()})


def doc_review_panel(thread_id: str, v: dict, intr: dict) -> dict | None:
    st.subheader("📄 Document review needed")
    st.warning("The extracted figures failed consistency checks even after an automatic repair. Compare them with the PDFs, then accept, correct or reject.")
    for i in intr.get("reconciliation_issues") or []:
        st.markdown(f"- FY{i.get('year', '')} · {i.get('check')} (expected {i.get('expected', '—')}, got {i.get('actual', '—')})")
    for i in intr.get("bank_issues") or []:
        st.markdown(f"- Bank · {i.get('month', '')} {i.get('check')}")
    ext = intr.get("extracted") or {}
    edited = None
    if ext:
        original = pd.DataFrame(ext).sort_index(axis=1)
        st.markdown("**Extracted statements — edit any wrong value:**")
        edited = st.data_editor(original, width="stretch", key=f"edit-{thread_id}")
    c1, c2, c3 = st.columns(3)
    action = None
    if c1.button("✅ Accept as is", key=f"acc-{thread_id}"):
        action = {"action": "accept"}
    if c2.button("✏️ Submit my corrections", key=f"cor-{thread_id}", disabled=edited is None):
        diff = {}
        for year in edited.columns:
            for field in edited.index:
                new, old = edited.loc[field, year], original.loc[field, year]
                if pd.notna(new) and (pd.isna(old) or float(new) != float(old)):
                    diff.setdefault(str(year), {})[field] = float(new)
        action = {"action": "correct", "corrections": diff} if diff else None
        if not diff:
            st.info("You have not changed any values.")
    if c3.button("🛑 Reject the documents", key=f"rej-{thread_id}"):
        action = {"action": "reject"}
    return resume_case(thread_id, action) if action else None
