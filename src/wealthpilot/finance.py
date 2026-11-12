"""Deterministic credit math shared by the fincalc MCP server, the reference
policy engine and the tests. The LLM never does arithmetic: it calls these."""

from __future__ import annotations

ASSUMED_RATE = 0.09  # proposed-loan interest rate used in DSCR (stated in every policy's Definitions)


def _div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return a / b


def amortized_payment(principal: float, annual_rate: float, months: int) -> float:
    """Level monthly payment."""
    r = annual_rate / 12
    if months <= 0:
        raise ValueError("months must be positive")
    if r == 0:
        return principal / months
    return principal * r / (1 - (1 + r) ** -months)


def proposed_annual_debt_service(loan_amount: float, term_months: int, rate: float = ASSUMED_RATE) -> float:
    return 12 * amortized_payment(loan_amount, rate, term_months)


def compute_ratios(
    fs: dict,
    loan_amount: float,
    term_months: int,
    collateral_value: float | None = None,
    rate: float = ASSUMED_RATE,
) -> dict:
    """Ratios from ONE fiscal year's statements `fs` (latest year) plus the loan request.

    DSCR = (net income + interest expense + depreciation) /
           (interest expense + current portion of LTD + annual payment on the proposed loan)
    """
    ebitda_like = fs["net_income"] + fs["interest_expense"] + fs["depreciation"]
    service = fs["interest_expense"] + fs["current_portion_ltd"] + proposed_annual_debt_service(loan_amount, term_months, rate)
    gross_profit = fs["revenue"] - fs["cogs"]
    return {
        "cash_flow_available": round(ebitda_like, 2),
        "debt_service": round(service, 2),
        "dscr": _round(_div(ebitda_like, service)),
        "debt_to_equity": _round(_div(fs["total_liabilities"], fs["total_equity"])),
        "current_ratio": _round(_div(fs["total_current_assets"], fs["total_current_liabilities"])),
        "loan_to_revenue": _round(_div(loan_amount, fs["revenue"])),
        "collateral_coverage": _round(_div(collateral_value, loan_amount)) if collateral_value is not None else None,
        "gross_margin": _round(_div(gross_profit, fs["revenue"])),
        "net_margin": _round(_div(fs["net_income"], fs["revenue"])),
    }


def _round(x: float | None, nd: int = 4) -> float | None:
    return None if x is None else round(x, nd)


def trend(values: list[float]) -> dict:
    """Year-over-year growth for an ordered (oldest -> newest) series."""
    growth = [_round(_div(b - a, abs(a))) for a, b in zip(values, values[1:])]
    direction = "flat"
    valid = [g for g in growth if g is not None]
    if valid and all(g > 0.02 for g in valid):
        direction = "improving"
    elif valid and all(g < -0.02 for g in valid):
        direction = "declining"
    return {"yoy_growth": growth, "direction": direction}


def stress_test(fs: dict, loan_amount: float, term_months: int, revenue_drop: float = 0.10, rate: float = ASSUMED_RATE) -> dict:
    """DSCR if revenue falls by `revenue_drop`, losing gross margin on the lost sales."""
    gm = _div(fs["revenue"] - fs["cogs"], fs["revenue"]) or 0.0
    lost = fs["revenue"] * revenue_drop * gm
    stressed = dict(fs, net_income=fs["net_income"] - lost)
    return {"revenue_drop": revenue_drop, "stressed_dscr": compute_ratios(stressed, loan_amount, term_months, None, rate)["dscr"]}


def compare(value: float | None, op: str, threshold: float) -> dict:
    """Numeric comparison used by the policy agent. op in >=, <=, >, <, ==."""
    if value is None:
        return {"result": None, "reason": "missing_data"}
    ops = {">=": value >= threshold, "<=": value <= threshold, ">": value > threshold, "<": value < threshold, "==": value == threshold}
    if op not in ops:
        raise ValueError(f"unsupported operator {op!r}")
    return {"result": bool(ops[op]), "reason": None}


# ---- risk methodology (fixed bank methodology, NOT part of the credit policy) ----
# Bands are set relative to the SBA model's scale (5-year default base rate ~4%; synthetic applicants span ~0.1%-7%).
PD_BANDS = [(0.020, "low"), (0.035, "moderate"), (0.045, "elevated"), (1.01, "high")]
GRADES = ["A", "B", "C", "D", "E"]


def pd_band(pd: float) -> str:
    for ub, name in PD_BANDS:
        if pd < ub:
            return name
    return "high"


def scorecard(ratios: dict, min_dscr: float, max_debt_to_equity: float, min_current_ratio: float) -> dict:
    """Pass/fail on the three core ratios using thresholds supplied by the caller
    (the policy agent extracts them from the policy text)."""
    tests = {
        "dscr": ratios.get("dscr") is not None and ratios["dscr"] >= min_dscr,
        "debt_to_equity": ratios.get("debt_to_equity") is not None and 0 <= ratios["debt_to_equity"] <= max_debt_to_equity,
        "current_ratio": ratios.get("current_ratio") is not None and ratios["current_ratio"] >= min_current_ratio,
    }
    n = sum(tests.values())
    klass = "strong" if n == 3 else "adequate" if n == 2 else "weak"
    return {"tests": tests, "passed": n, "class": klass}


def grade(pd: float, scorecard_class: str) -> dict:
    band = pd_band(pd)
    idx = [b for _, b in PD_BANDS].index(band) + {"strong": 0, "adequate": 1, "weak": 2}[scorecard_class]
    return {"pd_band": band, "scorecard_class": scorecard_class, "grade": GRADES[min(idx, 4)]}


def grade_at_most(g: str, worst_acceptable: str) -> bool:
    return GRADES.index(g) <= GRADES.index(worst_acceptable)
