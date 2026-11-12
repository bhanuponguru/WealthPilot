"""Postgres-backed shared state for the NIM gateway: response cache, global token bucket, call log.

Every process (graph, MCP servers, experiments) imports this, so the ~40 RPM free-tier budget and the cache
are shared across all of them.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import time
from contextlib import contextmanager
from functools import lru_cache

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from ..config import get_settings

_tag: contextvars.ContextVar[str] = contextvars.ContextVar("wp_run_tag", default="")


@contextmanager
def run_tag(tag: str):
    """Label every NIM call made inside the block (e.g. a case id or experiment arm) in nim_calls."""
    token = _tag.set(tag)
    try:
        yield
    finally:
        _tag.reset(token)


@lru_cache
def pool() -> ConnectionPool:
    p = ConnectionPool(get_settings().database_url, min_size=1, max_size=10, kwargs={"autocommit": True}, open=True)
    _init_schema(p)
    return p


def _init_schema(p: ConnectionPool) -> None:
    with p.connection() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS nim_cache (
            key text PRIMARY KEY, kind text, model text, response jsonb, created_at timestamptz DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS nim_bucket (
            id int PRIMARY KEY, tokens double precision, updated_at timestamptz DEFAULT now())""")
        c.execute("INSERT INTO nim_bucket (id, tokens) VALUES (1, 5) ON CONFLICT DO NOTHING")
        c.execute("ALTER TABLE nim_bucket ADD COLUMN IF NOT EXISTS rpm double precision")
        c.execute("""CREATE TABLE IF NOT EXISTS nim_calls (
            id bigserial PRIMARY KEY, ts timestamptz DEFAULT now(), kind text, model text, cached boolean, ok boolean,
            latency_ms int, retries int, error text, prompt_tokens int, completion_tokens int, tag text)""")


def cache_key(kind: str, model: str, params: dict, payload) -> str:
    blob = json.dumps({"k": kind, "m": model, "p": params, "d": payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(key: str):
    if not get_settings().nim_cache_enabled:
        return None
    with pool().connection() as c:
        row = c.execute("SELECT response FROM nim_cache WHERE key = %s", (key,)).fetchone()
    return row[0] if row else None


def cache_put(key: str, kind: str, model: str, response) -> None:
    if not get_settings().nim_cache_enabled:
        return
    with pool().connection() as c:
        c.execute("INSERT INTO nim_cache (key, kind, model, response) VALUES (%s, %s, %s, %s) ON CONFLICT (key) DO NOTHING",
                  (key, kind, model, Jsonb(response)))


MIN_RPM = 6.0


def throttle(factor: float = 0.7) -> None:
    """A 429 was seen by some process: cut the SHARED rate (AIMD, multiplicative decrease) and drain the bucket."""
    with pool().connection() as c:
        c.execute("UPDATE nim_bucket SET rpm = GREATEST(%s, COALESCE(rpm, %s) * %s), tokens = 0, updated_at = now() WHERE id = 1",
                  (MIN_RPM, float(get_settings().nim_rpm_budget), factor))


def reward(step: float = 0.15) -> None:
    """A request succeeded: creep the shared rate back up towards the configured budget (additive increase)."""
    with pool().connection() as c:
        c.execute("UPDATE nim_bucket SET rpm = LEAST(%s, COALESCE(rpm, %s) + %s) WHERE id = 1",
                  (float(get_settings().nim_rpm_budget), float(get_settings().nim_rpm_budget), step))


def current_rpm() -> float:
    with pool().connection() as c:
        return float(c.execute("SELECT COALESCE(rpm, %s) FROM nim_bucket WHERE id = 1", (float(get_settings().nim_rpm_budget),)).fetchone()[0])


def acquire(rpm: int | None = None, capacity: float = 5.0) -> float:
    """Block until a request token is available (global across processes). Returns seconds waited.
    The rate is adaptive: throttle() lowers it on 429s, reward() raises it again on successes."""
    waited = 0.0
    while True:
        with pool().connection() as c, c.transaction():
            tokens, elapsed, cur = c.execute(
                "SELECT tokens, EXTRACT(EPOCH FROM (now() - updated_at)), COALESCE(rpm, %s) FROM nim_bucket WHERE id = 1 FOR UPDATE",
                (float(rpm or get_settings().nim_rpm_budget),)).fetchone()
            rate = float(cur) / 60.0
            tokens = min(capacity, float(tokens) + float(elapsed) * rate)
            if tokens >= 1.0:
                c.execute("UPDATE nim_bucket SET tokens = %s, updated_at = now() WHERE id = 1", (tokens - 1.0,))
                return waited
            wait = (1.0 - tokens) / rate
        time.sleep(min(wait, 3.0))
        waited += min(wait, 3.0)


def log_call(kind: str, model: str, cached: bool, ok: bool, latency_ms: int, retries: int = 0, error: str | None = None,
             prompt_tokens: int | None = None, completion_tokens: int | None = None) -> None:
    try:
        with pool().connection() as c:
            c.execute("""INSERT INTO nim_calls (kind, model, cached, ok, latency_ms, retries, error, prompt_tokens, completion_tokens, tag)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                      (kind, model, cached, ok, latency_ms, retries, (error or "")[:300] or None, prompt_tokens, completion_tokens, _tag.get() or None))
    except Exception:  # logging must never break a call
        pass


def reset_state(clear_cache: bool = False, clear_calls: bool = False) -> None:
    with pool().connection() as c:
        if clear_cache:
            c.execute("TRUNCATE nim_cache")
        if clear_calls:
            c.execute("TRUNCATE nim_calls")
        c.execute("UPDATE nim_bucket SET tokens = 5, rpm = NULL, updated_at = now() WHERE id = 1")
