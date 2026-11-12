"""Append-only, hash-chained audit log in Postgres. Each record's hash covers the previous hash, so any edit or
deletion of history breaks verification."""

from __future__ import annotations

import hashlib
import json

from psycopg.types.json import Jsonb

from ..nim.store import pool


def _init(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS audit_log (
        id bigserial PRIMARY KEY, ts timestamptz DEFAULT now(), case_id text, event text, payload jsonb,
        prev_hash text, hash text)""")


def _digest(prev: str, case_id: str, event: str, payload: dict) -> str:
    blob = json.dumps({"p": prev, "c": case_id, "e": event, "d": payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def append(case_id: str, event: str, payload: dict) -> str:
    payload = json.loads(json.dumps(payload, default=str))
    with pool().connection() as c, c.transaction():
        _init(c)
        c.execute("LOCK TABLE audit_log IN EXCLUSIVE MODE")  # serialise chain extension
        row = c.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = row[0] if row else "GENESIS"
        h = _digest(prev, case_id, event, payload)
        c.execute("INSERT INTO audit_log (case_id, event, payload, prev_hash, hash) VALUES (%s,%s,%s,%s,%s)", (case_id, event, Jsonb(payload), prev, h))
    return h


def verify() -> dict:
    """Recompute the whole chain. Returns {'ok': bool, 'records': n, 'first_bad_id': id|None}."""
    with pool().connection() as c:
        _init(c)
        rows = c.execute("SELECT id, case_id, event, payload, prev_hash, hash FROM audit_log ORDER BY id").fetchall()
    prev = "GENESIS"
    for rid, case_id, event, payload, prev_hash, h in rows:
        if prev_hash != prev or _digest(prev, case_id, event, payload) != h:
            return {"ok": False, "records": len(rows), "first_bad_id": rid}
        prev = h
    return {"ok": True, "records": len(rows), "first_bad_id": None}
