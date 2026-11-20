"""Graph nodes. Six LLM agents (Parser, Financial Analyst, Credit Research, Risk, Policy/Compliance, Memo Writer)
plus deterministic gates. No LLM ever decides routing, does arithmetic, or sees protected attributes."""

from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from .. import decision, finance
from ..compliance import audit
from ..compliance.language_scan import scan
from ..compliance.redaction import Redactor, leaked_terms
from ..memory import precedents
from ..parsing.pipeline import (
    extract_bank,
    llm_json,
    parse_financials,
    reconcile,
    reconcile_bank,
)
from .runtime import ToolUnavailable, rt
from .state import CaseState

TIERS = ["Analyst", "Senior Credit Officer", "Credit Committee"]


def _t(step: str, **kw) -> dict:
    return {"trace": [{"step": step, "t": round(time.time(), 2), **kw}]}


def _degrade(reason: str) -> dict:
    return {"degraded": True, "degraded_reasons": [reason]}


# ===================================================================== intake (code)
async def intake(state: CaseState) -> dict:
    """Validate the application and load the applicant's prior decisions from long-term memory."""
    app = state["application"]
    for k in ("loan_amount", "term_months", "years_in_business", "industry_name"):
        if app.get(k) is None:
            return {"errors": [f"missing application field {k}"], **_t("intake", ok=False)}
    history = []
    if rt.store is not None:
        item = await rt.store.aget(("applicants",), state["applicant_id"])
        history = (item.value if item else {}).get("decisions", [])
    return {"history": history, "loops": {"policy": 0, "memo": 0, "revise": 0}, **_t("intake", prior_decisions=len(history))}


# ===================================================================== parse (Parser agent)
async def parse(state: CaseState) -> dict:
    red = Redactor(state["sealed"], enabled=state.get("redaction", True))
    paths = state["doc_paths"]
    try:
        fin = await asyncio.to_thread(parse_financials, Path(paths["financials"]), True, red)
    except Exception as e:  # noqa: BLE001
        return {"errors": [f"parse_financials: {type(e).__name__}: {str(e)[:150]}"], "extracted": {}, "reconciliation_issues": [{"check": "parse_failed"}],
                "bank": {}, "bank_issues": [], **_t("parse", ok=False)}
    bank, bank_issues = {}, []
    try:
        bank = await asyncio.to_thread(extract_bank, Path(paths["bank"]), red)
        bank_issues = reconcile_bank(bank)
    except Exception as e:  # noqa: BLE001
        bank_issues = [{"check": f"bank_parse_failed: {type(e).__name__}"}]
    return {"extracted": fin["statements"], "doc_kind": fin["kind"], "reconciliation_issues": fin["issues"], "bank": bank,
            "bank_issues": bank_issues, **_t("parse", years=sorted(fin["statements"]), issues=len(fin["issues"]), repaired=fin["repaired"], kind=fin["kind"])}


def route_after_parse(state: CaseState):
    if state.get("reconciliation_issues") or state.get("bank_issues"):
        return "doc_review"
    return ["analyst", "research"]


async def doc_review(state: CaseState) -> dict:
    """Human reviews unresolved document problems. Resume value: {action: accept|correct|reject, corrections: {fy: {field: value}}}."""
    d = interrupt({"type": "doc_review", "case_id": state["case_id"], "reconciliation_issues": state.get("reconciliation_issues"),
                   "bank_issues": state.get("bank_issues"), "extracted": state.get("extracted")})
    ext = {y: dict(v) for y, v in (state.get("extracted") or {}).items()}
    if d.get("action") == "correct":
        for y, fields in (d.get("corrections") or {}).items():
            ext.setdefault(str(y), {}).update(fields)
    return {"doc_review": d, "extracted": ext, "reconciliation_issues": reconcile(ext) if d.get("action") == "correct" else state.get("reconciliation_issues"),
            **_t("doc_review", action=d.get("action"))}


def route_after_review(state: CaseState):
    if (state.get("doc_review") or {}).get("action") == "reject":
        return "finalize"
    return ["analyst", "research"]


# ===================================================================== analyst (Financial Analyst agent)
NEEDED = ["revenue", "cogs", "net_income", "interest_expense", "depreciation", "current_portion_ltd", "total_liabilities",
          "total_equity", "total_current_assets", "total_current_liabilities"]


def _latest_statements(ext: dict, fill_from_prior: bool) -> tuple[dict | None, str | None, list[str]]:
    years = sorted(ext)
    if not years:
        return None, None, NEEDED
    latest = dict(ext[years[-1]])
    notes = []
    for f in NEEDED:
        if latest.get(f) is None and fill_from_prior:
            for y in reversed(years[:-1]):
                if ext[y].get(f) is not None:
                    latest[f] = ext[y][f]
                    notes.append(f"{f} taken from FY{y}")
                    break
    missing = [f for f in NEEDED if latest.get(f) is None]
    return latest, years[-1], missing + notes if missing else notes


async def _analyst(state: CaseState, fill_from_prior: bool) -> dict:
    a = state["application"]
    latest, fy, info = _latest_statements(state.get("extracted") or {}, fill_from_prior)
    missing = [i for i in info if " taken from " not in i]
    if latest is None or missing:
        return {"ratios": None, "analysis": {"missing": missing}, **_t("analyst", ok=False, missing=missing)}
    try:
        ratios = await rt.call("compute_ratios", statements=latest, loan_amount=a["loan_amount"], term_months=a["term_months"],
                               collateral_value=a.get("collateral_value"))
        years = sorted(state["extracted"])
        rev = await rt.call("trend", values=[state["extracted"][y].get("revenue") or 0 for y in years])
        stress = await rt.call("stress_test", statements=latest, loan_amount=a["loan_amount"], term_months=a["term_months"], revenue_drop=0.10)
    except ToolUnavailable as e:
        return {"ratios": None, "analysis": {"error": str(e)}, **_degrade(str(e)), **_t("analyst", ok=False, error=str(e))}
    narrative = ""
    try:  # agent writes the analysis; ratios above are authoritative (deterministic tool calls)
        agent = create_agent(rt.llm, tools=rt.agent_tools(["compute_ratios", "stress_test", "trend"]),
                             system_prompt="You are a credit analyst. Write a concise financial analysis (max 5 sentences) from the provided figures. "
                                           "Use only provided numbers; you may call tools for extra what-if checks. Never invent numbers.")
        res = await agent.ainvoke({"messages": [HumanMessage(content=json.dumps({"fiscal_year": fy, "ratios": ratios, "revenue_trend": rev, "stress_10pct_revenue_drop": stress,
                                                                                  "loan_amount": a["loan_amount"], "industry": a["industry_name"]}))]},
                                  config={"recursion_limit": 8})
        narrative = str(res["messages"][-1].content)
    except Exception as e:  # noqa: BLE001
        narrative = f"(narrative unavailable: {type(e).__name__})"
    return {"ratios": ratios, "analysis": {"fiscal_year": fy, "revenue_trend": rev, "stress": stress, "narrative": narrative, "estimated_fields": [i for i in info if " taken from " in i]},
            **_t("analyst", ok=True, dscr=ratios.get("dscr"))}


async def analyst(state: CaseState) -> dict:
    return await _analyst(state, fill_from_prior=False)


async def analyst_retry(state: CaseState) -> dict:
    """Policy found missing data: recompute ratios filling gaps from the prior year (flagged as estimated)."""
    out = await _analyst(state, fill_from_prior=True)
    out["loops"] = {**state["loops"], "policy": state["loops"].get("policy", 0) + 1}
    return out


# ===================================================================== research (Credit Research agent)
async def research(state: CaseState) -> dict:
    s, a = state["sealed"], state["application"]
    red = Redactor(s, enabled=state.get("redaction", True))
    out: dict = {"sanctions_status": "not_performed", "adverse_media_max_severity": None, "articles": [], "registry": None, "industry_default_rate": None}
    try:
        own, biz, media, reg, ind = await asyncio.gather(
            rt.call("ofac_screen", name=s["owner_name"]), rt.call("ofac_screen", name=s["business_name"]),
            rt.call("adverse_media", subject=s["business_name"], owner=s["owner_name"]),
            rt.call("registry_lookup", business_name=s["business_name"], state=s["address"]["state"]),
            rt.call("industry_default_stats", naics2=str(a["naics"])[:2]))
    except ToolUnavailable as e:
        return {"research": out, **_degrade(str(e)), **_t("research", ok=False, error=str(e))}
    except Exception as e:  # noqa: BLE001
        return {"research": out, **_degrade(f"research error {type(e).__name__}"), **_t("research", ok=False)}
    matches = (own.get("matches") or []) + (biz.get("matches") or [])
    best = max((m["score"] for m in matches), default=0)
    # code decides (the LLM never sees names): >=97 confirmed, 92-97 possible
    out["sanctions_status"] = "confirmed_match" if best >= 97 else "possible_match" if matches else "no_match"
    out["adverse_media_max_severity"] = media.get("max_severity")
    out["articles"] = [red(x["headline"]) for x in media.get("articles", [])]
    out["registry"] = reg
    out["industry_default_rate"] = ind.get("default_rate")
    summary = "No adverse findings."
    if out["articles"] or matches:
        try:
            msg = await rt.llm.ainvoke([SystemMessage(content="Summarise credit-relevant research findings in 2 sentences. Use only the given facts."),
                                        HumanMessage(content=json.dumps({"sanctions_status": out["sanctions_status"], "adverse_media": out["articles"],
                                                                         "max_severity": out["adverse_media_max_severity"]}))])
            summary = str(msg.content)
        except Exception:  # noqa: BLE001
            summary = "Adverse findings present (summary unavailable)."
    out["summary"] = summary
    return {"research": out, **_t("research", ok=True, sanctions=out["sanctions_status"], media=out["adverse_media_max_severity"])}


# ===================================================================== risk (Risk Scorer agent)
async def risk(state: CaseState) -> dict:
    a = state["application"]
    try:
        r = await rt.call("score_pd", profile=a["profile"], loan_amount=a["loan_amount"], term_months=a["term_months"],
                          years_in_business=a["years_in_business"], naics=str(a["naics"]), has_collateral=bool(a.get("collateral_value")))
    except ToolUnavailable as e:
        return {"risk": None, **_degrade(str(e)), **_t("risk", ok=False, error=str(e))}
    return {"risk": r, **_t("risk", pd=r["pd"], band=r["pd_band"])}


# ===================================================================== policy (Policy/Compliance agent, RAG)
def to_status(obj: dict) -> str:
    """Map the agent's three plain answers to a rule status (code, not the LLM, decides the label)."""
    if obj.get("applies") is False:
        return "not_applicable"
    if obj.get("exception") is True:
        return "exception"
    sat = obj.get("rule_satisfied")
    return "pass" if sat is True else "fail" if sat is False else "missing_data"


def case_facts(state: CaseState) -> dict:
    a, r = state["application"], state.get("ratios") or {}
    rs = state.get("research") or {}
    years = sorted(state.get("extracted") or {})
    f = {"business": a["business_label"], "industry": a["industry_name"], "years_in_business": a["years_in_business"], "loan_amount": a["loan_amount"],
         "term_months": a["term_months"], "purpose": a["purpose"], "collateral_value": a.get("collateral_value"), "personal_guarantee_provided": a.get("guarantor_provided"),
         "financial_statement_years_provided": len(years), "latest_fiscal_year": years[-1] if years else None,
         "ratios": {k: r.get(k) for k in ("dscr", "debt_to_equity", "current_ratio", "loan_to_revenue", "collateral_coverage")},
         "sanctions_screening": rs.get("sanctions_status", "not_performed"), "adverse_media_max_severity": rs.get("adverse_media_max_severity", "not_performed") if rs.get("sanctions_status") == "not_performed" else rs.get("adverse_media_max_severity") or "none"}
    if state.get("grade"):
        f["risk_grade"] = state["grade"]["grade"]
    return f


BATCH_SYS = """You are a credit policy analyst applying several rules of a bank's credit policy to ONE loan case.
Read each rule in the retrieved policy passages (they come from a search of the policy text) and apply it exactly as written to the case facts. Never rely on memory of the policy.
For EACH listed rule answer three plain questions about the CASE (not about the wording of the rule):
 - applies: does this rule's condition apply to this case? false if the rule only covers situations this case is not in (e.g. a collateral requirement for loans above a size this loan does not reach, or a guarantee that is not required for this loan).
 - rule_satisfied: is the case IN COMPLIANCE with the rule? true = compliant, false = it violates the rule, null = a needed fact is missing or was not performed. Careful with prohibition rules: a business that is NOT in a prohibited industry IS compliant (true).
 - exception: does the rule text define this situation as an exception to be referred to a committee (e.g. a finding at the stated severity, or a metric in the stated exception band with the stated extra condition met)? true or false.
Compare numbers carefully (e.g. 1.22 is LESS than 1.30). For EVERY numeric comparison you relied on (a case value against a number in the rule), list it in "comparisons" with your claim of whether it is true; a deterministic checker re-evaluates each one.
Reply with ONLY one JSON object keyed by rule id:
{"CP-1": {"applies": true, "rule_satisfied": true, "exception": false, "reason": "<one sentence>", "evidence": "<quote the decisive policy sentence and the case values>", "extracted_threshold": <main numeric pass threshold stated in the rule, or null>,
          "comparisons": [{"left": 132000, "op": ">", "right": 150000, "claimed_true": false}]}, "CP-2": {...}}"""


OPS = {"≥": ">=", "≤": "<=", "=": "==", "=>": ">=", "=<": "<="}


def wrong_comparisons(o) -> list[str]:
    """Re-evaluate every comparison the LLM listed; return human-readable descriptions of those it got wrong."""
    wrong = []
    for c in (o or {}).get("comparisons", []) if isinstance(o, dict) else []:
        try:
            left, right, op, claim = c["left"], c["right"], OPS.get(str(c["op"]).strip(), str(c["op"]).strip()), c["claimed_true"]
            if isinstance(left, bool) or isinstance(right, bool) or not isinstance(claim, bool):
                continue
            truth = finance.compare(float(left), op, float(right))["result"]
        except Exception:  # noqa: BLE001 - malformed comparison entries are ignored, not trusted
            continue
        if truth is not None and truth != claim:
            wrong.append(f"{left} {op} {right} is actually {str(truth).upper()}, you claimed {str(claim).upper()}")
    return wrong


async def _retrieve(policy_id: str, rule: dict) -> list[dict]:
    """RAG step through the policydocs MCP server (hybrid search + rerank); falls back to get_rule if the rule's own section is missing."""
    found = await rt.call("search_policy", query=rule["title"], policy_id=policy_id, k=3)
    res = found["results"]
    if not any(rule["rule_id"] in r["rule_ids"] for r in res):
        g = await rt.call("get_rule", policy_id=policy_id, rule_id=rule["rule_id"])
        if g.get("text"):
            res = res + [{"rule_ids": [rule["rule_id"]], "title": g["title"], "text": g["text"]}]
    return res


async def judge_batch(policy_id: str, rules: list[dict], facts: dict) -> list[dict]:
    """One LLM call for several rules. Retrieval per rule is done by code via MCP; the LLM reads passages and answers booleans."""
    bases = {r["rule_id"]: {"rule_id": r["rule_id"], "title": r["title"], "citation": f"{policy_id}/{r['rule_id']}"} for r in rules}

    def failed(reason: str, degraded: bool = False) -> list[dict]:
        return [{**b, "status": "missing_data", "reason": reason, "evidence": "", "extracted_threshold": None, **({"degraded": True} if degraded else {})} for b in bases.values()]
    try:
        retrieved = await asyncio.gather(*[_retrieve(policy_id, r) for r in rules])
    except ToolUnavailable as e:
        return failed(f"tool_unavailable: {e}", degraded=True)
    seen, passages = set(), []
    for res in retrieved:
        for p in res:
            if p["text"] not in seen:
                seen.add(p["text"])
                passages.append(f"[{', '.join(p['rule_ids']) or p['title']}]\n{p['text']}")
    user = ("Retrieved policy passages:\n" + "\n\n".join(passages) + "\n\nRules to judge: " + json.dumps([{"rule_id": r["rule_id"], "title": r["title"]} for r in rules])
            + "\n\nCase facts:\n" + json.dumps(facts))
    try:
        obj = await asyncio.to_thread(llm_json, rt.llm, [SystemMessage(content=BATCH_SYS), HumanMessage(content=user)])
    except Exception as e:  # noqa: BLE001
        return failed(f"agent_error: {type(e).__name__}: {str(e)[:120]}")
    # deterministic numeric verification: the LLM must not be trusted with arithmetic comparisons
    bad = {rid: wrong_comparisons(obj.get(rid)) for rid in bases}
    bad = {rid: w for rid, w in bad.items() if w}
    status_note = {rid: "ok" for rid in bases}
    if bad:
        fix = "A deterministic checker re-evaluated the numeric comparisons in your answer and found errors:\n" + "\n".join(
            f"- {rid}: {w}" for rid, w in bad.items()) + "\nRe-answer ONLY these rules (same JSON format, keyed by rule id), with correct comparisons."
        try:
            redo = await asyncio.to_thread(llm_json, rt.llm, [SystemMessage(content=BATCH_SYS), HumanMessage(content=user),
                                                              AIMessage(content=json.dumps(obj)), HumanMessage(content=fix)])
        except Exception:  # noqa: BLE001
            redo = {}
        for rid in bad:
            if isinstance(redo.get(rid), dict) and not wrong_comparisons(redo[rid]):
                obj[rid] = redo[rid]
                status_note[rid] = "repaired"
            else:
                obj[rid] = None
                status_note[rid] = "failed"
    out = []
    for rid, base in bases.items():
        o = obj.get(rid)
        if status_note[rid] == "failed":
            out.append({**base, "status": "missing_data", "reason": "numeric comparison inconsistent after re-check", "evidence": "", "extracted_threshold": None, "numeric_check": "failed"})
            continue
        if not isinstance(o, dict) or not any(k in o for k in ("applies", "rule_satisfied", "exception")):
            out.append({**base, "status": "missing_data", "reason": "no answer for this rule in the model reply", "evidence": "", "extracted_threshold": None, "numeric_check": "none"})
            continue
        thr = o.get("extracted_threshold")
        out.append({**base, "status": to_status(o), "reason": str(o.get("reason", ""))[:300], "evidence": str(o.get("evidence", ""))[:500],
                    "extracted_threshold": thr if isinstance(thr, (int, float)) and not isinstance(thr, bool) else None,
                    "numeric_check": status_note[rid] if o.get("comparisons") else "no_comparisons"})
    return out


async def _run_rules(state: CaseState, rules: list[dict], batch_size: int = 4) -> list[dict]:
    facts = case_facts(state)
    groups = [rules[i:i + batch_size] for i in range(0, len(rules), batch_size)]
    results = await asyncio.gather(*[judge_batch(state["policy_id"], g, facts) for g in groups])
    return [c for g in results for c in g]


async def policy(state: CaseState) -> dict:
    """Phase 1: every rule except CP-12 (needs the grade) and CP-13 (authority tier)."""
    try:
        rules = (await rt.call("list_rules", policy_id=state["policy_id"]))["rules"]
    except ToolUnavailable as e:
        return {"policy_checks": [], **_degrade(str(e)), **_t("policy", ok=False, error=str(e))}
    todo = [r for r in rules if r["rule_id"] not in ("CP-12", "CP-13")]
    checks = await _run_rules(state, todo)
    thr = {}
    for c in checks:
        if c["rule_id"] == "CP-3":
            thr["min_dscr"] = c["extracted_threshold"]
        elif c["rule_id"] == "CP-4":
            thr["max_debt_to_equity"] = c["extracted_threshold"]
        elif c["rule_id"] == "CP-5":
            thr["min_current_ratio"] = c["extracted_threshold"]
    out = {"policy_checks": checks, "thresholds": thr, **_t("policy", rules=len(checks), missing=sum(c["status"] == "missing_data" for c in checks))}
    if any(c.get("degraded") for c in checks):
        out.update(_degrade("policy tools unavailable"))
    return out


def route_after_policy(state: CaseState) -> str:
    missing = any(c["status"] == "missing_data" for c in state.get("policy_checks", []))
    return "analyst_retry" if missing and state["loops"].get("policy", 0) < 1 and state.get("extracted") else "grade"


async def grade(state: CaseState) -> dict:
    """Scorecard from the thresholds the policy agent extracted from prose, then the fixed grade matrix."""
    thr, ratios, rk = state.get("thresholds") or {}, state.get("ratios"), state.get("risk")
    if not (ratios and rk and all(thr.get(k) is not None for k in ("min_dscr", "max_debt_to_equity", "min_current_ratio"))):
        return {"grade": None, **_t("grade", ok=False)}
    try:
        sc = await rt.call("scorecard", ratios=ratios, **{k: thr[k] for k in ("min_dscr", "max_debt_to_equity", "min_current_ratio")})
        g = await rt.call("grade", pd=rk["pd"], scorecard_class=sc["class"])
    except ToolUnavailable as e:
        return {"grade": None, **_degrade(str(e)), **_t("grade", ok=False, error=str(e))}
    return {"grade": {**g, "scorecard": sc}, **_t("grade", grade=g["grade"], scorecard=sc["class"])}


async def approver_tier(policy_id: str, loan_amount: float, has_exception: bool) -> str | None:
    """CP-13: code fetches the rule text, the LLM only EXTRACTS the authority limits from the prose, code compares."""
    try:
        rule = await rt.call("get_rule", policy_id=policy_id, rule_id="CP-13")
        sysmsg = ("Extract the approval-authority limits from this credit policy rule. Reply ONLY with JSON "
                  '{"analyst_max": <largest loan amount in USD an Analyst may approve>, "officer_max": <largest loan amount in USD a Senior Credit Officer may approve>, '
                  '"exception_requires_committee": true|false}. Numbers are plain USD integers.')
        lim = await asyncio.to_thread(llm_json, rt.llm, [SystemMessage(content=sysmsg), HumanMessage(content=rule["text"])])
        a_max, o_max = float(lim["analyst_max"]), float(lim["officer_max"])
        if (has_exception and lim.get("exception_requires_committee", True)) or loan_amount > o_max:
            return "Credit Committee"
        return "Senior Credit Officer" if loan_amount > a_max else "Analyst"
    except Exception:  # noqa: BLE001
        return None


def final_recommendation(checks: list[dict], degraded: bool) -> str:
    rec = decision.derive_recommendation(checks)
    # A degraded run never auto-decides in EITHER direction: approving on incomplete checks is unsafe, and declining because a
    # tool was down (e.g. "sanctions screening not performed" read as a failure) would be an adverse action with no real basis
    # (E4 found 4 such wrongful declines before this cap).
    return "refer" if degraded and rec != "refer" else rec


async def policy2(state: CaseState) -> dict:
    """Phase 2: CP-12 (acceptable grade) and CP-13 (approver tier), then the fixed decision rule."""
    checks = list(state.get("policy_checks", []))
    try:
        rules = {r["rule_id"]: r for r in (await rt.call("list_rules", policy_id=state["policy_id"]))["rules"]}
    except ToolUnavailable as e:
        return {"recommendation": "refer", **_degrade(str(e)), **_t("policy2", ok=False)}
    if "CP-12" in rules:
        checks += await _run_rules(state, [rules["CP-12"]])
    tier = None
    has_exc = any(c["status"] == "exception" for c in checks)
    if "CP-13" in rules:
        tier = await approver_tier(state["policy_id"], state["application"]["loan_amount"], has_exc)
    if tier not in TIERS:
        tier = "Credit Committee"  # safe default when the tier cannot be determined
    degraded = bool(state.get("degraded")) or any(c.get("degraded") for c in checks)
    rec = final_recommendation(checks, degraded)
    return {"policy_checks": checks, "required_tier": tier, "recommendation": rec, **_t("policy2", recommendation=rec, tier=tier)}


# ===================================================================== memo (Memo Writer agent) + validator (code)
MEMO_SYS = """You are a credit memo writer at a bank. Write a structured credit memo as ONLY a JSON object:
{"recommendation": "approve|decline|refer", "summary": "3-4 sentences", "strengths": ["..."], "concerns": ["..."], "conditions": ["..."],
 "adverse_action_reasons": [{"rule_id": "CP-x", "reason": "plain-language principal reason"}], "limitations": ["..."]}
Rules: the recommendation MUST equal the given `recommendation` (it was derived by the bank's fixed decision rule; you explain it, you do not change it).
Use only numbers present in the provided facts. Cite rule ids (CP-x) only from the provided policy checks. adverse_action_reasons: only when the recommendation is decline,
one per failed rule, max 4, plain language. limitations: list any degraded tools or missing data, else an empty list.
Never mention or infer the owner's gender, race, ethnicity, age, religion, marital status or other personal characteristics; refer to the business, not people."""


def _collect(o, out: set) -> None:
    if isinstance(o, bool) or o is None:
        return
    if isinstance(o, (int, float)):
        for v in (o, round(o, 2), round(o, 3), round(o, 4), o * 100, round(o * 100, 1), o / 1000, o / 1e6):
            out.add(float(v))
    elif isinstance(o, dict):
        for v in o.values():
            _collect(v, out)
    elif isinstance(o, list):
        for v in o:
            _collect(v, out)


def allowed_numbers(state: CaseState) -> set:
    out: set = set()
    for k in ("application", "ratios", "risk", "analysis", "thresholds", "grade", "required_tier"):
        _collect(state.get(k), out)
    for y, row in (state.get("extracted") or {}).items():
        _collect(row, out)
        out.add(float(y))
    for c in state.get("policy_checks", []):
        _collect(c.get("extracted_threshold"), out)
    return out


NUM = re.compile(r"(?<![A-Za-z\-])\$?(\d[\d,]*\.?\d*)%?")


def unsupported_numbers(text: str, allowed: set) -> list[str]:
    text = re.sub(r"CP-\d+", "", text)
    text = re.sub(r"FY\s?\d{4}", "", text)
    bad = []
    for m in NUM.finditer(text):
        raw = m.group(1).rstrip(".,")
        try:
            x = float(raw.replace(",", ""))
        except ValueError:
            continue
        if x < 100 and "." not in raw:
            continue  # small integers (years, counts, 'top 3') are not checked
        if not any(abs(x - a) <= max(0.006 * abs(a), 0.006) for a in allowed):
            bad.append(m.group(0))
    return bad


def _memo_text(memo: dict) -> str:
    parts = []
    for v in memo.values():
        parts.append(json.dumps(v) if not isinstance(v, str) else v)
    return " ".join(parts)


async def memo(state: CaseState) -> dict:
    rk = state.get("risk") or {}
    facts = {"recommendation": state["recommendation"], "application": state["application"], "ratios": state.get("ratios"),
             "risk": {"pd": rk.get("pd"), "pd_band": rk.get("pd_band"), "main_risk_factors": rk.get("reasons")}, "grade": (state.get("grade") or {}).get("grade"),
             "policy_checks": [{k: c[k] for k in ("rule_id", "title", "status", "reason")} for c in state.get("policy_checks", [])],
             "required_approver": state.get("required_tier"), "research": {k: (state.get("research") or {}).get(k) for k in ("sanctions_status", "adverse_media_max_severity", "summary", "industry_default_rate")},
             "analysis": (state.get("analysis") or {}).get("narrative"), "prior_decisions_for_this_applicant": state.get("history"),
             "degraded_reasons": state.get("degraded_reasons")}
    try:
        sim = await rt.call("similar_precedents", summary=f"{state['application']['industry_name']} loan {state['application']['loan_amount']} grade {facts['grade']}", k=2)
        facts["similar_past_cases"] = [{k: p[k] for k in ("decision", "grade", "similarity")} for p in sim["precedents"]]
    except ToolUnavailable:
        facts["similar_past_cases"] = []
    extra = ""
    if state.get("validator_issues"):
        extra += "\nYour previous memo was rejected by validation. Fix these problems:\n- " + "\n- ".join(state["validator_issues"])
    hd = state.get("human_decision") or {}
    if hd.get("decision") == "revise":
        extra += f"\nThe reviewing officer requested a revision: {hd.get('reason', '')}"
    try:
        m = await asyncio.to_thread(llm_json, rt.llm, [SystemMessage(content=MEMO_SYS), HumanMessage(content="Facts:\n" + json.dumps(facts, default=str) + extra)])
    except Exception as e:  # noqa: BLE001
        m = {"recommendation": state["recommendation"], "summary": "Memo generation failed; manual review required.", "strengths": [], "concerns": [],
             "conditions": [], "adverse_action_reasons": [], "limitations": [f"memo generation failed: {type(e).__name__}"], "_failed": True}
    return {"memo": m, **_t("memo", attempt=state["loops"].get("memo", 0) + 1)}


async def memo_validator(state: CaseState) -> dict:
    m, issues = state["memo"], []
    if m.get("recommendation") != state["recommendation"]:
        issues.append(f"memo recommendation {m.get('recommendation')!r} differs from the decision-rule result {state['recommendation']!r}")
    valid_rules = {c["rule_id"] for c in state.get("policy_checks", [])}
    text = _memo_text(m)
    for rid in set(re.findall(r"CP-\d+", text)) - valid_rules - {"CP-13"}:
        issues.append(f"memo cites {rid}, which is not among the evaluated policy rules")
    bad = unsupported_numbers(text, allowed_numbers(state))
    if bad:
        issues.append("numbers not found in the case facts: " + ", ".join(sorted(set(bad))[:6]))
    terms = scan(text)
    if terms:
        issues.append("prohibited-basis language: " + ", ".join(terms))
    if state.get("redaction", True):
        leak = leaked_terms(text, state["sealed"])
        if leak:
            issues.append("memo contains identifying details: " + ", ".join(leak))
    if state["recommendation"] == "decline":
        failed = {c["rule_id"] for c in state["policy_checks"] if c["status"] == "fail"}
        reasons = m.get("adverse_action_reasons") or []
        if not reasons:
            issues.append("decline requires adverse_action_reasons")
        elif not {r.get("rule_id") for r in reasons} & failed:
            issues.append("adverse_action_reasons must cite failed rules")
    if state.get("degraded") and not m.get("limitations"):
        issues.append("run was degraded but memo lists no limitations")
    loops = dict(state["loops"])
    if issues:
        loops["memo"] = loops.get("memo", 0) + 1
    return {"validator_issues": issues, "loops": loops, **_t("memo_validator", issues=len(issues))}


def route_after_validator(state: CaseState) -> str:
    return "memo" if state.get("validator_issues") and state["loops"].get("memo", 0) <= 1 else "human_approval"


# ===================================================================== human approval (interrupt) + finalize
async def human_approval(state: CaseState) -> dict:
    payload = {"type": "approval", "case_id": state["case_id"], "recommendation": state["recommendation"], "required_tier": state.get("required_tier"),
               "memo": state["memo"], "policy_checks": state.get("policy_checks"), "ratios": state.get("ratios"), "risk": state.get("risk"),
               "grade": state.get("grade"), "research": state.get("research"), "degraded_reasons": state.get("degraded_reasons"),
               "validator_issues": state.get("validator_issues"), "error": None}
    need = TIERS.index(state.get("required_tier") or "Credit Committee")
    while True:
        d = interrupt(payload)
        tier = d.get("approver_tier")
        if d.get("decision") in ("approve", "decline", "revise") and tier in TIERS and TIERS.index(tier) >= need:
            break
        payload = {**payload, "error": f"approver tier {tier!r} is below the required tier {TIERS[need]!r}, or the decision is invalid"}
    loops = dict(state["loops"])
    if d["decision"] == "revise":
        loops["revise"] = loops.get("revise", 0) + 1
        loops["memo"] = 0
    return {"human_decision": d, "loops": loops, **_t("human_approval", decision=d["decision"], tier=tier)}


def route_after_approval(state: CaseState) -> str:
    d = state["human_decision"]
    return "memo" if d["decision"] == "revise" and state["loops"].get("revise", 0) <= 2 else "finalize"


async def finalize(state: CaseState) -> dict:
    d = state.get("human_decision") or {}
    rejected_docs = (state.get("doc_review") or {}).get("action") == "reject"
    decision = d.get("decision") or ("decline" if rejected_docs else "refer")
    if decision == "revise":  # revision budget exhausted: escalate instead of deciding
        decision = "refer"
    rec = state.get("recommendation")
    override = decision in ("approve", "decline") and rec in ("approve", "decline") and decision != rec
    final = {"case_id": state["case_id"], "policy_id": state["policy_id"], "recommendation": rec, "decision": decision, "override": override,
             "override_reason": d.get("reason") if override else None, "approver": d.get("approver_id"), "approver_tier": d.get("approver_tier"),
             "required_tier": state.get("required_tier"), "grade": (state.get("grade") or {}).get("grade"), "pd": (state.get("risk") or {}).get("pd"),
             "degraded": bool(state.get("degraded")), "degraded_reasons": state.get("degraded_reasons"), "documents_rejected": rejected_docs,
             "decided_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    if rt.store is not None:
        await rt.store.aput(("decisions",), state["case_id"], final)
        item = await rt.store.aget(("applicants",), state["applicant_id"])
        hist = (item.value if item else {}).get("decisions", []) + [{k: final[k] for k in ("case_id", "decision", "grade", "decided_at")}]
        await rt.store.aput(("applicants",), state["applicant_id"], {"decisions": hist})
    if state.get("memo") and not rejected_docs:
        try:
            summary = f"{state['application']['industry_name']} loan {state['application']['loan_amount']}; grade {final['grade']}; {state['memo'].get('summary', '')}"
            await asyncio.to_thread(precedents.add, state["case_id"], summary, decision, final["grade"] or "?")
        except Exception:  # noqa: BLE001
            pass
    await asyncio.to_thread(audit.append, state["case_id"], "decision", {**final, "policy_checks": [(c["rule_id"], c["status"]) for c in state.get("policy_checks", [])]})
    return {"final": final, **_t("finalize", decision=decision)}
