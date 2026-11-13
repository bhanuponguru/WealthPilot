"""Console tests. The offline ones need no services; the `live` ones need the full stack (Postgres, Ollama, MCP servers, NIM key)."""

import pymupdf
import pytest
from streamlit.testing.v1 import AppTest

from wealthpilot import health
from wealthpilot.graph import cases
from wealthpilot.graph.builder import make_input_from_applicant
from wealthpilot.ui import forms

GOOD = {"business_name": "Harbor Bakery LLC", "owner_name": "Jane Harbor", "industry_name": "Restaurant and catering", "naics": "722511",
        "years_in_business": 6, "business_type": "CORPORATION", "jobs_supported": 8, "street": "12 Main St", "city": "Columbus", "state": "OH", "zip": "43215",
        "loan_amount": 120000, "term_months": 84, "purpose": "expansion", "collateral_value": 60000, "fixed_or_variable": "V", "guarantor_provided": True, "franchise": False}


def _pdf(pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"page {i}")
    return doc.tobytes()


# ---------------------------------------------------------------- form validation and building
def test_valid_form_has_no_errors():
    assert forms.validate_application(GOOD) == []


@pytest.mark.parametrize("change,fragment", [
    ({"business_name": " "}, "Business name"), ({"owner_name": "Madonna"}, "first and last"), ({"naics": "7225"}, "NAICS"),
    ({"loan_amount": 500}, "Loan amount"), ({"term_months": 2}, "Term"), ({"zip": "4321"}, "ZIP"), ({"state": "ZZ"}, "state"),
    ({"collateral_value": -1}, "Collateral"), ({"years_in_business": -1}, "Years"),
])
def test_invalid_form_is_explained(change, fragment):
    errs = forms.validate_application({**GOOD, **change})
    assert any(fragment in e for e in errs), errs


def test_built_applicant_keeps_identity_out_of_llm_facts():
    a = forms.build_applicant(GOOD, "U1")
    inp = make_input_from_applicant(a, "strict", {"financials": "f.pdf", "bank": "b.pdf"}, redaction=True)
    llm_facts = str(inp["application"])
    assert "Harbor" not in llm_facts and "Jane" not in llm_facts and "[OWNER]" in inp["application"]["business_label"]
    assert inp["sealed"]["owner_name"] == "Jane Harbor"                       # identity is kept, but only in the sealed block
    assert inp["application"]["naics"] == "722511" and inp["application"]["guarantor_provided"] is True
    off = make_input_from_applicant(a, "strict", {"financials": "f.pdf", "bank": "b.pdf"}, redaction=False)
    assert off["application"]["business_label"] == "Harbor Bakery LLC"
    assert inp["applicant_id"] == off["applicant_id"]                         # same applicant -> same memory key


def test_known_industry_gets_its_tag():
    assert forms.build_applicant({**GOOD, "industry_name": "Cannabis dispensary", "naics": "453998"}, "U2")["industry"]["tag"] == "cannabis"
    assert forms.build_applicant({**GOOD, "industry_name": "Bespoke thing"}, "U3")["industry"]["tag"] == "other"


# ---------------------------------------------------------------- uploads
def test_save_uploads_stores_both_pdfs(tmp_path):
    paths = forms.save_uploads("U9", _pdf(2), _pdf(1), root=tmp_path)
    assert paths["financials"].exists() and paths["bank"].exists() and paths["financials"].parent == tmp_path / "U9"


@pytest.mark.parametrize("data,fragment", [(b"", "empty"), (b"not a pdf at all", "not a readable PDF"), (_pdf(forms.MAX_PAGES + 1), "pages")])
def test_bad_uploads_are_rejected_with_a_reason(tmp_path, data, fragment):
    with pytest.raises(ValueError, match=fragment):
        forms.save_uploads("U8", data, _pdf(), root=tmp_path)
    assert not (tmp_path / "U8").exists()           # nothing stored for a rejected upload


# ---------------------------------------------------------------- export
STATE = {"case_id": "C9", "policy_id": "strict", "recommendation": "decline", "required_tier": "Senior Credit Officer", "grade": {"grade": "B"},
         "risk": {"pd": 0.026}, "application": {"business_label": "[OWNER] Retail LLC", "industry_name": "Retail", "loan_amount": 100000, "term_months": 84, "purpose": "expansion"},
         "sealed": {"owner_name": "Jane Harbor", "business_name": "Harbor Retail LLC"},
         "memo": {"summary": "Declined on loan-to-revenue.", "strengths": ["Strong DSCR"], "concerns": ["High LTR"], "adverse_action_reasons": [{"rule_id": "CP-6", "reason": "Loan too large vs revenue"}]},
         "policy_checks": [{"rule_id": "CP-6", "title": "Loan size", "status": "fail", "reason": "0.36 > 0.30"}],
         "final": {"decision": "decline", "override": False, "approver": "sco-7", "approver_tier": "Senior Credit Officer"}}


def test_memo_markdown_has_the_sections_and_no_identity():
    md = forms.memo_to_markdown(STATE)
    for text in ("# Credit memo — C9", "DECLINE", "Declined on loan-to-revenue.", "Strong DSCR", "(CP-6)", "| CP-6 Loan size | fail |", "sco-7"):
        assert text in md
    assert "Jane" not in md and "Harbor" not in md
    assert "Jane" not in forms.evidence_json(STATE)             # the sealed block is dropped from the evidence download


def test_degraded_memo_is_flagged():
    assert "Degraded run" in forms.memo_to_markdown({**STATE, "degraded": True, "degraded_reasons": ["research down"]})


def test_parse_rules_reads_a_real_policy():
    from wealthpilot.config import PROJECT_ROOT
    rules = forms.parse_rules((PROJECT_ROOT / "data" / "policies" / "strict" / "policy.md").read_text())
    assert [r["rule_id"] for r in rules] == [f"CP-{i}" for i in range(1, 14)]
    assert "1.30" in next(r for r in rules if r["rule_id"] == "CP-3")["text"]


# ---------------------------------------------------------------- case index status mapping
@pytest.mark.parametrize("snap,expected", [
    ({"interrupt": {"type": "approval"}, "done": False, "values": {}}, "awaiting_approval"),
    ({"interrupt": {"type": "doc_review"}, "done": False, "values": {}}, "awaiting_doc_review"),
    ({"interrupt": None, "done": True, "values": {"final": {"decision": "approve"}}}, "decided"),
    ({"interrupt": None, "done": True, "values": {}}, "finished"),
    ({"interrupt": None, "done": False, "values": {}}, "running"),
])
def test_case_status_mapping(snap, expected):
    assert cases.status_of(snap) == expected


def test_snapshot_fields_never_include_identity():
    f = cases.fields_from_snapshot({"interrupt": None, "done": False, "values": STATE})
    assert "Jane" not in str(f) and f["business_label"] == "[OWNER] Retail LLC" and f["grade"] == "B" and f["status"] == "running"


# ---------------------------------------------------------------- health
def test_closed_port_is_reported_not_raised():
    assert health._tcp(1, timeout=0.2) is False


def test_blocking_checks_are_only_the_essential_ones():
    checks = [health.Check("Postgres", False, "down", "x"), health.Check("MLflow (traces)", False, "down", "y", required=False), health.Check("MCP: fincalc", False, "down", "z")]
    assert [c.name for c in health.blocking(checks)] == ["Postgres"]


# ---------------------------------------------------------------- pages render (with or without services)
PAGE_MODULES = ["home", "underwrite", "queue", "history", "policies", "results", "system"]


@pytest.mark.parametrize("page", PAGE_MODULES)
def test_every_page_renders_without_an_exception(page):
    """Whether or not Postgres/MCP/Ollama are up, a page must show a message, never a stack trace."""
    at = AppTest.from_string(f"from wealthpilot.ui.views import {page}\n{page}.render()", default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]


def test_full_app_with_navigation_renders():
    from wealthpilot.config import PROJECT_ROOT
    at = AppTest.from_file(str(PROJECT_ROOT / "src" / "wealthpilot" / "ui" / "app.py"), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
