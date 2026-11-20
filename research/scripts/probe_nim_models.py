"""Probe which NVIDIA NIM chat models actually respond for this account, and rank them.

The public catalog lists many models that are retired (410) or missing (404) for a given key, so availability must be
measured. For each candidate chat model this sends two small requests:

  1. a tool-calling request (must return a correct ``tool_calls`` entry), and
  2. a plain question with a checkable answer (must contain the right number).

It records status, latency and whether the reply was empty (reasoning models can spend the whole token budget thinking).
Results go to ``results/nim_probe.json`` so they can be compared over time.

    uv run python research/scripts/probe_nim_models.py                 # probe every tool-capable chat model in the catalog
    uv run python research/scripts/probe_nim_models.py --only nvidia/x # probe specific models
"""

from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from wealthpilot.config import get_settings

BASE = "https://integrate.api.nvidia.com/v1"
OUT = Path(__file__).resolve().parents[1] / "results" / "nim_probe.json"
SKIP = re.compile(r"embed|rerank|guard|safety|reward|parse|clip|vl\b|vision|vila|neva|paligemma|fuyu|kosmos|riva|translate|"
                  r"nemoretriever|retriev|content-safety|topic-control|nv-embed|bge|arctic-embed|deplot|synthetic|steer", re.I)

TOOL = {"type": "function", "function": {
    "name": "get_dscr", "description": "Compute a debt service coverage ratio.",
    "parameters": {"type": "object", "properties": {
        "net_operating_income": {"type": "number"}, "annual_debt_service": {"type": "number"}},
        "required": ["net_operating_income", "annual_debt_service"]}}}


def _post(client: httpx.Client, key: str, body: dict, timeout: float) -> tuple[int, dict | str, float]:
    t0 = time.perf_counter()
    try:
        r = client.post(f"{BASE}/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=body, timeout=timeout)
        try:
            data: dict | str = r.json()
        except Exception:
            data = r.text[:200]
        return r.status_code, data, time.perf_counter() - t0
    except Exception as e:  # timeouts, connection resets
        return -1, f"{type(e).__name__}: {e}"[:200], time.perf_counter() - t0


def probe(model: str, key: str, timeout: float) -> dict:
    res: dict = {"model": model}
    with httpx.Client() as c:
        st, data, dt = _post(c, key, {
            "model": model, "temperature": 0, "max_tokens": 1024, "tools": [TOOL], "tool_choice": "auto",
            "messages": [{"role": "user", "content": "Use the tool: net operating income is 150000 and annual debt service is 100000."}]},
            timeout)
        res.update(tool_status=st, tool_seconds=round(dt, 1))
        if st == 200 and isinstance(data, dict):
            msg = data["choices"][0]["message"]
            calls = msg.get("tool_calls") or []
            ok = False
            if calls:
                try:
                    args = json.loads(calls[0]["function"]["arguments"])
                    ok = calls[0]["function"]["name"] == "get_dscr" and float(args["net_operating_income"]) == 150000 and float(args["annual_debt_service"]) == 100000
                except Exception:
                    ok = False
            res["tool_ok"] = ok
        else:
            res["tool_ok"] = False
            res["tool_error"] = data if isinstance(data, str) else str(data)[:160]
        if st != 200:  # no point asking a dead model a second question
            return res
        st, data, dt = _post(c, key, {
            "model": model, "temperature": 0, "max_tokens": 1024,
            "messages": [{"role": "user", "content": "A loan of 240000 is repaid over 8 years in equal annual payments with no interest. "
                                                     "What is one annual payment? Reply with just the number."}]}, timeout)
        res.update(qa_status=st, qa_seconds=round(dt, 1))
        if st == 200 and isinstance(data, dict):
            text = (data["choices"][0]["message"].get("content") or "").strip()
            res["qa_empty"] = not text
            res["qa_ok"] = "30000" in text.replace(",", "")
        else:
            res["qa_ok"] = False
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="probe only these model ids")
    ap.add_argument("--timeout", type=float, default=60)
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()
    key = get_settings().nvidia_api_key.get_secret_value() if hasattr(get_settings().nvidia_api_key, "get_secret_value") else get_settings().nvidia_api_key

    if args.only:
        models = args.only
    else:
        r = httpx.get(f"{BASE}/models", headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        models = sorted(m["id"] for m in r.json()["data"] if not SKIP.search(m["id"]))
    print(f"probing {len(models)} models …", flush=True)

    with ThreadPoolExecutor(args.workers) as ex:
        results = list(ex.map(lambda m: probe(m, key, args.timeout), models))

    def score(r: dict) -> tuple:
        return (not r.get("tool_ok"), not r.get("qa_ok"), r.get("tool_seconds", 999) + r.get("qa_seconds", 999))
    results.sort(key=score)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "results": results}, indent=2))
    print(f"{'model':58} tool  qa    tool_s qa_s  note")
    for r in results:
        note = "" if r.get("tool_status") == 200 else f"HTTP {r.get('tool_status')}"
        if r.get("qa_empty"):
            note += " empty-reply"
        print(f"{r['model']:58} {'ok ' if r.get('tool_ok') else '-- '}  {'ok ' if r.get('qa_ok') else '-- '}  "
              f"{r.get('tool_seconds', ''):<6} {r.get('qa_seconds', ''):<6} {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
