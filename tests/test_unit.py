"""Offline unit tests (no NIM, no MCP). Run: uv run pytest -m "not live" """

import pytest

from wealthpilot import decision, finance
from wealthpilot.compliance.language_scan import scan
from wealthpilot.compliance.redaction import Redactor, leaked_terms
from wealthpilot.config import Settings
from wealthpilot.graph import nodes as N
from wealthpilot.parsing.pipeline import reconcile, reconcile_bank

FS = {"revenue": 1_000_000, "cogs": 500_000, "operating_expenses": 250_000, "depreciation": 40_000, "interest_expense": 20_000, "income_tax": 47_500,
      "net_income": 142_500, "total_current_assets": 400_000, "total_current_liabilities": 200_000, "current_portion_ltd": 20_000,
      "total_liabilities": 600_000, "total_equity": 300_000}


# ---------------------------------------------------------------- finance
def test_amortized_payment_known_value():
    assert finance.amortized_payment(100_000, 0.09, 60) == pytest.approx(2075.84, abs=0.01)


def test_ratios_and_dscr_definition():
    r = finance.compute_ratios(FS, 100_000, 60, collateral_value=120_000)
    service = 20_000 + 20_000 + 12 * 2075.84
    assert r["dscr"] == pytest.approx((142_500 + 20_000 + 40_000) / service, abs=1e-3)
    assert r["debt_to_equity"] == 2.0 and r["current_ratio"] == 2.0 and r["loan_to_revenue"] == 0.1 and r["collateral_coverage"] == 1.2


def test_compare_and_missing():
    assert finance.compare(1.22, ">=", 1.30)["result"] is False
    assert finance.compare(None, ">=", 1.30) == {"result": None, "reason": "missing_data"}


def test_scorecard_grade_matrix():
    sc = finance.scorecard({"dscr": 1.5, "debt_to_equity": 2.0, "current_ratio": 1.5}, 1.3, 3.0, 1.2)
    assert sc["class"] == "strong"
    assert finance.grade(0.01, "strong")["grade"] == "A"
    assert finance.grade(0.05, "weak")["grade"] == "E"
    assert finance.grade_at_most("C", "C") and not finance.grade_at_most("D", "C")


# ---------------------------------------------------------------- decision rule
def test_decision_rule():
    f = lambda *s: [{"status": x} for x in s]  # noqa: E731
    assert decision.derive_recommendation(f("pass", "fail", "exception")) == "decline"
    assert decision.derive_recommendation(f("pass", "exception")) == "refer"
    assert decision.derive_recommendation(f("pass", "missing_data")) == "refer"
    assert decision.derive_recommendation(f("pass", "not_applicable")) == "approve"


def test_degraded_never_auto_decides():
    assert N.final_recommendation([{"status": "pass"}], degraded=True) == "refer"
    assert N.final_recommendation([{"status": "fail"}], degraded=True) == "refer"   # no adverse action caused by an outage
    assert N.final_recommendation([{"status": "pass"}], degraded=False) == "approve"
    assert N.final_recommendation([{"status": "fail"}], degraded=False) == "decline"


# ---------------------------------------------------------------- reconciliation
def _stmt():
    return {"2024": {"revenue": 100, "cogs": 40, "operating_expenses": 30, "depreciation": 5, "interest_expense": 5, "income_tax": 5, "net_income": 15,
                     "cash": 10, "accounts_receivable": 10, "inventory": 10, "total_current_assets": 30, "net_fixed_assets": 70, "total_assets": 100,
                     "accounts_payable": 10, "current_portion_ltd": 5, "total_current_liabilities": 15, "long_term_debt": 35, "total_liabilities": 50, "total_equity": 50}}


def test_reconcile_clean_and_broken():
    assert reconcile(_stmt()) == []
    bad = _stmt()
    bad["2024"]["total_assets"] = 120
    assert any("assets = liabilities" in i["check"] for i in reconcile(bad))


def test_bank_rollforward():
    ok = {"months": [{"month": "2024-01", "opening": 100, "deposits": 50, "withdrawals": 30, "closing": 120},
                     {"month": "2024-02", "opening": 120, "deposits": 10, "withdrawals": 20, "closing": 110}]}
    assert reconcile_bank(ok) == []
    ok["months"][1]["opening"] = 999
    assert reconcile_bank(ok)


# ---------------------------------------------------------------- redaction / compliance
def test_redaction_covers_name_zip_and_business_name():
    a = {"owner_name": "Chidi Okonkwo", "address": {"street": "88 Bayshore Ave", "zip": "33602", "city": "Tampa", "state": "FL"}}
    red = Redactor(a)
    out = red("Okonkwo Retail LLC, owner CHIDI Okonkwo, 88 Bayshore Ave, Tampa FL 33602; OKONKWO, Chidi")
    assert leaked_terms(out, a) == []
    assert "[OWNER]" in out and "Tampa" in out  # city kept
    assert Redactor(a, enabled=False)("Chidi Okonkwo") == "Chidi Okonkwo"


def test_language_scan():
    assert "gender" in scan("We considered her gender.")
    assert scan("The business has strong cash flow.") == []


# ---------------------------------------------------------------- memo validator helpers
def test_unsupported_numbers():
    allowed = {1.88, 100000.0, 1.3, 7.0, 188.0}
    assert N.unsupported_numbers("DSCR of 1.88 versus minimum 1.30 on a $100,000 loan (CP-3, FY2024)", allowed) == []
    assert N.unsupported_numbers("DSCR of 2.45 on a $100,000 loan", allowed) == ["2.45"]


# ---------------------------------------------------------------- routing predicates (code, never an LLM)
def test_routing():
    base = {"loops": {"policy": 0, "memo": 0, "revise": 0}}
    assert N.route_after_parse({**base, "reconciliation_issues": [{"x": 1}]}) == "doc_review"
    assert N.route_after_parse({**base, "reconciliation_issues": [], "bank_issues": []}) == ["analyst", "research"]
    missing = {**base, "policy_checks": [{"status": "missing_data"}], "extracted": {"2024": {}}}
    assert N.route_after_policy(missing) == "analyst_retry"
    assert N.route_after_policy({**missing, "loops": {"policy": 1}}) == "grade"
    assert N.route_after_policy({**base, "policy_checks": [{"status": "pass"}]}) == "grade"
    assert N.route_after_validator({**base, "validator_issues": ["x"], "loops": {"memo": 1}}) == "memo"
    assert N.route_after_validator({**base, "validator_issues": ["x"], "loops": {"memo": 2}}) == "human_approval"
    assert N.route_after_validator({**base, "validator_issues": []}) == "human_approval"
    assert N.route_after_approval({**base, "human_decision": {"decision": "revise"}, "loops": {"revise": 1}}) == "memo"
    assert N.route_after_approval({**base, "human_decision": {"decision": "revise"}, "loops": {"revise": 3}}) == "finalize"
    assert N.route_after_approval({**base, "human_decision": {"decision": "approve"}}) == "finalize"


def test_rule_status_mapping():
    assert N.to_status({"applies": False}) == "not_applicable"
    assert N.to_status({"applies": True, "rule_satisfied": True, "exception": False}) == "pass"
    assert N.to_status({"applies": True, "rule_satisfied": False, "exception": False}) == "fail"
    assert N.to_status({"applies": True, "rule_satisfied": False, "exception": True}) == "exception"
    assert N.to_status({"applies": True, "rule_satisfied": None, "exception": False}) == "missing_data"


# ---------------------------------------------------------------- config precedence: .env > global env > error
def test_config_precedence(tmp_path, monkeypatch):
    for k in ("NVIDIA_API_KEY", "NVIDIA_NIM_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    envf, blank, none = tmp_path / "a.env", tmp_path / "b.env", tmp_path / "c.env"
    envf.write_text("NVIDIA_API_KEY=from-dotenv\n")
    blank.write_text("NVIDIA_API_KEY=\n")
    none.write_text("")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "from-global")
    assert Settings(_env_file=envf).nvidia_api_key.get_secret_value() == "from-dotenv"
    assert Settings(_env_file=blank).nvidia_api_key.get_secret_value() == "from-global"
    assert Settings(_env_file=none).nvidia_api_key.get_secret_value() == "from-global"
    monkeypatch.delenv("NVIDIA_NIM_API_KEY")
    with pytest.raises(Exception):
        Settings(_env_file=none)


# ---------------------------------------------------------------- audit chain (needs Postgres)
@pytest.mark.live
def test_audit_chain_detects_tampering():
    from wealthpilot.compliance import audit
    from wealthpilot.nim.store import pool
    h1 = audit.append("pytest", "t1", {"v": 1})
    audit.append("pytest", "t2", {"v": 2})
    assert audit.verify()["ok"]
    with pool().connection() as c:
        rid, payload = c.execute("select id, payload from audit_log where case_id='pytest' and event='t1' order by id desc limit 1").fetchone()
        c.execute("update audit_log set payload = '{\"v\": 999}' where id = %s", (rid,))
    bad = audit.verify()
    assert not bad["ok"] and bad["first_bad_id"] == rid
    with pool().connection() as c:                      # restore so the log stays valid
        import json
        c.execute("update audit_log set payload = %s where id = %s", (json.dumps(payload), rid))
    assert audit.verify()["ok"] and h1


def test_numeric_verification_catches_llm_arithmetic():
    """The CP-8 failure seen in E0: the model claimed 132,000 > 150,000."""
    wrong = N.wrong_comparisons({"comparisons": [{"left": 132000, "op": ">", "right": 150000, "claimed_true": True},
                                                 {"left": 1.22, "op": ">=", "right": 1.30, "claimed_true": False}]})
    assert len(wrong) == 1 and "132000" in wrong[0]
    assert N.wrong_comparisons({"comparisons": [{"left": 3, "op": "≥", "right": 2, "claimed_true": True}]}) == []
    assert N.wrong_comparisons({"comparisons": [{"left": "x", "op": ">", "right": 1, "claimed_true": True}]}) == []  # malformed: ignored
    assert N.wrong_comparisons(None) == []


def test_redaction_is_whole_word_only():
    """Found via E3: substring redaction turned 'market' into '[OWNER]et' for an owner named Mark."""
    a = {"owner_name": "Mark Hanson", "address": {"street": "88 Oak Ave", "zip": "33602", "city": "Tampa", "state": "FL"}}
    txt = "The market analysis is fine; marketing is stable. Contact Mark Hanson, ZIP 33602, ref 1336029."
    out = Redactor(a)(txt)
    assert "market analysis" in out and "marketing" in out and "1336029" in out
    assert "Mark Hanson" not in out and "33602," not in out and "[OWNER]" in out and "[ZIP]" in out
    assert leaked_terms("The market analysis is fine.", a) == []
    assert "first_name" in leaked_terms("Contact Mark about this.", a)


# ---------------------------------------------------------------- batched rule judge (offline, LLM and MCP mocked)
def _run_batch(monkeypatch, replies):
    import asyncio
    from types import SimpleNamespace

    calls = {"llm": 0, "prompts": []}

    async def fake_retrieve(policy_id, rule):
        return [{"rule_ids": [rule["rule_id"]], "title": rule["title"], "text": f"{rule['rule_id']} text"}]

    def fake_llm_json(llm, messages):
        calls["llm"] += 1
        calls["prompts"].append(messages[-1].content)
        return replies[min(calls["llm"], len(replies)) - 1]

    monkeypatch.setattr(N, "_retrieve", fake_retrieve)
    monkeypatch.setattr(N, "llm_json", fake_llm_json)
    monkeypatch.setattr(N, "rt", SimpleNamespace(llm=object()))
    rules = [{"rule_id": "CP-8", "title": "Collateral"}, {"rule_id": "CP-2", "title": "Prohibited Industries"}]
    return asyncio.run(N.judge_batch("strict", rules, {"loan_amount": 132000})), calls


def test_batch_judge_maps_answers_to_statuses(monkeypatch):
    ok = {"CP-8": {"applies": False, "rule_satisfied": None, "exception": False, "reason": "below threshold", "extracted_threshold": 150000,
                   "comparisons": [{"left": 132000, "op": "<=", "right": 150000, "claimed_true": True}]},
          "CP-2": {"applies": True, "rule_satisfied": True, "exception": False, "reason": "not prohibited", "extracted_threshold": None, "comparisons": []}}
    out, calls = _run_batch(monkeypatch, [ok])
    assert calls["llm"] == 1                       # a whole batch costs ONE LLM call when the comparisons are right
    st = {c["rule_id"]: c for c in out}
    assert st["CP-8"]["status"] == "not_applicable" and st["CP-8"]["extracted_threshold"] == 150000 and st["CP-8"]["numeric_check"] == "ok"
    assert st["CP-2"]["status"] == "pass" and st["CP-2"]["citation"] == "strict/CP-2"


def test_batch_judge_reasks_after_wrong_comparison(monkeypatch):
    """The E0 failure: the model claimed 132,000 > 150,000. Code catches it and re-asks only that rule."""
    bad = {"CP-8": {"applies": True, "rule_satisfied": False, "exception": False, "comparisons": [{"left": 132000, "op": ">", "right": 150000, "claimed_true": True}]},
           "CP-2": {"applies": True, "rule_satisfied": True, "exception": False, "comparisons": []}}
    fixed = {"CP-8": {"applies": False, "rule_satisfied": None, "exception": False, "reason": "132,000 is below 150,000",
                      "comparisons": [{"left": 132000, "op": ">", "right": 150000, "claimed_true": False}]}}
    out, calls = _run_batch(monkeypatch, [bad, fixed])
    assert calls["llm"] == 2 and "actually FALSE" in calls["prompts"][1]
    st = {c["rule_id"]: c for c in out}
    assert st["CP-8"]["status"] == "not_applicable" and st["CP-8"]["numeric_check"] == "repaired"
    assert st["CP-2"]["status"] == "pass"


def test_batch_judge_fails_safe_when_still_inconsistent(monkeypatch):
    bad = {"CP-8": {"applies": True, "rule_satisfied": False, "exception": False, "comparisons": [{"left": 132000, "op": ">", "right": 150000, "claimed_true": True}]},
           "CP-2": {"applies": True, "rule_satisfied": True, "exception": False, "comparisons": []}}
    out, _ = _run_batch(monkeypatch, [bad, bad])   # the re-ask repeats the mistake
    assert {c["rule_id"]: c["status"] for c in out}["CP-8"] == "missing_data"   # never a silent wrong verdict
