"""Redaction: strip protected attributes and their proxies before any LLM sees case data.

Covers the owner's full/first/last name (also inside the business name), street address and ZIP. City/state are kept
(state is a legitimate model feature). Scanned images cannot be redacted this way; that residual leak is measured in E3.
"""

from __future__ import annotations

import re


def word_pattern(term: str) -> re.Pattern:
    """Whole-token match: 'Mark' must not match inside 'market'; '33602' must not match inside '1336029'."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)


class Redactor:
    def __init__(self, applicant: dict | None = None, enabled: bool = True):
        self.enabled = enabled
        self.patterns: list[tuple[re.Pattern, str]] = []
        if applicant and enabled:
            first, _, last = applicant["owner_name"].partition(" ")
            addr = applicant["address"]
            for term, repl in [(applicant["owner_name"], "[OWNER]"), (f"{last}, {first}", "[OWNER]"), (f"{last.upper()}, {first}", "[OWNER]"),
                               (last, "[OWNER]"), (first, "[OWNER]"), (addr["street"], "[ADDRESS]"), (addr["zip"], "[ZIP]")]:
                if term and len(term) > 2:
                    self.patterns.append((word_pattern(term), repl))

    def __call__(self, text: str) -> str:
        if not self.enabled:
            return text
        for pat, repl in self.patterns:
            text = pat.sub(repl, text)
        return text

    def obj(self, o):
        """Redact every string inside a JSON-like structure."""
        if isinstance(o, str):
            return self(o)
        if isinstance(o, list):
            return [self.obj(x) for x in o]
        if isinstance(o, dict):
            return {k: self.obj(v) for k, v in o.items()}
        return o


def leaked_terms(text: str, applicant: dict) -> list[str]:
    """Which sensitive tokens of this applicant still appear in `text` (for the E3 leak-rate metric)."""
    first, _, last = applicant["owner_name"].partition(" ")
    cands = {"owner_name": applicant["owner_name"], "first_name": first, "last_name": last, "zip": applicant["address"]["zip"],
             "street": applicant["address"]["street"]}
    return [k for k, v in cands.items() if v and word_pattern(v).search(text)]
