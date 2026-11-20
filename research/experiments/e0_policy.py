"""E0: end-to-end policy adherence. The same cases are underwritten under a strict and a lenient policy; the agents must
read each policy's PROSE (the YAML answer key is hidden from them). Ground truth = the reference engine.

Reported: decision accuracy, per-rule status accuracy, threshold-extraction accuracy (did the agent read the right number
out of the text?), approver-tier accuracy, and 'policy flip agreement' (cases whose correct decision differs between the
two policies: did the system change its decision the same way?). Runs stop at the human-approval interrupt.

Set E0_NAME to write results under another name (e.g. a model comparison) instead of overwriting e0_policy.*
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from common import log_mlflow, md_table, save, wilson
from wealthpilot_lab.inputs import make_input
from wealthpilot_lab.reference_engine import load_reference
from wealthpilot_lab.synth.applicants import load
from wealthpilot_lab.synth.groundtruth import load_gt

from wealthpilot.graph.builder import session
from wealthpilot.nim import run_tag
from wealthpilot.nim.store import pool

POLICIES = ["strict", "lenient"]
THRESH = {"CP-1": "min_years_in_business", "CP-3": "min_dscr", "CP-4": "max_debt_to_equity", "CP-5": "min_current_ratio",
          "CP-6": "max_loan_to_revenue", "CP-7": "min_statement_years", "CP-8": "min_collateral_coverage"}
norm = lambda s: "pass" if s == "not_applicable" else s  # noqa: E731


def select_cases(gt: dict, n: int) -> list[str]:
    """Stratified, deterministic: policy-flip cases, both-decline, both-approve, anything involving refer."""
    ids = sorted(gt)
    flip = [c for c in ids if gt[c]["strict"]["recommendation"] != gt[c]["lenient"]["recommendation"]]
    both_dec = [c for c in ids if gt[c]["strict"]["recommendation"] == gt[c]["lenient"]["recommendation"] == "decline"]
    both_app = [c for c in ids if gt[c]["strict"]["recommendation"] == gt[c]["lenient"]["recommendation"] == "approve"]
    refer = [c for c in ids if "refer" in (gt[c]["strict"]["recommendation"], gt[c]["lenient"]["recommendation"]) and c not in flip]
    pick: list[str] = []
    for pool_, k in ((flip, n // 2), (both_dec, n // 5), (both_app, n // 5), (refer, n // 10)):
        pick += [c for c in pool_[:: max(1, len(pool_) // max(1, k))][:k] if c not in pick]
    for c in ids:  # top up
        if len(pick) >= n:
            break
        if c not in pick:
            pick.append(c)
    return pick[:n]


async def run_one(runner, a, policy, stamp, sem):
    async with sem:
        tag = f"e0-{policy}-{a['case_id']}"
        t0 = time.time()
        try:
            with run_tag(tag):
                snap = await runner.start(make_input(a, policy, "clean"), f"{tag}-{stamp}")
            return {"case": a["case_id"], "policy": policy, "values": snap["values"], "interrupt": (snap["interrupt"] or {}).get("type"), "secs": round(time.time() - t0, 1)}
        except Exception as e:  # noqa: BLE001
            return {"case": a["case_id"], "policy": policy, "values": {}, "interrupt": None, "error": f"{type(e).__name__}: {str(e)[:200]}", "secs": round(time.time() - t0, 1)}


def score(runs: list[dict], gt: dict) -> dict:
    per_policy, rule_rows, miss = {}, {}, []
    for pol in POLICIES:
        rs = [r for r in runs if r["policy"] == pol]
        ref = load_reference(pol)
        dec_ok = tier_ok = grade_ok = n = 0
        rule_ok = rule_n = thr_ok = thr_n = 0
        for r in rs:
            v, g = r["values"], gt[r["case"]][pol]
            n += 1
            dec_ok += v.get("recommendation") == g["recommendation"]
            tier_ok += v.get("required_tier") == g["required_tier"]
            grade_ok += (v.get("grade") or {}).get("grade") == g["grade"]["grade"]
            ag = {c["rule_id"]: c for c in v.get("policy_checks", [])}
            for rc in g["checks"]:
                a_ = ag.get(rc["rule_id"])
                ok = a_ is not None and norm(a_["status"]) == norm(rc["status"])
                rule_ok += ok
                rule_n += 1
                rr = rule_rows.setdefault(rc["rule_id"], [0, 0])
                rr[0] += ok
                rr[1] += 1
                if not ok:
                    miss.append({"policy": pol, "case": r["case"], "rule": rc["rule_id"], "agent": a_["status"] if a_ else None, "reference": rc["status"],
                                 "agent_reason": (a_ or {}).get("reason", "")[:140]})
                key = THRESH.get(rc["rule_id"])
                if key and a_ is not None and rc["status"] != "not_applicable":
                    thr_n += 1
                    t = a_.get("extracted_threshold")
                    thr_ok += t is not None and abs(t - ref[key]) <= max(1e-6, 0.005 * abs(ref[key]))
        per_policy[pol] = {"cases": n, "decision_acc": round(dec_ok / n, 3) if n else 0, "decision_CI95": wilson(dec_ok, n), "rule_acc": round(rule_ok / rule_n, 3) if rule_n else 0,
                           "rule_CI95": wilson(rule_ok, rule_n), "threshold_acc": round(thr_ok / thr_n, 3) if thr_n else 0, "tier_acc": round(tier_ok / n, 3) if n else 0,
                           "grade_acc": round(grade_ok / n, 3) if n else 0, "failed_runs": sum(1 for r in rs if r.get("error")), "degraded_runs": sum(1 for r in rs if r["values"].get("degraded")),
                           "avg_secs": round(sum(r["secs"] for r in rs) / max(1, n), 1)}
    # flip agreement
    flips = [c for c in {r["case"] for r in runs} if gt[c]["strict"]["recommendation"] != gt[c]["lenient"]["recommendation"]]
    agree = 0
    for c in flips:
        d = {r["policy"]: r["values"].get("recommendation") for r in runs if r["case"] == c}
        agree += d.get("strict") == gt[c]["strict"]["recommendation"] and d.get("lenient") == gt[c]["lenient"]["recommendation"]
    return {"per_policy": per_policy, "flip_cases": len(flips), "flip_agreement": round(agree / len(flips), 3) if flips else None, "flip_CI95": wilson(agree, len(flips)),
            "rule_accuracy": {k: f"{a}/{b}" for k, (a, b) in sorted(rule_rows.items(), key=lambda kv: int(kv[0][3:]))}, "mismatches": miss}


async def main(n_cases: int = 12, concurrency: int = 4) -> dict:
    gt, stamp = load_gt(), int(time.time())
    apps = {a["case_id"]: a for a in load()}
    cases = select_cases(gt, n_cases)
    print("cases:", cases, flush=True)
    sem = asyncio.Semaphore(concurrency)
    async with session() as runner:
        runs = await asyncio.gather(*[run_one(runner, apps[c], p, stamp, sem) for c in cases for p in POLICIES])
    res = score(runs, gt)
    with pool().connection() as c:  # LLM usage per run from the call log
        row = c.execute("select count(*), coalesce(sum(prompt_tokens),0), coalesce(sum(completion_tokens),0) from nim_calls where tag like 'e0-%%' and cached=false and ts > to_timestamp(%s)", (stamp,)).fetchone()
    res["usage"] = {"uncached_calls": row[0], "prompt_tokens": int(row[1]), "completion_tokens": int(row[2]), "calls_per_run": round(row[0] / max(1, len(runs)), 1)}
    rows = [{"policy": p, **{k: v for k, v in d.items() if k not in ("decision_CI95", "rule_CI95")}, "decision_CI95": "-".join(map(str, d["decision_CI95"]))} for p, d in res["per_policy"].items()]
    md = "# E0: end-to-end policy adherence\n\n" + md_table(rows, ["policy", "cases", "decision_acc", "decision_CI95", "rule_acc", "threshold_acc", "tier_acc", "grade_acc", "failed_runs", "degraded_runs", "avg_secs"]) \
        + f"\nPolicy-flip agreement: {res['flip_agreement']} over {res['flip_cases']} cases whose correct decision differs between policies (CI95 {res['flip_CI95']}).\n\n## Per-rule accuracy\n" \
        + md_table([{"rule": k, "correct": v} for k, v in res["rule_accuracy"].items()], ["rule", "correct"]) + f"\nUsage: {res['usage']}\n"
    save(os.environ.get("E0_NAME", "e0_policy"), {**res, "case_ids": cases}, md)
    for p, d in res["per_policy"].items():
        log_mlflow("wealthpilot-E0-policy", p, {"policy": p, "cases": d["cases"]}, {"decision_acc": d["decision_acc"], "rule_acc": d["rule_acc"], "threshold_acc": d["threshold_acc"]})
    print(md)
    return res


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 12))
