"""Graph assembly + a Session/Runner API used by the CLI, the Streamlit console and the experiments."""

from __future__ import annotations

import hashlib
import time
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from ..compliance.redaction import Redactor
from ..config import get_settings
from ..observability import case_trace, enable as enable_tracing
from ..synth.render_docs import DOCS_DIR
from . import nodes as N
from .runtime import rt
from .state import CaseState


def build_graph(checkpointer, store=None):
    g = StateGraph(CaseState)
    for name, fn in [("intake", N.intake), ("parse", N.parse), ("doc_review", N.doc_review), ("analyst", N.analyst), ("analyst_retry", N.analyst_retry),
                     ("research", N.research), ("risk", N.risk), ("policy", N.policy), ("grade", N.grade), ("policy2", N.policy2), ("memo", N.memo),
                     ("memo_validator", N.memo_validator), ("human_approval", N.human_approval), ("finalize", N.finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "intake")
    g.add_edge("intake", "parse")
    g.add_conditional_edges("parse", N.route_after_parse, ["doc_review", "analyst", "research"])
    g.add_conditional_edges("doc_review", N.route_after_review, ["analyst", "research", "finalize"])
    g.add_edge(["analyst", "research"], "risk")          # join: both must finish
    g.add_edge("risk", "policy")
    g.add_conditional_edges("policy", N.route_after_policy, ["analyst_retry", "grade"])
    g.add_edge("analyst_retry", "policy")
    g.add_edge("grade", "policy2")
    g.add_edge("policy2", "memo")
    g.add_edge("memo", "memo_validator")
    g.add_conditional_edges("memo_validator", N.route_after_validator, ["memo", "human_approval"])
    g.add_conditional_edges("human_approval", N.route_after_approval, ["memo", "finalize"])
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer, store=store)


def make_input(applicant: dict, policy_id: str, variant: str = "clean", redaction: bool = True, docs_root=DOCS_DIR) -> dict:
    """Split an applicant record into LLM-safe facts (`application`) and identity (`sealed`), and point at the documents."""
    red = Redactor(applicant, enabled=redaction)
    sealed = {"owner_name": applicant["owner_name"], "business_name": applicant["business_name"], "gender": applicant["owner_gender"],
              "name_origin": applicant["name_origin"], "address": applicant["address"]}
    application = {"business_label": red(applicant["business_name"]), "industry_name": applicant["industry"]["name"], "naics": applicant["industry"]["naics"],
                   "years_in_business": applicant["years_in_business"], "loan_amount": applicant["loan_amount"], "term_months": applicant["term_months"],
                   "purpose": applicant["purpose"], "collateral_value": applicant["collateral_value"], "guarantor_provided": applicant["guarantor_provided"],
                   "profile": applicant["profile"]}
    d = docs_root / applicant["case_id"] / variant
    return {"case_id": applicant["case_id"], "policy_id": policy_id, "redaction": redaction, "application": application, "sealed": sealed,
            "applicant_id": hashlib.sha1((applicant["owner_name"] + applicant["business_name"]).encode()).hexdigest()[:10],
            "doc_paths": {"financials": str(d / "financials.pdf"), "bank": str(d / "bank_statement.pdf")},
            "degraded_reasons": [], "errors": [], "trace": []}


class Runner:
    def __init__(self, graph):
        self.graph = graph

    @staticmethod
    def cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    async def _drive(self, inp, thread_id: str, on_update=None) -> dict:
        meta = inp if isinstance(inp, dict) else (await self.graph.aget_state(self.cfg(thread_id))).values  # resume: read ids from the saved state
        with case_trace(meta.get("case_id", thread_id.split("-")[0]), meta.get("policy_id", "?"), thread_id, meta.get("redaction", True)):
            async for ev in self.graph.astream(inp, self.cfg(thread_id), stream_mode="updates"):
                if on_update:
                    on_update(ev)
        return await self.snapshot(thread_id)

    async def start(self, state_in: dict, thread_id: str | None = None, on_update=None) -> dict:
        return await self._drive(state_in, thread_id or state_in["case_id"], on_update)

    async def resume(self, thread_id: str, value: dict, on_update=None) -> dict:
        return await self._drive(Command(resume=value), thread_id, on_update)

    async def snapshot(self, thread_id: str) -> dict:
        snap = await self.graph.aget_state(self.cfg(thread_id))
        pending = [i.value for t in snap.tasks for i in t.interrupts]
        return {"values": snap.values, "next": list(snap.next), "interrupt": pending[0] if pending else None, "done": not snap.next}


@asynccontextmanager
async def session():
    """Open MCP tools, Postgres checkpointer and store; yield a Runner. Cleans up on exit."""
    dsn = get_settings().database_url
    enable_tracing()
    await rt.connect()
    async with AsyncPostgresSaver.from_conn_string(dsn) as cp, AsyncPostgresStore.from_conn_string(dsn) as store:
        await cp.setup()
        await store.setup()
        rt.store = store
        try:
            yield Runner(build_graph(cp, store))
        finally:
            rt.store = None


def new_thread_id(case_id: str, tag: str = "") -> str:
    return f"{case_id}-{tag or int(time.time())}"
