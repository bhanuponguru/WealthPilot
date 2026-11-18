"""WealthPilot console (Streamlit).

Run it with ``uv run wealthpilot ui`` (or ``uv run streamlit run src/wealthpilot/ui/app.py``).
Day-to-day work (inbox, new case, cases, history) comes first in the sidebar; reference material and the experiment and
diagnostic pages sit in their own sections below it.
"""

from __future__ import annotations

import streamlit as st

from wealthpilot.ui import nav
from wealthpilot.ui.common import cached_health
from wealthpilot.ui.forms import TIERS

st.set_page_config(page_title="WealthPilot", page_icon=":material/account_balance:", layout="wide", initial_sidebar_state="expanded")

page = st.navigation(nav.pages())

with st.sidebar:
    st.markdown("##### Signed in as")
    st.text_input("Your name or id", key="approver_id", placeholder="e.g. j.rivera",
                  help="Written to the audit log with every decision you make, and filled in for you on the decision form.")
    st.selectbox("Your authority", TIERS, index=None, key="reviewer_tier", placeholder="Choose your tier",
                 help="The policy requires a minimum authority tier to decide each case. You cannot decide a case above your tier.")
    checks = cached_health()
    required = [c for c in checks if c.required]
    ok = sum(c.ok for c in required)
    if ok == len(required):
        st.caption(":green[●] All services running")
    else:
        st.caption(f":orange[●] {len(required) - ok} service(s) need attention. See **System**.")
    st.caption("A human always makes the final decision.")

page.run()
