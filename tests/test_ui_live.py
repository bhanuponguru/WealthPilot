"""Live console tests: drive the real Streamlit pages against the running stack.

Needs Postgres, Ollama, the three MCP servers and a NIM key (`uv run wealthpilot doctor`). Prompts are cached after the first run,
so repeats are fast; the very first run of each scenario can take several minutes on the free model tier.
"""

import asyncio
import time

import pytest
from streamlit.testing.v1 import AppTest

from wealthpilot.config import PROJECT_ROOT
from wealthpilot.graph import cases
from wealthpilot.graph.builder import make_input_from_applicant, session
from wealthpilot.synth.render_docs import DOCS_DIR
from wealthpilot.ui import forms

pytestmark = pytest.mark.live
RUN_TIMEOUT = 600


def page(name: str) -> AppTest:
    return AppTest.from_string(f"from wealthpilot.ui.views import {name}\n{name}.render()", default_timeout=120)


def widget(at: AppTest, kind: str, label: str):
    return next(w for w in getattr(at, kind) if w.label == label)


def wait_until(at: AppTest, done, timeout: float = RUN_TIMEOUT) -> AppTest:
    """Runs execute in the background, so the page returns at once. Re-run it (as the live-progress fragment does) until `done(at)`."""
    deadline = time.time() + timeout
    while not done(at):
        assert time.time() < deadline, "the run did not finish in time"
        time.sleep(3)
        at.run(timeout=120)
        assert not at.exception, [e.value for e in at.exception]
    return at


def has_decision_form(at: AppTest) -> bool:
    return any(r.label == "Decision" for r in at.radio)


def decision_recorded(at: AppTest) -> bool:
    return any("Decision recorded" in s.value for s in at.success)


def test_sample_case_runs_and_a_human_decides_through_the_form():
    at = page("underwrite").run()
    assert not at.exception
    at.selectbox(key="sample-case").select("C004")
    at.radio(key="sample-policy").set_value("strict")
    at.radio(key="sample-variant").set_value("clean")
    at.button(key="sample-run").click().run(timeout=120)
    assert not at.exception, [e.value for e in at.exception]
    wait_until(at, has_decision_form)

    thread = at.session_state["active_thread"]
    assert any(m.label == "Recommendation" and m.value == "DECLINE" for m in at.metric)
    row = cases.get(thread)
    assert row["status"] == "awaiting_approval" and row["recommendation"] == "decline" and row["source"] == "synthetic"
    assert "Jane" not in str(row) and row["business_label"].startswith("[OWNER]")        # the index never holds identity

    # an under-authorised approver is stopped by the form itself, before anything is sent to the graph
    widget(at, "radio", "Decision").set_value("decline")
    widget(at, "selectbox", "Your authority tier").select("Analyst")
    widget(at, "text_input", "Approver id").set_value("live-test-sco")
    next(b for b in at.get("form_submit_button")).click()
    at.run(timeout=RUN_TIMEOUT)
    assert any("below the required tier" in e.value for e in at.error)
    assert cases.get(thread)["status"] == "awaiting_approval"

    # a proper decision records it
    widget(at, "selectbox", "Your authority tier").select("Senior Credit Officer")
    widget(at, "text_input", "Approver id").set_value("live-test-sco")
    next(b for b in at.get("form_submit_button")).click()
    at.run(timeout=120)
    wait_until(at, decision_recorded)
    row = cases.get(thread)
    assert row["status"] == "decided" and row["decision"] == "decline"


def test_override_requires_a_reason():
    at = page("underwrite").run()
    at.selectbox(key="sample-case").select("C004")
    assert at.radio(key="sample-policy").value == "strict"                      # strict is pre-selected
    at.button(key="sample-run").click().run(timeout=120)
    wait_until(at, has_decision_form)
    widget(at, "radio", "Decision").set_value("approve")                        # contradicts the DECLINE recommendation
    widget(at, "selectbox", "Your authority tier").select("Senior Credit Officer")
    widget(at, "text_input", "Approver id").set_value("live-test-sco")
    next(b for b in at.get("form_submit_button")).click()
    at.run(timeout=RUN_TIMEOUT)
    assert any("reason is required" in e.value for e in at.error)


def test_a_run_survives_the_page_that_started_it():
    """Leaving the page (or closing the tab) must not abandon a run: it belongs to the background worker, not to the page script."""
    from wealthpilot.ui.runner import manager
    at = page("underwrite").run()
    at.selectbox(key="sample-case").select("C004")
    at.button(key="sample-run").click().run(timeout=120)
    thread = at.session_state["active_thread"]
    assert manager().is_active(thread) or cases.get(thread)["status"] != "running"
    del at                                                                      # the page is gone; nobody is watching
    deadline = time.time() + RUN_TIMEOUT
    while manager().is_active(thread):
        assert time.time() < deadline
        time.sleep(3)
    assert manager().progress(thread).error is None
    assert cases.get(thread)["status"] in ("awaiting_approval", "decided")


def test_an_interrupted_run_can_be_continued():
    """A case left 'running' by a killed process shows as interrupted and can be continued from its checkpoint."""
    from wealthpilot.ui.runner import manager
    at = page("underwrite").run()
    at.selectbox(key="sample-case").select("C004")
    at.button(key="sample-run").click().run(timeout=120)
    thread = at.session_state["active_thread"]
    wait_until(at, has_decision_form)
    cases.upsert(thread, status="running")                                      # simulate a crash: the index says running, the worker knows nothing
    manager()._runs.pop(thread, None)
    at.run(timeout=120)
    assert any("interrupted" in w.value.lower() for w in at.warning)
    next(b for b in at.button if b.key == f"continue-{thread}").click().run(timeout=120)
    wait_until(at, has_decision_form)
    assert cases.get(thread)["status"] == "awaiting_approval"


def test_cases_history_system_and_policies_pages_render_with_data():
    q = page("queue").run(timeout=120)
    assert not q.exception and q.dataframe, "the cases table should list the runs created above (or earlier)"
    h = page("history").run(timeout=120)
    assert not h.exception and any("Audit chain intact" in s.value for s in h.success)
    s = page("system").run(timeout=120)
    assert not s.exception and s.dataframe
    p = page("policies").run(timeout=120)
    assert not p.exception
    p.text_input(key="s-q").set_value("What is the minimum DSCR?")
    p.button(key="s-go").click().run(timeout=RUN_TIMEOUT)
    assert not p.exception and any("CP-3" in m.value for m in p.markdown)


def test_new_application_with_uploaded_pdfs_end_to_end():
    """The full 'New application' path: form -> validation -> saved PDFs -> graph -> case index -> decision."""
    form = {"business_name": "Harbor Bakery LLC", "owner_name": "Jane Harbor", "industry_name": "Restaurant and catering", "naics": "722511", "years_in_business": 6,
            "business_type": "CORPORATION", "jobs_supported": 8, "street": "12 Main St", "city": "Columbus", "state": "OH", "zip": "43215", "loan_amount": 100000,
            "term_months": 84, "purpose": "expansion", "collateral_value": 160000, "fixed_or_variable": "V", "guarantor_provided": True, "franchise": False}
    assert forms.validate_application(form) == []
    src = DOCS_DIR / "C004" / "clean"                                            # real statements, "uploaded" as raw bytes
    case_id = forms.new_case_id() + "t"
    paths = forms.save_uploads(case_id, (src / "financials.pdf").read_bytes(), (src / "bank_statement.pdf").read_bytes())
    assert paths["financials"].is_relative_to(PROJECT_ROOT / "data" / "uploads")
    state_in = make_input_from_applicant(forms.build_applicant(form, case_id), "strict", paths, redaction=True)
    assert "Jane" not in str(state_in["application"])

    async def go():
        async with session() as runner:
            snap = await runner.start(state_in, f"{case_id}-ui", None, {"source": "upload", "variant": "uploaded"})
            assert snap["interrupt"]["type"] in ("approval", "doc_review")
            if snap["interrupt"]["type"] == "approval":
                snap = await runner.resume(f"{case_id}-ui", {"decision": snap["values"]["recommendation"] if snap["values"]["recommendation"] != "refer" else "decline",
                                                              "approver_tier": "Credit Committee", "approver_id": "live-test", "reason": "test"})
            return snap
    snap = asyncio.run(go())
    row = cases.get(f"{case_id}-ui")
    assert row["source"] == "upload" and row["status"] in ("decided", "awaiting_doc_review") and row["business_label"].startswith("[OWNER]")
    assert snap["values"]["policy_checks"], "the policy rules should have been evaluated for an uploaded application"
