"""E4: reliability under injected faults. Cache is OFF and fault injection sits below it, so every call really hits the network.

Profiles: none | 429 storm | timeouts | malformed model output | flaky MCP | research server down | fincalc server down.
Plus a crash/resume test (kill the process after the risk step, resume from the Postgres checkpoint in a new session).
Safety metric: an UNSAFE APPROVE is a run that recommends approve when the ground truth is not approve. Degraded runs
must never auto-approve (the memo says so and the recommendation is capped at refer).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

from common import RESULTS, log_mlflow, md_table, save
from wealthpilot_lab.inputs import make_input
from wealthpilot_lab.synth.applicants import load
from wealthpilot_lab.synth.groundtruth import load_gt

from wealthpilot.config import get_settings
from wealthpilot.graph.builder import session
from wealthpilot.nim import chaos, gateway, run_tag
from wealthpilot.nim.store import pool

POLICY = "strict"
PROFILES = {
    "none": {},
    "429_storm": {"p_429": 0.35, "kinds": ["chat", "rerank"]},
    "timeouts": {"p_timeout": 0.25, "kinds": ["chat"]},
    "malformed_output": {"p_malformed": 0.30, "kinds": ["chat"]},
    "mcp_flaky": {"p_503": 0.30, "kinds": ["mcp"]},
    "research_down": {"down_servers": ["research"]},
    "fincalc_down": {"down_servers": ["fincalc"]},
}


async def run_one(runner, a, profile, stamp, sem):
    async with sem:
        tag = f"e4-{profile}-{a['case_id']}"
        t0 = time.time()
        try:
            with run_tag(tag):
                snap = await runner.start(make_input(a, POLICY, "clean"), f"{tag}-{stamp}")
            v = snap["values"]
            return {"case": a["case_id"], "profile": profile, "completed": snap["interrupt"] is not None or snap["done"], "rec": v.get("recommendation"),
                    "degraded": bool(v.get("degraded")), "errors": v.get("errors"), "secs": round(time.time() - t0, 1), "tag": tag}
        except Exception as e:  # noqa: BLE001
            return {"case": a["case_id"], "profile": profile, "completed": False, "rec": None, "degraded": False, "error": f"{type(e).__name__}: {str(e)[:100]}", "secs": round(time.time() - t0, 1), "tag": tag}


async def crash_resume(a, stamp):
    cfg = {"configurable": {"thread_id": f"e4-crash-{a['case_id']}-{stamp}"}, "recursion_limit": 60}
    inp = make_input(a, POLICY, "clean")
    before = []
    async with session() as r1:                       # "process 1": dies right after the risk step
        with run_tag(f"e4-crash-1-{a['case_id']}"):
            async for ev in r1.graph.astream(inp, cfg, stream_mode="updates"):
                before += [k for k in ev if k != "__interrupt__"]
                if "risk" in ev:
                    break
    after = []
    async with session() as r2:                       # "process 2": new session, resumes from the checkpoint with no input
        with run_tag(f"e4-crash-2-{a['case_id']}"):
            async for ev in r2.graph.astream(None, cfg, stream_mode="updates"):
                after += [k for k in ev if k != "__interrupt__"]
        snap = await r2.snapshot(cfg["configurable"]["thread_id"])
    return {"case": a["case_id"], "nodes_before_crash": before, "nodes_after_resume": after, "reran_completed_nodes": sorted(set(before) & set(after)),
            "resumed_to": snap["interrupt"]["type"] if snap["interrupt"] else None, "rec": snap["values"].get("recommendation")}


def usage(stamp: int) -> dict:
    out = {}
    with pool().connection() as c:
        rows = c.execute("""select split_part(tag, '-', 2) prof, count(*) filter (where kind='chat'), count(*) filter (where kind='chat' and not ok),
                            coalesce(sum(retries),0), count(*) filter (where kind='chat' and model like '%%ultra%%'), coalesce(sum(prompt_tokens),0) + coalesce(sum(completion_tokens),0)
                            from nim_calls where tag like 'e4-%%' and ts > to_timestamp(%s) group by 1""", (stamp,)).fetchall()
    for prof, calls, failed, retries, fb, toks in rows:
        out[prof] = {"chat_calls": calls, "failed_calls": failed, "retries": int(retries), "fallback_model_calls": fb, "tokens": int(toks)}
    return out


async def main(n_cases: int = 4, concurrency: int = 3, only: list[str] | None = None) -> dict:
    gt, stamp = load_gt(), int(time.time())
    apps = {a["case_id"]: a for a in load()}
    app_ids = [c for c in sorted(gt) if gt[c][POLICY]["recommendation"] == "approve"][:: 3][: n_cases // 2]
    dec_ids = [c for c in sorted(gt) if gt[c][POLICY]["recommendation"] == "decline"][:: 7][: n_cases - len(app_ids)]
    cases = app_ids + dec_ids
    print("cases:", cases, [gt[c][POLICY]["recommendation"] for c in cases], flush=True)
    get_settings().nim_cache_enabled = False
    get_settings().chat_fallback_model = "nvidia/nemotron-3-ultra-550b-a55b"  # E4 exercises the fallback chain (off by default)
    sem = asyncio.Semaphore(concurrency)
    results = []
    async with session() as runner:
        for prof, cfg in PROFILES.items():
            if only and prof not in only:
                continue
            chaos.set_chaos(cfg or None, seed=11)
            gateway.reset_breakers()
            runner_runs = await asyncio.gather(*[run_one(runner, apps[c], prof, stamp, sem) for c in cases])
            results += runner_runs
            print(prof, [(r["rec"], r["degraded"]) for r in runner_runs], flush=True)
        chaos.set_chaos(None)
    prev = None
    if only:  # re-run of a subset: keep the other profiles (and the crash test) from the previous full run
        prev = json.loads((RESULTS / "e4_reliability.json").read_text())
        crash = prev["crash_resume"]
        results = [r for r in prev["runs"] if r["profile"] not in only] + results
    else:
        crash = [await crash_resume(apps[cases[0]], stamp)]
    use = usage(stamp)
    rows = []
    base_secs = None
    for prof in PROFILES:
        if prev and prof not in only:
            old_row = next(r for r in prev["rows"] if r["profile"] == prof)
            rows.append(old_row)
            base_secs = base_secs or old_row["avg_secs"]
            continue
        rs = [r for r in results if r["profile"] == prof]
        comp = [r for r in rs if r["completed"]]
        acc = sum(r["rec"] == gt[r["case"]][POLICY]["recommendation"] for r in comp)
        unsafe = sum(r["rec"] == "approve" and gt[r["case"]][POLICY]["recommendation"] != "approve" for r in comp)
        deg = [r for r in comp if r["degraded"]]
        deg_approve = sum(r["rec"] == "approve" for r in deg)
        secs = sum(r["secs"] for r in rs) / max(1, len(rs))
        base_secs = base_secs or secs
        u = use.get(prof, {})
        rows.append({"profile": prof, "runs": len(rs), "completed": f"{len(comp)}/{len(rs)}", "decision_correct": f"{acc}/{len(comp)}", "unsafe_approves": unsafe,
                     "degraded_runs": len(deg), "degraded_auto_approved": deg_approve, "avg_secs": round(secs, 1), "latency_x": round(secs / base_secs, 2),
                     "chat_calls": u.get("chat_calls"), "failed_calls": u.get("failed_calls"), "retries": u.get("retries"), "fallback_calls": u.get("fallback_model_calls"), "tokens": u.get("tokens")})
    md = "# E4: reliability under fault injection (cache off)\n\n" + md_table(rows, ["profile", "runs", "completed", "decision_correct", "unsafe_approves", "degraded_runs", "degraded_auto_approved",
                                                                              "avg_secs", "latency_x", "chat_calls", "failed_calls", "retries", "fallback_calls", "tokens"]) \
        + "\n## Crash and resume\n" + "\n".join(f"- case {c['case']}: nodes before crash {c['nodes_before_crash']}; after resume {c['nodes_after_resume']}; re-ran already-completed nodes: {c['reran_completed_nodes'] or 'none'}; resumed to `{c['resumed_to']}`; recommendation {c['rec']}" for c in crash)
    save("e4_reliability", {"rows": rows, "crash_resume": crash, "runs": results, "cases": cases}, md)
    for r in rows:
        log_mlflow("wealthpilot-E4-reliability", r["profile"], {"profile": r["profile"]}, {"unsafe_approves": r["unsafe_approves"], "avg_secs": r["avg_secs"], "latency_x": r["latency_x"]})
    print(md)
    get_settings().nim_cache_enabled = True
    return {"rows": rows}


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else 4, only=sys.argv[2].split(",") if len(sys.argv) > 2 else None))
