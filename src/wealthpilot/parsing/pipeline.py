"""Financial-document parsing: text layer or vision model -> LLM structured extraction -> reconciliation -> repair.

Also contains a rule-based baseline (regex + label dictionary) used as the E1 comparison arm.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pymupdf
from langchain_core.messages import HumanMessage, SystemMessage

from ..nim import get_chat, get_vlm
from .fields import ALL_FIELDS, IS_FIELDS, LABELS

FIELD_HELP = {
    "revenue": "total sales / revenue", "cogs": "cost of goods sold / cost of sales / direct costs",
    "operating_expenses": "operating expenses (SG&A, overheads); NOT depreciation, interest or tax",
    "depreciation": "depreciation (and amortization)", "interest_expense": "interest expense / finance costs",
    "income_tax": "income tax / provision for taxes", "net_income": "net income / net profit / profit after tax",
    "cash": "cash and cash equivalents", "accounts_receivable": "accounts / trade receivables", "inventory": "inventory / stock",
    "total_current_assets": "total current assets", "net_fixed_assets": "net fixed assets / property, plant & equipment (net)",
    "total_assets": "total assets", "accounts_payable": "accounts / trade payables", "current_portion_ltd": "current portion of long-term debt / debt due within one year",
    "total_current_liabilities": "total current liabilities", "long_term_debt": "long-term (non-current) debt, excluding the current portion",
    "total_liabilities": "total liabilities", "total_equity": "total equity / shareholders' / owner's equity / net worth",
}

SYSTEM = ("You extract numbers from small-business financial statements. Reply with ONLY one JSON object, no prose. "
          "Numbers are plain integers in US dollars: remove $ and commas; parentheses or a leading minus mean negative. "
          "Use null for a field that does not appear. Do not compute or infer values; copy what is printed.")


def _prompt(fields: list[str], extra: str = "") -> str:
    spec = "\n".join(f"- {f}: {FIELD_HELP[f]}" for f in fields)
    return (f"Extract these fields for EACH fiscal year column in the statements.\n{spec}\n\n"
            'Return JSON exactly like {"years": {"2024": {"revenue": 123, ...}, "2023": {...}}}. '
            "The year key is the 4-digit fiscal year from the column header. Columns may be ordered newest-first or "
            "oldest-first and differently on each page: assign each number to the year printed above ITS OWN column, "
            f"never by position.{extra}")


# --------------------------------------------------------------------- JSON helpers
def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text)
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON")


def llm_json(llm, messages: list, retries: int = 1) -> dict:
    """Invoke, parse JSON; on malformed output ask once for a corrected object."""
    msgs = list(messages)
    last = None
    for _ in range(retries + 1):
        out = llm.invoke(msgs)
        try:
            return _extract_json(out.content if isinstance(out.content, str) else str(out.content))
        except Exception as e:  # noqa: BLE001
            last = e
            msgs = msgs + [out, HumanMessage(content=f"That was not valid JSON ({e}). Reply with ONLY the corrected JSON object.")]
    raise ValueError(f"LLM did not return valid JSON: {last}")


# --------------------------------------------------------------------- reading documents
def read_pdf(path: Path) -> dict:
    """{'kind': 'text'|'image', 'text': str, 'images': [png bytes per page]}"""
    doc = pymupdf.open(path)
    text = "\n\n".join(p.get_text() for p in doc)
    if len(text.strip()) > 40:
        return {"kind": "text", "text": text, "images": []}
    return {"kind": "image", "text": "", "images": [p.get_pixmap(dpi=110).tobytes("png") for p in doc]}


_NUMTOK = re.compile(r"^[\(\-]*\$?[\(\-]*[\d,]+\.?\d*\)?$")


def layout_text(path: Path) -> str:
    """Rebuild tables from word coordinates so each row states its values BY YEAR ("Revenue: FY2023=1,000; FY2024=1,100").
    Deterministic; removes the column-order ambiguity that made the LLM swap years on mixed-format headers."""
    out = []
    for page in pymupdf.open(path):
        rows: dict[int, list] = {}
        for x0, y0, x1, _y1, w, *_ in page.get_text("words"):
            rows.setdefault(round(y0 / 3), []).append((x0, x1, w))
        anchors: list[tuple[float, str]] = []
        for _, r in sorted(rows.items()):
            r.sort()
            text = " ".join(w for _, _, w in r)
            years = [(x1, m.group(1)) for _x0, x1, w in r if (m := re.fullmatch(r"(?:FY)?(20\d\d),?", w))] \
                if re.match(r"^(FY|Year ended)", text) else []
            if years:
                anchors = years
                out.append("Columns: " + ", ".join(f"FY{y}" for _, y in anchors))
                continue
            nums = [(x1, w) for _x0, x1, w in r if _NUMTOK.match(w) and anchors and any(abs(x1 - ax) < 30 for ax, _ in anchors)]
            if nums:
                label = " ".join(w for _x0, _x1, w in r if (_x1, w) not in nums)
                cells = []
                for x1, w in nums:
                    ay = min(anchors, key=lambda a: abs(a[0] - x1))[1]
                    cells.append(f"FY{ay}={w}")
                out.append(f"{label}: " + "; ".join(cells))
            else:
                out.append(text)
        out.append("")
    return "\n".join(out)


def _img_msg(prompt: str, png: bytes) -> HumanMessage:
    b64 = base64.b64encode(png).decode()
    return HumanMessage(content=[{"type": "text", "text": prompt},
                                 {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}])


def _clean_years(obj: dict, fields: list[str]) -> dict[str, dict]:
    out = {}
    for y, row in (obj.get("years") or {}).items():
        ys = re.search(r"(20\d\d)", str(y))
        if not ys or not isinstance(row, dict):
            continue
        out[ys.group(1)] = {f: _num(row.get(f)) for f in fields}
    return out


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    neg = s.startswith("(") or s.startswith("-")
    digits = re.sub(r"[^0-9.]", "", s)
    if not digits:
        return None
    x = float(digits)
    return -x if neg else x


def extract_statements(path: Path, extra: str = "", use_layout: bool = True, redact=None) -> dict[str, dict]:
    """LLM extraction of all 19 statement fields per fiscal year. Text layer -> chat model; scans -> vision model.
    `redact` (callable str->str) is applied to document text before it is sent to the LLM."""
    doc = read_pdf(path)
    if doc["kind"] == "text":
        body = layout_text(path) if use_layout else doc["text"]
        body = redact(body) if redact else body
        msgs = [SystemMessage(content=SYSTEM), HumanMessage(content=_prompt(ALL_FIELDS, extra) + "\n\nDOCUMENT TEXT:\n" + body)]
        return _clean_years(llm_json(get_chat(max_tokens=2500), msgs), ALL_FIELDS)
    merged: dict[str, dict] = {}
    vlm = get_vlm(max_tokens=2500)
    for png in doc["images"]:  # one statement per page: ask for all fields, keep what is present
        msgs = [SystemMessage(content=SYSTEM), _img_msg(_prompt(ALL_FIELDS, extra) + "\nThis page may contain only the income statement or only the balance sheet; use null for fields not on this page.", png)]
        for y, row in _clean_years(llm_json(vlm, msgs), ALL_FIELDS).items():
            cur = merged.setdefault(y, {f: None for f in ALL_FIELDS})
            for f, v in row.items():
                if v is not None and cur[f] is None:
                    cur[f] = v
    return merged


def extract_bank(path: Path, redact=None) -> dict:
    doc = read_pdf(path)
    if redact and doc["kind"] == "text":
        doc["text"] = redact(doc["text"])
    prompt = ('Extract the monthly summary table. Return JSON: {"account_holder": str, "signatory": str, "months": '
              '[{"month": "2024-01", "opening": int, "deposits": int, "withdrawals": int, "closing": int}]}. Numbers as plain integers.')
    if doc["kind"] == "text":
        obj = llm_json(get_chat(max_tokens=2500), [SystemMessage(content=SYSTEM), HumanMessage(content=prompt + "\n\nDOCUMENT TEXT:\n" + doc["text"])])
    else:
        obj = llm_json(get_vlm(max_tokens=2500), [SystemMessage(content=SYSTEM), _img_msg(prompt, doc["images"][0])])
    obj["months"] = [{k: (_num(v) if k != "month" else v) for k, v in m.items()} for m in obj.get("months", []) if isinstance(m, dict)]
    return obj


# --------------------------------------------------------------------- reconciliation
def _close(a, b, rel=0.001, absol=2.0) -> bool:
    return abs(a - b) <= max(absol, rel * max(abs(a), abs(b)))


def reconcile(statements: dict[str, dict]) -> list[dict]:
    """Deterministic consistency checks per fiscal year. Returns issues (empty list = consistent)."""
    issues = []
    for y, s in sorted(statements.items()):
        def need(*fs):
            return all(s.get(f) is not None for f in fs)

        def chk(name, lhs, rhs, fields):
            if not _close(lhs, rhs):
                issues.append({"year": y, "check": name, "expected": round(rhs), "actual": round(lhs), "fields": fields})
        missing = [f for f in ALL_FIELDS if s.get(f) is None]
        if missing:
            issues.append({"year": y, "check": "missing_fields", "fields": missing})
        if need("total_assets", "total_liabilities", "total_equity"):
            chk("assets = liabilities + equity", s["total_assets"], s["total_liabilities"] + s["total_equity"], ["total_assets", "total_liabilities", "total_equity"])
        if need("total_current_assets", "cash", "accounts_receivable", "inventory"):
            chk("current assets = cash + AR + inventory", s["total_current_assets"], s["cash"] + s["accounts_receivable"] + s["inventory"], ["total_current_assets", "cash", "accounts_receivable", "inventory"])
        if need("total_assets", "total_current_assets", "net_fixed_assets"):
            chk("total assets = current + fixed", s["total_assets"], s["total_current_assets"] + s["net_fixed_assets"], ["total_assets", "total_current_assets", "net_fixed_assets"])
        if need("total_current_liabilities", "accounts_payable", "current_portion_ltd"):
            chk("current liabilities = AP + current LTD", s["total_current_liabilities"], s["accounts_payable"] + s["current_portion_ltd"], ["total_current_liabilities", "accounts_payable", "current_portion_ltd"])
        if need("total_liabilities", "total_current_liabilities", "long_term_debt"):
            chk("liabilities = current + long-term", s["total_liabilities"], s["total_current_liabilities"] + s["long_term_debt"], ["total_liabilities", "total_current_liabilities", "long_term_debt"])
        if need(*IS_FIELDS):
            chk("net income = revenue - costs - tax", s["net_income"], s["revenue"] - s["cogs"] - s["operating_expenses"] - s["depreciation"] - s["interest_expense"] - s["income_tax"], IS_FIELDS)
    return issues


def reconcile_bank(bank: dict) -> list[dict]:
    issues, months = [], bank.get("months", [])
    for m in months:
        if all(m.get(k) is not None for k in ("opening", "deposits", "withdrawals", "closing")) and not _close(m["closing"], m["opening"] + m["deposits"] - m["withdrawals"]):
            issues.append({"month": m["month"], "check": "closing = opening + deposits - withdrawals"})
    for a, b in zip(months, months[1:]):
        if a.get("closing") is not None and b.get("opening") is not None and not _close(a["closing"], b["opening"]):
            issues.append({"month": b["month"], "check": "opening = previous closing"})
    return issues


def parse_financials(path: Path, repair: bool = True, redact=None) -> dict:
    """Full pipeline for one financial-statements PDF. Returns statements + issues + whether a repair was attempted."""
    st = extract_statements(path, redact=redact)
    issues = reconcile(st)
    repaired = False
    if issues and repair:
        note = "\n\nA consistency check found problems in your previous answer:\n" + "\n".join(
            f"- FY{i['year']}: {i['check']} (fields {i.get('fields')})" for i in issues) + \
            "\nRe-read the document carefully for those values and return the full corrected JSON."
        st2 = extract_statements(path, extra=note, redact=redact)
        issues2 = reconcile(st2)
        repaired = True
        if len(issues2) <= len(issues):
            st, issues = st2, issues2
    return {"statements": st, "issues": issues, "repaired": repaired, "kind": read_pdf(path)["kind"]}


# --------------------------------------------------------------------- rule-based baseline (E1 arm)
_ALL_LABELS, _CANON_LABELS = {}, {}
for _f, (_clean, _syn) in LABELS.items():
    _CANON_LABELS[re.sub(r"[^a-z]", "", _clean.lower())] = _f
    for _l in [_clean] + _syn:
        _ALL_LABELS[re.sub(r"[^a-z]", "", _l.lower())] = _f
_NUM = re.compile(r"\(?-?\$?\(?[\d,]+\)?")


def baseline_extract(path: Path, oracle_synonyms: bool = True) -> dict[str, dict]:
    """Regex/label-dictionary parser. Blind to scans. With oracle_synonyms=True it knows every label variant the
    generator can emit (an unrealistically strong baseline); False = canonical labels only (realistic)."""
    labels = _ALL_LABELS if oracle_synonyms else _CANON_LABELS
    doc = read_pdf(path)
    if doc["kind"] != "text":
        return {}
    lines = [ln.strip() for ln in doc["text"].splitlines() if ln.strip()]
    out: dict[str, dict] = {}
    years: list[str] = []
    seen_label = False  # a new run of year headers after data rows means a new statement/page
    i = 0
    while i < len(lines):
        ln = lines[i]
        ys = re.findall(r"(20\d\d)", ln)
        if ys and re.match(r"^(FY|Year ended)", ln):
            if seen_label:
                years, seen_label = [], False
            years.append(ys[0])
        key = re.sub(r"[^a-z]", "", ln.lower())
        if key in labels and years:
            seen_label = True
            n = len(years)
            vals = []
            for j in range(i + 1, min(i + 1 + n, len(lines))):
                m = _NUM.fullmatch(lines[j].replace(" ", ""))
                if not m:
                    break
                vals.append(_num(lines[j]))
            if len(vals) == n:
                for y, v in zip(years[-n:], vals):
                    out.setdefault(y, {})[labels[key]] = v
                i += n
        i += 1
    return out
