"""The fixed decision rule: how rule statuses become a recommendation, and who may approve."""

from __future__ import annotations

STATUSES = ("pass", "fail", "exception", "not_applicable", "missing_data")
RULE_IDS = [f"CP-{i}" for i in range(1, 13)]  # CP-13 (approval authority) is informational


def derive_recommendation(checks: list[dict]) -> str:
    """Any fail -> decline; otherwise any exception or missing data -> refer; otherwise approve."""
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        return "decline"
    if "exception" in statuses or "missing_data" in statuses:
        return "refer"
    return "approve"


def required_tier(loan_amount: float, authority: dict, has_exception: bool) -> str:
    """The lowest approval tier allowed to decide the case, given the policy's approval limits."""
    if has_exception or loan_amount > authority["officer_max"]:
        return "Credit Committee"
    if loan_amount > authority["analyst_max"]:
        return "Senior Credit Officer"
    return "Analyst"
