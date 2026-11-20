"""Prohibited-basis language scan for memos (ECOA/Reg-B-style example profile; configurable list)."""

from __future__ import annotations

import re

import yaml

from ..config import CONFIG_DIR

PROFILE = CONFIG_DIR / "compliance_profiles" / "us_example.yaml"


def load_profile() -> dict:
    return yaml.safe_load(PROFILE.read_text())


def scan(text: str, extra_terms: list[str] | None = None) -> list[str]:
    """Return the prohibited-basis terms found in `text` (case-insensitive, whole-word)."""
    terms = load_profile()["prohibited_terms"] + (extra_terms or [])
    found = []
    for t in terms:
        if re.search(rf"\b{re.escape(t)}\b", text, re.I):
            found.append(t)
    return sorted(set(found))
