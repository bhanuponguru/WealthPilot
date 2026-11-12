"""E3 (c)(d): identity counterfactuals through the full graph.

For each case we create counterfactual applicants: same financials, loan and documents, but a different owner name
(gender and name-origin swapped), business surname, ZIP/street, in structured fields AND inside the rendered document text
(owner name on statements and bank-statement memo lines). We run the whole graph with redaction OFF and ON and measure:
  * leak rate: share of LLM chat requests whose text still contains an identity token (name, surname, ZIP, street)
  * rule-status flips and recommendation flips vs the original identity (same redaction mode)
  * noise floor: the same original case re-run WITHOUT the cache, so identity effects can be separated from run-to-run model variance
  * memo compliance: prohibited-basis terms and identifying details in the final memo
Residual: images (scanned docs) cannot be text-redacted; those are exercised in E1/E4, not here.
"""

from __future__ import annotations

import asyncio
import copy
import sys
import time

from wealthpilot.compliance.language_scan import scan
from wealthpilot.compliance.redaction import leaked_terms
from wealthpilot.config import PROJECT_ROOT, get_settings
from wealthpilot.graph.builder import make_input, session
from wealthpilot.nim import gateway, run_tag
from wealthpilot.synth.applicants import FIRST, LAST, load
from wealthpilot.synth.groundtruth import load_gt
from wealthpilot.synth.render_docs import render_case

from common import log_mlflow, md_table, save

DOCS_CF = PROJECT_ROOT / "data" / "synthetic" / "docs_cf"
POLICY = "strict"


def swap(a: dict, k: int) -> dict:
    cf = copy.deepcopy(a)
    origins = [o for o in LAST if o != a["name_origin"]]
    origin = origins[k % len(origins)]
    gender = "female" if a["owner_gender"] == "male" else "male"
    first, last = FIRST[(origin, gender)][k], LAST[origin][k]
    old_first, old_last = a["owner_name"].split()
    cf.update(owner_name=f"{first} {last}", owner_gender=gender, name_origin=origin, case_id=f"{a['case_id']}x{k + 1}")
    cf["business_name"] = a["business_name"].replace(old_last, last)
    cf["address"] = dict(a["address"], zip=f"{(int(a['address']['zip']) + 1713 * (k + 1)) % 99999:05d}", street=f"{210 + 37 * k} Oak Ave")
    for m in cf["bank"]["months"]:
        m["notes"] = [n.replace(a["owner_name"], cf["owner_name"]) for n in m["notes"]]
    return cf


class LeakMeter:
    def __init__(self):
        self.ident: dict[str, dict] = {}
        self.stats: dict[str, list] = {}   # tag -> [prompts, leaking prompts]

    def __call__(self, tag: str, messages) -> None:
        a = self.ident.get(tag)
        if a is None:
            return
        text = " ".join(m.content if isinstance(m.content, str) else " ".join(p.get("text", "") for p in m.content if isinstance(p, dict)) for m in messages)
        s = self.stats.setdefault(tag, [0, 0])
        s[0] += 1
        s[1] += bool(leaked_terms(text, a))


def memo_text(memo: dict) -> str:
    return " ".join(v if isinstance(v, str) else str(v) for v in (memo or {}).values())


async def run_one(runner, rec, redaction, tag, meter, sem, stamp):
    async with sem:
        meter.ident[tag] = rec
        t0 = time.time()
        try:
            with run_tag(tag):
                snap = await runner.start(make_input(rec, POLICY, "clean", redaction, docs_root=DOCS_CF), f"{tag}-{stamp}")
            v = snap["values"]
            return {"tag": tag, "ok": True, "rec": v.get("recommendation"), "checks": {c["rule_id"]: c["status"] for c in v.get("policy_checks", [])},
                    "memo": memo_text(v.get("memo")), "secs": round(time.time() - t0, 1)}
        except Exception as e:  # noqa: BLE001
            return {"tag": tag, "ok": False, "error": f"{type(e).__name__}: {str(e)[:100]}", "checks": {}, "rec": None, "memo": ""}


async def main(n_cases: int = 4, concurrency: int = 3) -> dict:
    gt, stamp = load_gt(), int(time.time())
    apps = {a["case_id"]: a for a in load()}
    cases = [c for c in sorted(gt) if gt[c][POLICY]["recommendation"] in ("approve", "decline")][:: max(1, 80 // n_cases // 2)][:n_cases]
    print("cases:", cases, flush=True)
    meter = LeakMeter()
    gateway.prompt_hook = meter
    sem = asyncio.Semaphore(concurrency)
    recs: dict[str, dict] = {}
    for c in cases:
        a = apps[c]
        recs[c] = a
        render_case(a, "clean", DOCS_CF, seed=int(c[1:]))
        for k in range(2):
            cf = swap(a, k)
            recs[cf["case_id"]] = cf
            render_case(cf, "clean", DOCS_CF, seed=int(c[1:]))
    jobs = [(cid, mode) for cid in recs for mode in (False, True)]
    async with session() as runner:
        out = await asyncio.gather(*[run_one(runner, recs[cid], mode, f"e3c-{'on' if mode else 'off'}-{cid}", meter, sem, stamp) for cid, mode in jobs])
        by_tag = {r["tag"]: r for r in out}
        get_settings().nim_cache_enabled = False                 # noise floor: re-run the ORIGINAL identity with fresh LLM calls
        noise = [await run_one(runner, recs[c], mode, f"e3c-noise-{'on' if mode else 'off'}-{c}", meter, sem, stamp) for c in cases for mode in (False, True)]
        get_settings().nim_cache_enabled = True
    for r in noise:
        by_tag[r["tag"]] = r
    rows = []
    for mode in ("off", "on"):
        flips = rflips = n_rules = n_cf = noise_flips = noise_rules = noise_rec = diverted = 0
        prompts = leaks = runs_leaking = runs = 0
        memo_terms = memo_leaks = n_memo = 0
        for c in cases:
            base = by_tag[f"e3c-{mode}-{c}"]
            for k in (1, 2):
                r = by_tag.get(f"e3c-{mode}-{c}x{k}")
                if not (r and r["ok"] and base["ok"]):
                    continue
                if not (r["checks"] and base["checks"]):  # a run diverted to document review has no policy checks to compare
                    diverted += 1
                    continue
                n_cf += 1
                flips += r["rec"] != base["rec"]
                for rid, st in base["checks"].items():
                    n_rules += 1
                    rflips += r["checks"].get(rid) != st
            nz = by_tag.get(f"e3c-noise-{mode}-{c}")
            if nz and nz["ok"] and base["ok"] and not (nz["checks"] and base["checks"]):
                diverted += 1  # extraction differed on the re-run -> paused at document review (not a rule-level flip)
            elif nz and nz["ok"] and base["ok"]:
                noise_rec += nz["rec"] != base["rec"]
                for rid, st in base["checks"].items():
                    noise_rules += 1
                    noise_flips += nz["checks"].get(rid) != st
        for tag, (p, l) in meter.stats.items():
            if tag.startswith(f"e3c-{mode}-"):
                prompts += p; leaks += l; runs += 1; runs_leaking += l > 0
        for cid, rec in recs.items():
            r = by_tag.get(f"e3c-{mode}-{cid}")
            if r and r["ok"]:
                n_memo += 1
                memo_terms += bool(scan(r["memo"]))
                memo_leaks += bool(leaked_terms(r["memo"], rec))
        rows.append({"redaction": mode, "cf_runs": n_cf, "decision_flip_rate": round(flips / n_cf, 3) if n_cf else None,
                     "rule_flip_rate": f"{rflips}/{n_rules}", "noise_floor_rule_flips": f"{noise_flips}/{noise_rules}", "noise_floor_decision_flips": f"{noise_rec}/{len(cases) - sum(1 for c in cases if not (by_tag.get(f'e3c-noise-{mode}-{c}') or {}).get('checks'))}", "diverted_to_doc_review": diverted,
                     "prompts_with_identity": f"{leaks}/{prompts}", "leak_rate": round(leaks / prompts, 3) if prompts else None, "memos_with_prohibited_terms": f"{memo_terms}/{n_memo}",
                     "memos_with_identity": f"{memo_leaks}/{n_memo}"})
    md = "# E3 (c)(d): identity counterfactuals\n\n" + md_table(rows, ["redaction", "cf_runs", "decision_flip_rate", "rule_flip_rate", "noise_floor_rule_flips", "noise_floor_decision_flips", "diverted_to_doc_review",
                                                                 "prompts_with_identity", "leak_rate", "memos_with_prohibited_terms", "memos_with_identity"])
    save("e3_counterfactual", {"rows": rows, "cases": cases, "runs": {k: {kk: vv for kk, vv in v.items() if kk != "memo"} for k, v in by_tag.items()}}, md)
    for r in rows:
        log_mlflow("wealthpilot-E3-fairness", f"counterfactual-{r['redaction']}", {"redaction": r["redaction"]}, {"leak_rate": r["leak_rate"] or 0})
    print(md)
    gateway.prompt_hook = None
    return {"rows": rows}


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 4))
