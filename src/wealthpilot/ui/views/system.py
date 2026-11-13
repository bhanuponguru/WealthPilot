"""System page: service health with fix commands, configuration, and model-call diagnostics."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...config import get_settings
from ...nim import store
from ..common import cached_health, friendly_error, require_db, show_table


def tab_health() -> None:
    if st.button("↻ Re-check now", key="sys-refresh"):
        cached_health.clear()
        st.rerun()
    checks = cached_health()
    df = pd.DataFrame([{"": "✅" if c.ok else ("⚠️" if not c.required else "❌"), "Component": c.name, "Status": c.detail,
                        "Required": "yes" if c.required else "optional", "How to fix": "" if c.ok else c.fix} for c in checks])
    show_table(df)
    bad = [c for c in checks if not c.ok and c.required]
    if bad:
        st.markdown("**Start everything (in separate terminals, from the project folder):**")
        st.code("docker compose up -d postgres\nollama serve                    # skip if Ollama already runs as a service\nuv run wealthpilot mcp-up\nmake mlflow                     # optional: traces", language="bash")
    else:
        st.success("Everything required is running.")


def tab_config() -> None:
    s = get_settings()
    rows = {"Chat model": s.chat_model, "Fallback chat model": s.chat_fallback_model or "(disabled)", "Vision model": s.vlm_model, "Rerank model": s.rerank_model,
            "Embedding model": f"{s.embed_model} (Ollama)", "Request ceiling (per minute)": s.nim_rpm_budget, "Request timeout (s)": s.nim_timeout_s,
            "Response cache": "on" if s.nim_cache_enabled else "off", "Model 'thinking'": "on" if s.nim_thinking else "off", "MLflow": s.mlflow_tracking_uri,
            "API key": "set (hidden)"}
    show_table(pd.DataFrame({"Setting": list(rows), "Value": [str(v) for v in rows.values()]}))
    st.caption("Change these with environment variables or `.env` — see the documentation's Configuration page. Restart the console to apply them.")


def tab_models() -> None:
    if not require_db():
        return
    try:
        rpm = store.current_rpm()
        with store.pool().connection() as c:
            stats = c.execute("""SELECT model, kind, count(*) FILTER (WHERE NOT cached) AS real_calls, count(*) FILTER (WHERE cached) AS cache_hits,
                                        count(*) FILTER (WHERE NOT ok) AS failed, round(avg(latency_ms) FILTER (WHERE NOT cached AND ok)) AS avg_ms,
                                        coalesce(sum(prompt_tokens),0) + coalesce(sum(completion_tokens),0) AS tokens
                                 FROM nim_calls WHERE ts > now() - interval '24 hours' GROUP BY 1, 2 ORDER BY real_calls DESC""").fetchall()
            errors = c.execute("""SELECT left(error, 90), model, count(*) FROM nim_calls WHERE NOT ok AND ts > now() - interval '24 hours'
                                  GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8""").fetchall()
            cache_n = c.execute("SELECT count(*) FROM nim_cache").fetchone()[0]
    except Exception as e:  # noqa: BLE001
        st.error(friendly_error(e))
        return
    budget = get_settings().nim_rpm_budget
    c1, c2, c3 = st.columns(3)
    c1.metric("Current request rate (per minute)", f"{rpm:.1f}", help="Adaptive: it drops when the model service returns 429 and recovers on success.")
    c2.metric("Ceiling", budget)
    c3.metric("Cached replies", f"{cache_n:,}")
    if rpm <= store.MIN_RPM + 0.5:
        st.warning("The rate is at its floor: the model service is throttling this key. Runs will be slow until it recovers.")
    st.markdown("**Model calls — last 24 hours**")
    if stats:
        show_table(pd.DataFrame(stats, columns=["Model", "Kind", "Real calls", "Cache hits", "Failed", "Avg latency (ms)", "Tokens"]))
    else:
        st.caption("No model calls recorded yet.")
    if errors:
        st.markdown("**Most common failures**")
        show_table(pd.DataFrame(errors, columns=["Error", "Model", "Count"]))
    if st.button("Reset the rate limiter", key="sys-reset", help="Sets the request rate back to the ceiling (it re-adapts automatically)."):
        store.reset_state()
        st.success("Rate limiter reset.")
        st.rerun()


def render() -> None:
    st.title("🛠️ System")
    t1, t2, t3 = st.tabs(["Health", "Configuration", "Model calls"])
    with t1:
        tab_health()
    with t2:
        tab_config()
    with t3:
        tab_models()
