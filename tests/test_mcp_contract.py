"""Contract tests: every MCP tool called through the real MultiServerMCPClient (servers must be running:
`uv run wealthpilot mcp-up`). Run: uv run pytest -m live tests/test_mcp_contract.py"""

import pytest

from wealthpilot import demo, finance
from wealthpilot.mcp_client import call, load_tools

pytestmark = pytest.mark.live
load = demo.applicants   # the sample applicants (demonstration data)


@pytest.fixture(scope="module")
async def tools():
    return await load_tools()


async def test_tool_inventory(tools):
    expected = {"compute_ratios", "amortize", "trend", "stress_test", "compare", "scorecard", "grade", "score_pd",
                "list_rules", "search_policy", "get_rule", "similar_precedents",
                "ofac_screen", "adverse_media", "registry_lookup", "industry_default_stats"}
    assert expected <= set(tools)


async def test_fincalc_matches_reference_math(tools):
    a = load()[0]
    latest = a["statements"][max(a["statements"])]
    got = await call(tools, "compute_ratios", statements=latest, loan_amount=a["loan_amount"], term_months=a["term_months"],
                     collateral_value=a["collateral_value"])
    want = finance.compute_ratios(latest, a["loan_amount"], a["term_months"], a["collateral_value"])
    assert got["dscr"] == pytest.approx(want["dscr"])
    assert (await call(tools, "compare", value=1.22, op=">=", threshold=1.30))["result"] is False
    assert (await call(tools, "compare", value=None, op=">=", threshold=1.30))["reason"] == "missing_data"
    g = await call(tools, "grade", pd=0.01, scorecard_class="strong")
    assert g["grade"] == "A"


async def test_score_pd(tools):
    a = load()[0]
    r = await call(tools, "score_pd", profile=a["profile"], loan_amount=a["loan_amount"], term_months=a["term_months"],
                   years_in_business=a["years_in_business"], naics=a["industry"]["naics"], has_collateral=a["collateral_value"] > 0)
    assert 0 < r["pd"] < 1 and r["pd_band"] in {"low", "moderate", "elevated", "high"}


async def test_policy_tools(tools):
    rules = (await call(tools, "list_rules", policy_id="strict"))["rules"]
    assert [r["rule_id"] for r in rules][:3] == ["CP-1", "CP-2", "CP-3"] and len(rules) == 13
    rule = await call(tools, "get_rule", policy_id="strict", rule_id="CP-3")
    assert "1.30" in rule["text"]
    res = await call(tools, "search_policy", query="minimum DSCR", policy_id="lenient", k=3)
    assert any("CP-3" in r["rule_ids"] for r in res["results"])
    assert "1.15" in next(r["text"] for r in res["results"] if "CP-3" in r["rule_ids"])


async def test_research_tools(tools):
    clean = await call(tools, "ofac_screen", name="Zzyzx Quillfeather")
    assert clean["match_count"] == 0
    planted = [a for a in load() if a["planted"]["sanctions_hit"]]
    if planted:
        a = planted[0]
        hit = await call(tools, "ofac_screen", name=a["owner_name"])
        assert hit["match_count"] >= 1 and hit["matches"][0]["list"] == "WATCHLIST"
    flagged = next(a for a in load() if a["planted"]["adverse_severity"] in ("medium", "high"))
    am = await call(tools, "adverse_media", subject=flagged["business_name"], owner=flagged["owner_name"])
    assert am["max_severity"] == flagged["planted"]["adverse_severity"]
    st = await call(tools, "industry_default_stats", naics2="72")
    assert st["n"] > 1000 and 0 < st["default_rate"] < 0.2
    reg = await call(tools, "registry_lookup", business_name=load()[0]["business_name"])
    assert reg["found"]
