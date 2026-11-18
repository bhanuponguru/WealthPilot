"""Navigation: the page list (grouped by who needs it) and a helper for jumping between pages."""

from __future__ import annotations

import streamlit as st


def pages() -> dict[str, list[st.Page]]:
    """Sections of the sidebar. Day-to-day work first; reference material and the research/diagnostic pages after it."""
    from .views import history, home, policies, queue, results, system, underwrite

    return {
        "Work": [
            st.Page(home.render, title="Inbox", icon=":material/inbox:", url_path="inbox", default=True,
                    help="Cases waiting for your decision, runs in progress and recent decisions."),
            st.Page(underwrite.render, title="New case", icon=":material/add_circle:", url_path="new-case",
                    help="Submit a loan application with its PDF statements, or try a sample applicant."),
            st.Page(queue.render, title="Cases", icon=":material/folder_open:", url_path="cases",
                    help="Every case: open one to read the memo and evidence, and to record your decision."),
            st.Page(history.render, title="History", icon=":material/history:", url_path="history",
                    help="The tamper-evident record of every decision."),
        ],
        "Reference": [
            st.Page(policies.render, title="Credit policies", icon=":material/menu_book:", url_path="policies",
                    help="Read the credit policies, compare two of them and test how the rules are found."),
        ],
        "Admin and research": [
            st.Page(results.render, title="Experiments", icon=":material/science:", url_path="experiments",
                    help="Evaluation results: policy adherence, parsing, retrieval, fairness and reliability."),
            st.Page(system.render, title="System", icon=":material/settings:", url_path="system",
                    help="Service health with fix commands, configuration and model-call diagnostics."),
        ],
    }


def go(url_path: str) -> None:
    """Switch to a page by its url_path (e.g. ``go("cases")``)."""
    for section in pages().values():
        for p in section:
            if p.url_path == url_path:
                st.switch_page(p)
    raise KeyError(url_path)


def open_in_cases(thread_id: str) -> None:
    """Jump to the Cases page with this case opened."""
    st.session_state["case_open"] = thread_id
    go("cases")
