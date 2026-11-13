"""Pure (Streamlit-free) logic behind the console: application form validation, upload handling and memo export.

Kept separate from the page code so it can be unit-tested without a browser or any service.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from ..config import PROJECT_ROOT
from ..synth.applicants import INDUSTRIES, PROHIBITED, PURPOSES

UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
MAX_UPLOAD_MB = 25
MAX_PAGES = 40

#: every industry the system knows, as {name, tag, naics}; "tag" drives nothing in the agents (they read the industry NAME) but is kept for ground truth.
INDUSTRY_OPTIONS = [{"name": n, "tag": t, "naics": c} for n, t, c, *_ in [*INDUSTRIES, *PROHIBITED]]
OTHER_INDUSTRY = "Other (enter name and NAICS code)"
BUSINESS_TYPES = ["CORPORATION", "INDIVIDUAL", "PARTNERSHIP"]
RATE_TYPES = {"V": "Variable", "F": "Fixed"}
STATES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR GU VI").split()
PURPOSE_OPTIONS = [*PURPOSES, "other"]
TIERS = ["Analyst", "Senior Credit Officer", "Credit Committee"]


def new_case_id() -> str:
    """Unique id for an uploaded application, e.g. ``U20261113-142530``."""
    return "U" + time.strftime("%Y%m%d-%H%M%S")


def industry_by_name(name: str) -> dict | None:
    return next((i for i in INDUSTRY_OPTIONS if i["name"] == name), None)


def validate_application(form: dict) -> list[str]:
    """Return a list of human-readable problems; empty means the form can be submitted."""
    errs: list[str] = []
    for key, label in (("business_name", "Business name"), ("owner_name", "Principal owner name")):
        if not str(form.get(key, "")).strip():
            errs.append(f"{label} is required.")
    if form.get("owner_name") and " " not in form["owner_name"].strip():
        errs.append("Enter the owner's first and last name (the redactor matches both).")
    if not str(form.get("industry_name", "")).strip():
        errs.append("Industry is required.")
    naics = str(form.get("naics", "")).strip()
    if not re.fullmatch(r"\d{6}", naics):
        errs.append("NAICS code must be 6 digits.")
    if not (1000 <= float(form.get("loan_amount") or 0) <= 50_000_000):
        errs.append("Loan amount must be between $1,000 and $50,000,000.")
    if not (6 <= int(form.get("term_months") or 0) <= 360):
        errs.append("Term must be between 6 and 360 months.")
    if not (0 <= float(form.get("years_in_business") or 0) <= 150):
        errs.append("Years in business must be between 0 and 150.")
    if float(form.get("collateral_value") or 0) < 0:
        errs.append("Collateral value cannot be negative.")
    if not re.fullmatch(r"\d{5}", str(form.get("zip", "")).strip()):
        errs.append("ZIP code must be 5 digits.")
    if form.get("state") not in STATES:
        errs.append("Choose a state.")
    return errs


def build_applicant(form: dict, case_id: str) -> dict:
    """Turn a validated form into the applicant record `make_input_from_applicant` expects."""
    return {
        "case_id": case_id,
        "business_name": form["business_name"].strip(),
        "owner_name": form["owner_name"].strip(),
        "owner_gender": "unspecified",       # identity attributes the console never asks for
        "name_origin": "unspecified",
        "address": {"street": form.get("street", "").strip(), "city": form.get("city", "").strip(), "state": form["state"], "zip": str(form["zip"]).strip()},
        "industry": {"name": form["industry_name"].strip(), "naics": str(form["naics"]).strip(),
                     "tag": (industry_by_name(form["industry_name"]) or {}).get("tag", "other")},
        "years_in_business": float(form["years_in_business"]),
        "loan_amount": float(form["loan_amount"]),
        "term_months": int(form["term_months"]),
        "purpose": form.get("purpose", "other"),
        "collateral_value": float(form.get("collateral_value") or 0),
        "guarantor_provided": bool(form.get("guarantor_provided")),
        "profile": {"state": form["state"], "business_type": form.get("business_type", "CORPORATION"),
                    "fixed_or_variable": form.get("fixed_or_variable", "V"), "jobs_supported": int(form.get("jobs_supported") or 0),
                    "franchise": bool(form.get("franchise"))},
    }


def check_pdf(data: bytes, label: str) -> None:
    """Raise ValueError with a user-facing message if `data` is not a usable PDF."""
    import pymupdf

    if not data:
        raise ValueError(f"{label}: the file is empty.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise ValueError(f"{label}: larger than {MAX_UPLOAD_MB} MB.")
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{label}: not a readable PDF ({type(e).__name__}).") from e
    if doc.page_count == 0:
        raise ValueError(f"{label}: the PDF has no pages.")
    if doc.page_count > MAX_PAGES:
        raise ValueError(f"{label}: {doc.page_count} pages; the limit is {MAX_PAGES}.")


def save_uploads(case_id: str, financials: bytes, bank: bytes, root: Path = UPLOAD_DIR) -> dict:
    """Validate and store the two PDFs under ``data/uploads/<case_id>/``; return the ``doc_paths`` dict for the graph."""
    check_pdf(financials, "Financial statements")
    check_pdf(bank, "Bank statement")
    d = root / case_id
    d.mkdir(parents=True, exist_ok=True)
    fin, bk = d / "financials.pdf", d / "bank_statement.pdf"
    fin.write_bytes(financials)
    bk.write_bytes(bank)
    return {"financials": fin, "bank": bk}


# ---------------------------------------------------------------- exporting a case
def money(x) -> str:
    return "—" if x is None else f"${x:,.0f}"


def memo_to_markdown(state: dict) -> str:
    """A shareable credit memo in Markdown: header facts, memo sections, policy checklist, human decision. Contains no sealed identity."""
    v, m, app = state, state.get("memo") or {}, state.get("application") or {}
    final, hd = v.get("final") or {}, v.get("human_decision") or {}
    out = [f"# Credit memo — {v.get('case_id', '?')}", "",
           f"* **Business:** {app.get('business_label', '—')} ({app.get('industry_name', '—')})",
           f"* **Request:** {money(app.get('loan_amount'))} over {app.get('term_months', '—')} months — {app.get('purpose', '—')}",
           f"* **Policy:** {v.get('policy_id', '—')}",
           f"* **Recommendation:** {(v.get('recommendation') or '—').upper()}   |   **Risk grade:** {(v.get('grade') or {}).get('grade', '—')}   |   "
           f"**5-year PD:** {(v.get('risk') or {}).get('pd', '—')}   |   **Required approver:** {v.get('required_tier', '—')}"]
    if v.get("degraded"):
        out += ["", f"> **Degraded run** — recommendation capped at REFER. {'; '.join(v.get('degraded_reasons') or [])}"]
    out += ["", "## Summary", "", m.get("summary", "_No memo was generated._")]
    for title, key in (("Strengths", "strengths"), ("Concerns", "concerns"), ("Conditions", "conditions"), ("Limitations", "limitations")):
        if m.get(key):
            out += ["", f"## {title}", ""] + [f"- {x}" for x in m[key]]
    if m.get("adverse_action_reasons"):
        out += ["", "## Adverse-action reasons", ""] + [f"- ({r.get('rule_id')}) {r.get('reason')}" for r in m["adverse_action_reasons"]]
    if v.get("policy_checks"):
        out += ["", "## Policy checklist", "", "| Rule | Status | Reason |", "|---|---|---|"]
        out += [f"| {c['rule_id']} {c.get('title', '')} | {c['status']} | {str(c.get('reason', '')).replace('|', '/')} |" for c in v["policy_checks"]]
    if hd or final:
        out += ["", "## Human decision", "",
                f"* **Decision:** {final.get('decision') or hd.get('decision', '—')}" + ("  (**override**)" if final.get("override") else ""),
                f"* **Approver:** {final.get('approver') or hd.get('approver_id', '—')} ({final.get('approver_tier') or hd.get('approver_tier', '—')})",
                f"* **Reason:** {final.get('override_reason') or hd.get('reason') or '—'}"]
    return "\n".join(out) + "\n"


def evidence_json(state: dict) -> str:
    """The case state without the sealed identity block, for download."""
    return json.dumps({k: v for k, v in state.items() if k != "sealed"}, indent=2, default=str)


def parse_rules(policy_md: str) -> list[dict]:
    """Rules (`## CP-n Title`) of a policy document as [{rule_id, title, text}] — no database needed."""
    rules, cur = [], None
    for line in policy_md.splitlines():
        m = re.match(r"^## (CP-\d+)\s+(.*)$", line)
        if m:
            cur = {"rule_id": m.group(1), "title": m.group(2), "lines": []}
            rules.append(cur)
        elif line.startswith("## "):
            cur = None
        elif cur is not None:
            cur["lines"].append(line)
    return [{"rule_id": r["rule_id"], "title": r["title"], "text": " ".join(x.strip() for x in r["lines"] if x.strip())} for r in rules]
