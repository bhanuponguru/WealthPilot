"""E1: financial-document parsing accuracy on clean / noisy-layout / scanned (image-only) documents.

Arms: rule-based baseline (oracle label dictionary), baseline (canonical labels only), LLM on raw text, LLM on
layout-reconstructed text, LLM + layout + reconciliation repair. Scanned docs go through the NIM vision model for LLM arms
(the baselines cannot read them). Metric: field-level accuracy (|err| <= 0.1%), Wilson 95% CI, doc-level exact rate,
and how often reconciliation flags a document that has at least one wrong field.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from common import log_mlflow, md_table, save, wilson
from wealthpilot_lab.synth.applicants import load
from wealthpilot_lab.synth.render_docs import ALL_FIELDS, DOCS_DIR

from wealthpilot.nim import run_tag
from wealthpilot.parsing.pipeline import (
    baseline_extract,
    extract_bank,
    extract_statements,
    parse_financials,
    reconcile,
    reconcile_bank,
)

VARIANTS = ["clean", "noisy", "scanned"]
ARMS = ["baseline_oracle", "baseline_canonical", "llm_raw", "llm_layout", "llm_layout_repair"]


def field_hits(pred: dict, truth: dict) -> tuple[int, int, list]:
    ok = tot = 0
    wrong = []
    for y, row in truth.items():
        for f in ALL_FIELDS:
            tot += 1
            v = (pred.get(y) or {}).get(f)
            if v is not None and abs(v - row[f]) <= max(1.0, 0.001 * abs(row[f])):
                ok += 1
            else:
                wrong.append((y, f))
    return ok, tot, wrong


def run_arm(arm: str, path: Path) -> tuple[dict, dict]:
    """Returns (predicted statements, extra info)."""
    if arm == "baseline_oracle":
        return baseline_extract(path, True), {}
    if arm == "baseline_canonical":
        return baseline_extract(path, False), {}
    if arm == "llm_raw":
        return extract_statements(path, use_layout=False), {}
    if arm == "llm_layout":
        st = extract_statements(path)
        return st, {"recon_issues": len(reconcile(st))}
    r = parse_financials(path, repair=True)
    return r["statements"], {"recon_issues": len(r["issues"]), "repaired": r["repaired"]}


def one(job):
    a, variant, arm = job
    path = DOCS_DIR / a["case_id"] / variant / "financials.pdf"
    t0 = time.time()
    try:
        with run_tag(f"e1-{arm}-{variant}-{a['case_id']}"):
            pred, info = run_arm(arm, path)
        ok, tot, wrong = field_hits(pred, a["statements"])
        err = None
    except Exception as e:  # noqa: BLE001
        ok, tot, wrong, info, err = 0, sum(len(r) for r in a["statements"].values()) and len(a["statements"]) * len(ALL_FIELDS), [], {}, f"{type(e).__name__}: {str(e)[:100]}"
    return {"case": a["case_id"], "variant": variant, "arm": arm, "ok": ok, "tot": tot, "exact": ok == tot, "wrong": wrong[:8], "secs": round(time.time() - t0, 1), "error": err, **info}


def bank_job(job):
    a, variant = job
    path = DOCS_DIR / a["case_id"] / variant / "bank_statement.pdf"
    try:
        with run_tag(f"e1-bank-{variant}-{a['case_id']}"):
            b = extract_bank(path)
        truth = {m["month"]: m for m in a["bank"]["months"]}
        ok = sum(1 for m in b["months"] if m["month"] in truth and all(abs((m.get(k) or -1e9) - truth[m["month"]][k]) <= 1 for k in ("opening", "deposits", "withdrawals", "closing")))
        return {"case": a["case_id"], "variant": variant, "months_ok": ok, "months": 12, "flagged": len(reconcile_bank(b)), "error": None}
    except Exception as e:  # noqa: BLE001
        return {"case": a["case_id"], "variant": variant, "months_ok": 0, "months": 12, "flagged": 0, "error": type(e).__name__}


def main(n_cases: int = 16, workers: int = 4) -> dict:
    apps = load()[::5][:n_cases]  # every 5th applicant, deterministic
    jobs = [(a, v, arm) for a in apps for v in VARIANTS for arm in ARMS]
    # baselines are free (no LLM); run LLM arms with limited parallelism
    with ThreadPoolExecutor(workers) as ex:
        rows = list(ex.map(one, jobs))
        bank_rows = list(ex.map(bank_job, [(a, v) for a in apps for v in VARIANTS]))
    table = []
    for v in VARIANTS:
        for arm in ARMS:
            rs = [r for r in rows if r["variant"] == v and r["arm"] == arm]
            ok, tot = sum(r["ok"] for r in rs), sum(r["tot"] for r in rs)
            lo, hi = wilson(ok, tot)
            flagged = [r for r in rs if not r["exact"] and r.get("recon_issues", 0) > 0]
            wrong_docs = [r for r in rs if not r["exact"]]
            table.append({"variant": v, "arm": arm, "docs": len(rs), "field_acc": round(ok / tot, 4) if tot else 0, "CI95": f"{lo}-{hi}",
                          "doc_exact": f"{sum(r['exact'] for r in rs)}/{len(rs)}", "wrong_docs_flagged_by_recon": f"{len(flagged)}/{len(wrong_docs)}" if "recon_issues" in (rs[0] if rs else {}) else "-",
                          "errors": sum(1 for r in rs if r["error"]), "avg_secs": round(sum(r["secs"] for r in rs) / max(1, len(rs)), 1)})
    bank_table = []
    for v in VARIANTS:
        rs = [r for r in bank_rows if r["variant"] == v]
        ok, tot = sum(r["months_ok"] for r in rs), sum(r["months"] for r in rs)
        bank_table.append({"variant": v, "docs": len(rs), "month_rows_correct": f"{ok}/{tot}", "acc": round(ok / tot, 4), "CI95": "-".join(map(str, wilson(ok, tot))), "errors": sum(1 for r in rs if r["error"])})
    md = "# E1: Document parsing\n\n## Financial statements (field-level)\n" + md_table(table, ["variant", "arm", "docs", "field_acc", "CI95", "doc_exact", "wrong_docs_flagged_by_recon", "errors", "avg_secs"]) \
        + "\n## Bank statements (monthly rows)\n" + md_table(bank_table, ["variant", "docs", "month_rows_correct", "acc", "CI95", "errors"])
    save("e1_parsing", {"table": table, "bank": bank_table, "rows": rows}, md)
    for t in table:
        log_mlflow("wealthpilot-E1-parsing", f"{t['variant']}/{t['arm']}", {"variant": t["variant"], "arm": t["arm"]}, {"field_acc": t["field_acc"], "avg_secs": t["avg_secs"]})
    print(md)
    return {"table": table}


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 16)
