"""Navigation: the page list and a helper for jumping between pages."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class PageSpec:
    title: str
    icon: str
    url_path: str
    module: str       # module in ui.views that exposes render()
    help: str
    default: bool = False


#: Sections of the sidebar: day-to-day work first, then reference material, then administration.
SECTIONS: dict[str, list[PageSpec]] = {
    "Work": [
        PageSpec("Inbox", ":material/inbox:", "inbox", "home", "Cases waiting for your decision, runs in progress and recent decisions.", default=True),
        PageSpec("New case", ":material/add_circle:", "new-case", "underwrite", "Submit a loan application with its PDF statements."),
        PageSpec("Cases", ":material/folder_open:", "cases", "queue", "Every case: open one to read the memo and evidence, and to record your decision."),
        PageSpec("History", ":material/history:", "history", "history", "The tamper-evident record of every decision."),
    ],
    "Reference": [
        PageSpec("Credit policies", ":material/menu_book:", "policies", "policies", "Read the credit policies, compare two of them and test how the rules are found."),
    ],
    "Administration": [
        PageSpec("System", ":material/settings:", "system", "system", "Service health with fix commands, configuration and model-call diagnostics."),
    ],
}


def pages() -> dict[str, list[st.Page]]:
    out: dict[str, list[st.Page]] = {}
    for section, specs in SECTIONS.items():
        out[section] = [
            st.Page(importlib.import_module(f"wealthpilot.ui.views.{s.module}").render, title=s.title, icon=s.icon, url_path=s.url_path, help=s.help, default=s.default)
            for s in specs
        ]
    return out


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
