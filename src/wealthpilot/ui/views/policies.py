"""Policies page: read a credit policy, see its rules, compare two policies, and try the retrieval that the agents use."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ...config import PROJECT_ROOT
from .. import forms
from ..common import cached_health, friendly_error, show_table
from .underwrite import policy_ids


def _read(pid: str) -> str:
    return (PROJECT_ROOT / "data" / "policies" / pid / "policy.md").read_text()


def tab_read(pid: str) -> None:
    st.markdown(_read(pid))


def tab_rules(pid: str) -> None:
    rules = forms.parse_rules(_read(pid))
    show_table(pd.DataFrame(rules).rename(columns={"rule_id": "Rule", "title": "Title", "text": "Text"}))


def tab_compare() -> None:
    ids = policy_ids()
    if len(ids) < 2:
        st.info("Add a second policy to compare.")
        return
    c1, c2 = st.columns(2)
    a = c1.selectbox("Policy A", ids, index=0, key="cmp-a")
    b = c2.selectbox("Policy B", ids, index=1, key="cmp-b")
    ra, rb = {r["rule_id"]: r for r in forms.parse_rules(_read(a))}, {r["rule_id"]: r for r in forms.parse_rules(_read(b))}
    only_diff = st.checkbox("Show only rules that differ", value=True, key="cmp-diff")
    shown = 0
    for rid in sorted({*ra, *rb}, key=lambda x: int(x.split("-")[1])):
        ta, tb = ra.get(rid, {}).get("text", "—"), rb.get(rid, {}).get("text", "—")
        if only_diff and ta == tb:
            continue
        shown += 1
        st.markdown(f"**{rid} · {(ra.get(rid) or rb.get(rid))['title']}**  {'🟰 identical' if ta == tb else '🔀 differs'}")
        l, r = st.columns(2)
        l.caption(f"{a}"); l.write(ta)
        r.caption(f"{b}"); r.write(tb)
    if not shown:
        st.success("The two policies have identical rules.")


def tab_search(pid: str) -> None:
    st.caption("This runs the same retrieval the agents use: BM25 + vector search fused, then reranked by the NIM reranker. It needs Postgres, Ollama and the NIM key.")
    q = st.text_input("Ask a question about the policy", value="What is the minimum debt service coverage ratio?", key="s-q")
    c1, c2, c3, c4 = st.columns(4)
    mode = c1.selectbox("Retrieval", ["hybrid", "bm25", "dense"], key="s-mode")
    rerank = c2.toggle("Rerank", value=True, key="s-rr")
    strategy = c3.selectbox("Chunking", ["structure", "fixed"], key="s-st")
    k = c4.slider("Results", 1, 6, 3, key="s-k")
    if st.button("Search", type="primary", key="s-go") and q.strip():
        try:
            from ...rag import index
            index.ensure_indexed()
            with st.spinner("Searching…"):
                res = index.search(q, pid, strategy=strategy, mode=mode, use_rerank=rerank, k=k)
        except Exception as e:  # noqa: BLE001
            st.error(friendly_error(e))
            return
        if res.get("degraded"):
            st.warning("The reranker was unavailable, so results keep the first-stage order.")
        for r in res["results"]:
            st.markdown(f"**#{r['rank']} · {', '.join(r['rule_ids']) or r['title']}**")
            st.write(r["text"])


def render() -> None:
    st.title("Credit policies")
    st.caption("The policy is a plain Markdown document. The agents read it, extract its thresholds and apply it — there is no hard-coded rule set. "
               "See the documentation page *Writing a new policy* to add your own.")
    ids = policy_ids()
    if not ids:
        st.warning("No policies found in `data/policies/`.")
        return
    pid = st.selectbox("Policy", ids, key="pol-id")
    t1, t2, t3, t4 = st.tabs(["Read", "Rules", "Compare policies", "Try retrieval"])
    with t1:
        tab_read(pid)
    with t2:
        tab_rules(pid)
    with t3:
        tab_compare()
    with t4:
        if any(c.name == "Postgres" and not c.ok for c in cached_health()):
            st.error("Postgres is not reachable. Start it with `docker compose up -d postgres`.")
        else:
            tab_search(pid)
