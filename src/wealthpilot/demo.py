"""Optional demonstration data: sample applicants with ready-made statements, so the system can be tried without real documents.

Demo mode is off unless ``WEALTHPILOT_DEMO`` is set. The data is a set of plain files in the demo folder (applicants,
statement PDFs in three layouts, and the mock news and registry sources); nothing here depends on how they were produced.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import DEMO_DIR, DEMO_MODE
from .graph.builder import make_input_from_applicant

VARIANTS = ("clean", "noisy", "scanned")


def enabled() -> bool:
    return DEMO_MODE and (DEMO_DIR / "applicants.json").exists()


def applicants() -> list[dict]:
    path = DEMO_DIR / "applicants.json"
    return json.loads(path.read_text()) if path.exists() else []


def docs_dir(case_id: str, variant: str = "clean") -> Path:
    return DEMO_DIR / "docs" / case_id / variant


def make_input(applicant: dict, policy_id: str, variant: str = "clean", redaction: bool = True) -> dict:
    """Graph input for a sample applicant, pointing at its statements in the given layout."""
    d = docs_dir(applicant["case_id"], variant)
    return make_input_from_applicant(applicant, policy_id, {"financials": d / "financials.pdf", "bank": d / "bank_statement.pdf"}, redaction)
