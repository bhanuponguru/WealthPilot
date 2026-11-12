"""Typed case state shared by all nodes. Agents write typed results here; their chat messages stay private."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict


def _or(a: bool, b: bool) -> bool:
    return bool(a) or bool(b)


class CaseState(TypedDict, total=False):
    case_id: str
    policy_id: str
    applicant_id: str
    redaction: bool

    application: dict      # LLM-safe facts (redacted when redaction is on)
    sealed: dict           # identity + protected attributes: NEVER placed in a prompt
    doc_paths: dict        # {"financials": path, "bank": path}
    history: list          # prior decisions for this applicant (long-term memory)

    extracted: dict        # {fy: {field: number}}
    doc_kind: str          # text | image
    reconciliation_issues: list
    bank: dict
    bank_issues: list
    doc_review: dict       # human decision on document problems

    ratios: dict | None
    analysis: dict
    research: dict
    risk: dict
    thresholds: dict       # numeric thresholds the policy agent extracted from policy prose
    policy_checks: list    # [{rule_id, status, reason, evidence, extracted_threshold, citation}]
    required_tier: str
    grade: dict
    recommendation: str    # derived by the fixed decision rule from policy_checks (+ degraded cap)

    memo: dict
    validator_issues: list
    human_decision: dict
    final: dict

    loops: dict            # loop counters: policy / memo / revise
    degraded: Annotated[bool, _or]
    degraded_reasons: Annotated[list, operator.add]
    errors: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]
