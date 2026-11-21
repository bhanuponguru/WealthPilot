"""Research tests: the reference engine and the generated ground truth."""

from wealthpilot_lab import reference_engine as policy_ref
from wealthpilot_lab.synth.applicants import truth_of

from wealthpilot import finance

FS = {"revenue": 1_000_000, "cogs": 500_000, "operating_expenses": 250_000, "depreciation": 40_000, "interest_expense": 20_000, "income_tax": 47_500,
      "net_income": 142_500, "total_current_assets": 400_000, "total_current_liabilities": 200_000, "current_portion_ltd": 20_000,
      "total_liabilities": 600_000, "total_equity": 300_000}


def test_lenient_dscr_exception_band(world):
    a = world[0][0]
    t = truth_of(a)
    strict, lenient = policy_ref.load_reference("strict"), policy_ref.load_reference("lenient")
    assert strict["dscr_exception_floor"] is None and lenient["dscr_exception_floor"] == 1.05
    # craft statements giving DSCR ~1.10 and ample collateral
    fs = dict(FS)
    t = dict(t, statements={"2024": fs}, years_in_business=10, industry_tag="software", guarantor_provided=True, sanctions_hit=False,
             adverse_severity=None, loan_amount=100_000, term_months=60, collateral_value=130_000)
    base = finance.compute_ratios(fs, 100_000, 60, 130_000)["dscr"]
    fs["net_income"] = int(1.10 * (20_000 + 20_000 + 12 * 2075.84) - 20_000 - 40_000)
    assert 1.05 <= finance.compute_ratios(fs, 100_000, 60, 130_000)["dscr"] < 1.15 < base
    res = policy_ref.evaluate_case(t, 0.01, lenient)
    assert {c["rule_id"]: c["status"] for c in res["checks"]}["CP-3"] == "exception"
    assert policy_ref.evaluate_case(t, 0.01, strict)["checks"][2]["status"] == "fail"


def test_ground_truth_decisions_differ_between_policies(world):
    gt = world[1]
    assert sum(v["strict"]["recommendation"] != v["lenient"]["recommendation"] for v in gt.values()) >= 20
