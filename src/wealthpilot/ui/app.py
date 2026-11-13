"""WealthPilot console (Streamlit).

Run it with ``uv run wealthpilot ui`` (or ``uv run streamlit run src/wealthpilot/ui/app.py``).
The console needs Postgres, Ollama, the MCP servers and a NIM key; the Overview and System pages tell you what is missing and how to start it.
"""

from __future__ import annotations

import streamlit as st

from wealthpilot.ui.common import cached_health
from wealthpilot.ui.views import history, home, policies, queue, results, system, underwrite

st.set_page_config(page_title="WealthPilot", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

PAGES = [
    st.Page(home.render, title="Overview", icon="🏠", url_path="overview", default=True),
    st.Page(underwrite.render, title="Underwrite", icon="▶️", url_path="underwrite"),
    st.Page(queue.render, title="Cases", icon="🗂️", url_path="cases"),
    st.Page(history.render, title="History", icon="📜", url_path="history"),
    st.Page(policies.render, title="Policies", icon="📘", url_path="policies"),
    st.Page(results.render, title="Results", icon="🧪", url_path="results"),
    st.Page(system.render, title="System", icon="🛠️", url_path="system"),
]

nav = st.navigation(PAGES)

with st.sidebar:
    st.markdown("---")
    checks = cached_health()
    required = [c for c in checks if c.required]
    ok = sum(c.ok for c in required)
    st.caption(("🟢" if ok == len(required) else "🟠" if ok else "🔴") + f" Services: {ok}/{len(required)} required running")
    st.caption("A human always makes the final decision.")

nav.run()
