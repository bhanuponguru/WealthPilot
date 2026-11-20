"""Graph assembly + a Session/Runner API used by the CLI, the Streamlit console and the experiments."""

from __future__ import annotations

import asyncio
import hashlib
import time
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.postgres.aio import AsyncPostgresStore
from langgraph.types import Command

from ..compliance.redaction import Redactor
from ..config import get_settings
from ..observability import case_trace
from ..observability import enable as enable_tracing
from . import cases
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


def make_input_from_applicant(applicant: dict, policy_id: str, doc_paths: dict, redaction: bool = True) -> dict:
    """Split an applicant record into LLM-safe facts (`application`) and identity (`sealed`), and point at the documents.

    `applicant` needs: case_id, business_name, owner_name, owner_gender, name_origin, address{street,city,state,zip},
    industry{name,naics}, years_in_business, loan_amount, term_months, purpose, collateral_value, guarantor_provided, profile.
    """
    red = Redactor(applicant, enabled=redaction)
    sealed = {"owner_name": applicant["owner_name"], "business_name": applicant["business_name"], "gender": applicant["owner_gender"],
              "name_origin": applicant["name_origin"], "address": applicant["address"]}
    application = {"business_label": red(applicant["business_name"]), "industry_name": applicant["industry"]["name"], "naics": applicant["industry"]["naics"],
                   "years_in_business": applicant["years_in_business"], "loan_amount": applicant["loan_amount"], "term_months": applicant["term_months"],
                   "purpose": applicant["purpose"], "collateral_value": applicant["collateral_value"], "guarantor_provided": applicant["guarantor_provided"],
                   "profile": applicant["profile"]}
    return {"case_id": applicant["case_id"], "policy_id": policy_id, "redaction": redaction, "application": application, "sealed": sealed,
            "applicant_id": hashlib.sha1((applicant["owner_name"] + applicant["business_name"]).encode()).hexdigest()[:10],
            "doc_paths": {"financials": str(doc_paths["financials"]), "bank": str(doc_paths["bank"])},
            "degraded_reasons": [], "errors": [], "trace": []}


class Runner:
    def __init__(self, graph):
        self.graph = graph

    @staticmethod
    def cfg(thread_id: str) -> dict:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 60}

    async def _drive(self, inp, thread_id: str, on_update=None, meta: dict | None = None) -> dict:
        meta = meta or {}
        is_new = isinstance(inp, dict)
        state_meta = inp if is_new else (await self.graph.aget_state(self.cfg(thread_id))).values  # resume: read ids from the saved state
        if is_new:  # register the run immediately so the console can show it while it is still running
            await self._index(thread_id, status="running", case_id=inp.get("case_id"), policy_id=inp.get("policy_id"), redaction=inp.get("redaction"),
                              business_label=(inp.get("application") or {}).get("business_label"), loan_amount=(inp.get("application") or {}).get("loan_amount"), **meta)
        else:
            await self._index(thread_id, status="running")
        try:
            with case_trace(state_meta.get("case_id", thread_id.split("-")[0]), state_meta.get("policy_id", "?"), thread_id, state_meta.get("redaction", True)):
                async for ev in self.graph.astream(inp, self.cfg(thread_id), stream_mode="updates"):
                    if on_update:
                        on_update(ev)
        except Exception as e:  # noqa: BLE001 - record the failure for the console, then let the caller handle it
            await self._index(thread_id, status="error", error=f"{type(e).__name__}: {e}"[:500])
            raise
        snap = await self.snapshot(thread_id)
        try:
            await asyncio.to_thread(cases.record_snapshot, thread_id, snap)
        except Exception:  # noqa: BLE001 - the case index is best-effort
            pass
        return snap

    @staticmethod
    async def _index(thread_id: str, **fields) -> None:
        try:
            await asyncio.to_thread(cases.upsert, thread_id, **fields)
        except Exception:  # noqa: BLE001
            pass

    async def start(self, state_in: dict, thread_id: str | None = None, on_update=None, meta: dict | None = None) -> dict:
        """Run a new case until it finishes or needs a human. `meta` may carry `source` ('demo' | 'upload') and `variant`."""
        return await self._drive(state_in, thread_id or state_in["case_id"], on_update, meta)

    async def resume(self, thread_id: str, value: dict, on_update=None) -> dict:
        return await self._drive(Command(resume=value), thread_id, on_update)

    async def continue_run(self, thread_id: str, on_update=None) -> dict:
        """Pick an interrupted run (process killed, browser closed, transient error) up from its last checkpoint."""
        return await self._drive(None, thread_id, on_update)

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


@asynccontextmanager
async def readonly_session():
    """A Runner that can only READ saved cases (snapshots). No MCP connection, store or tracing: cheap enough to call on every page view."""
    async with AsyncPostgresSaver.from_conn_string(get_settings().database_url) as cp:
        await cp.setup()
        yield Runner(build_graph(cp, None))


def new_thread_id(case_id: str, tag: str = "") -> str:
    return f"{case_id}-{tag or int(time.time())}"
