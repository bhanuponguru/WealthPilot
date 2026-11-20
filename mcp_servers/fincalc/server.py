"""fincalc MCP server: deterministic credit math + PD model scoring. The LLM never does arithmetic."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from wealthpilot import finance
from wealthpilot.config import MCP_BIND
from wealthpilot.risk import pd_model

PORT = 8101
mcp = FastMCP("fincalc", host=MCP_BIND, port=PORT)


@mcp.tool()
def compute_ratios(statements: dict, loan_amount: float, term_months: int, collateral_value: float | None = None) -> dict:
    """Compute DSCR, debt_to_equity, current_ratio, loan_to_revenue, collateral_coverage and margins.

    `statements` is ONE fiscal year (the most recent) with keys: revenue, cogs, operating_expenses, depreciation,
    interest_expense, income_tax, net_income, total_current_assets, total_current_liabilities, current_portion_ltd,
    total_liabilities, total_equity. DSCR = (net income + interest + depreciation) / (interest + current portion of
    LTD + annual payment on the proposed loan at 9% over the term)."""
    return finance.compute_ratios(statements, loan_amount, term_months, collateral_value)


@mcp.tool()
def amortize(loan_amount: float, annual_rate: float, term_months: int) -> dict:
    """Monthly and annual payment for a level-payment loan (annual_rate as a fraction, e.g. 0.09)."""
    m = finance.amortized_payment(loan_amount, annual_rate, term_months)
    return {"monthly_payment": round(m, 2), "annual_payment": round(12 * m, 2)}


@mcp.tool()
def trend(values: list[float]) -> dict:
    """Year-over-year growth and direction for a series ordered oldest to newest (e.g. revenue by year)."""
    return finance.trend(values)


@mcp.tool()
def stress_test(statements: dict, loan_amount: float, term_months: int, revenue_drop: float = 0.10) -> dict:
    """DSCR if revenue falls by `revenue_drop` (fraction), losing gross margin on the lost sales."""
    return finance.stress_test(statements, loan_amount, term_months, revenue_drop)


@mcp.tool()
def compare(value: float | None, op: str, threshold: float) -> dict:
    """Numeric comparison. op is one of >=, <=, >, <, ==. Use this for every policy threshold check.
    Returns {'result': true|false|null, 'reason': 'missing_data' when value is null}."""
    return finance.compare(value, op, threshold)


@mcp.tool()
def scorecard(ratios: dict, min_dscr: float, max_debt_to_equity: float, min_current_ratio: float) -> dict:
    """Pass/fail on DSCR, leverage and liquidity using the thresholds you extracted from the policy text."""
    return finance.scorecard(ratios, min_dscr, max_debt_to_equity, min_current_ratio)


@mcp.tool()
def grade(pd: float, scorecard_class: str) -> dict:
    """Internal risk grade A-E from probability of default and scorecard class (strong|adequate|weak)."""
    return finance.grade(pd, scorecard_class)


@mcp.tool()
def score_pd(profile: dict, loan_amount: float, term_months: int, years_in_business: float, naics: str, has_collateral: bool) -> dict:
    """Probability of default (5-year horizon) from the SBA-trained model, with top risk-increasing reasons (SHAP).
    `profile` keys: state, business_type, fixed_or_variable, jobs_supported, franchise."""
    X = pd_model.applicant_features(profile, loan_amount, term_months, years_in_business, naics, has_collateral)
    out = pd_model.score(X)
    out["pd_band"] = finance.pd_band(out["pd"])
    return out


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
