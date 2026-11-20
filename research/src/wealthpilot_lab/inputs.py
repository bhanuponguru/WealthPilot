"""Workflow inputs for synthetic applicants, optionally with documents rendered somewhere other than the demonstration folder."""

from __future__ import annotations

from pathlib import Path

from wealthpilot.graph.builder import make_input_from_applicant

from .synth.render_docs import DOCS_DIR


def make_input(applicant: dict, policy_id: str, variant: str = "clean", redaction: bool = True, docs_root: Path = DOCS_DIR) -> dict:
    d = docs_root / applicant["case_id"] / variant
    return make_input_from_applicant(applicant, policy_id, {"financials": d / "financials.pdf", "bank": d / "bank_statement.pdf"}, redaction)
