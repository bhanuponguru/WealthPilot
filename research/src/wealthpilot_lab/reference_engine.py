"""Reference policy engine: the ground truth that agent results are scored against.

It reads a hidden, machine-readable answer key for each credit policy, which the agents never see, and applies the same fixed
decision rule the product uses to the ground-truth rule results.
"""

from __future__ import annotations

import yaml

from wealthpilot import finance
from wealthpilot.decision import (  # noqa: F401
    RULE_IDS,
    STATUSES,
    derive_recommendation,
    required_tier,
)

from .paths import REFERENCE


def load_reference(policy_id: str) -> dict:
    return yaml.safe_load((REFERENCE / f"{policy_id}.yaml").read_text())


def _chk(rule: str, status: str, reason: str | None = None) -> dict:
    return {"rule_id": rule, "status": status, "reason": reason}


def evaluate_case(truth: dict, pd: float, ref: dict) -> dict:
    """Ground-truth evaluation of one synthetic case under one policy.

    `truth` keys: years_in_business, industry_tag, statements (dict year-> fs), loan_amount, term_months,
    collateral_value, guarantor_provided, sanctions_hit (bool), adverse_severity (None|low|medium|high).
    """
    years = sorted(truth["statements"])
    latest = truth["statements"][years[-1]]
    ratios = finance.compute_ratios(latest, truth["loan_amount"], truth["term_months"], truth["collateral_value"])
    sc = finance.scorecard(ratios, ref["min_dscr"], ref["max_debt_to_equity"], ref["min_current_ratio"])
    g = finance.grade(pd, sc["class"])
    cov = ratios["collateral_coverage"]
    checks = []

    checks.append(_chk("CP-1", "pass" if truth["years_in_business"] >= ref["min_years_in_business"] else "fail"))
    checks.append(_chk("CP-2", "fail" if truth["industry_tag"] in ref["prohibited_industries"] else "pass"))

    dscr = ratios["dscr"]
    if dscr is None:
        checks.append(_chk("CP-3", "missing_data", "dscr"))
    elif dscr >= ref["min_dscr"]:
        checks.append(_chk("CP-3", "pass"))
    elif ref["dscr_exception_floor"] is not None and dscr >= ref["dscr_exception_floor"] \
            and cov is not None and cov >= ref["dscr_exception_min_collateral"]:
        checks.append(_chk("CP-3", "exception"))
    else:
        checks.append(_chk("CP-3", "fail"))

    de = ratios["debt_to_equity"]
    checks.append(_chk("CP-4", "missing_data") if de is None else _chk("CP-4", "pass" if 0 <= de <= ref["max_debt_to_equity"] else "fail"))
    cr = ratios["current_ratio"]
    checks.append(_chk("CP-5", "missing_data") if cr is None else _chk("CP-5", "pass" if cr >= ref["min_current_ratio"] else "fail"))
    lr = ratios["loan_to_revenue"]
    checks.append(_chk("CP-6", "missing_data") if lr is None else _chk("CP-6", "pass" if lr <= ref["max_loan_to_revenue"] else "fail"))
    checks.append(_chk("CP-7", "pass" if len(years) >= ref["min_statement_years"] else "fail"))

    if truth["loan_amount"] > ref["collateral_threshold_amount"]:
        checks.append(_chk("CP-8", "pass" if (cov or 0) >= ref["min_collateral_coverage"] else "fail"))
    else:
        checks.append(_chk("CP-8", "not_applicable", "below_threshold"))

    need_guarantee = (
        ref["guarantee_always"]
        or (ref["guarantee_amount_trigger"] is not None and truth["loan_amount"] > ref["guarantee_amount_trigger"])
        or (ref["guarantee_years_trigger"] is not None and truth["years_in_business"] < ref["guarantee_years_trigger"])
    )
    if need_guarantee:
        checks.append(_chk("CP-9", "pass" if truth["guarantor_provided"] else "fail"))
    else:
        checks.append(_chk("CP-9", "not_applicable", "not_required"))

    checks.append(_chk("CP-10", "fail" if truth["sanctions_hit"] else "pass"))
    checks.append(_chk("CP-11", "exception" if truth["adverse_severity"] in ref["adverse_media_exception_levels"] else "pass"))
    checks.append(_chk("CP-12", "pass" if finance.grade_at_most(g["grade"], ref["worst_acceptable_grade"]) else "fail"))

    rec = derive_recommendation(checks)
    tier = required_tier(truth["loan_amount"], ref["authority"], any(c["status"] == "exception" for c in checks))
    return {"policy_id": ref["policy_id"], "ratios": ratios, "scorecard": sc, "grade": g, "checks": checks,
            "recommendation": rec, "required_tier": tier}
