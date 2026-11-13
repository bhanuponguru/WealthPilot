"""Case index: one row per underwriting run, so the console can list, filter and reopen cases.

LangGraph checkpoints hold the full state of every thread but are not designed for listing. This small table (``case_runs``)
mirrors the headline facts and the lifecycle status of each run. It is best-effort: failures here never affect underwriting.

Statuses: ``running`` -> ``awaiting_doc_review`` | ``awaiting_approval`` -> ``decided``  (or ``error``).
"""

from __future__ import annotations

from ..nim.store import pool

STATUSES = ("running", "awaiting_doc_review", "awaiting_approval", "decided", "finished", "error")

_COLUMNS = ("thread_id", "case_id", "policy_id", "variant", "source", "redaction", "business_label", "loan_amount", "status",
            "recommendation", "decision", "grade", "required_tier", "degraded", "error", "created_at", "updated_at")


def _init(c) -> None:
    c.execute("""CREATE TABLE IF NOT EXISTS case_runs (
        thread_id text PRIMARY KEY, case_id text, policy_id text, variant text, source text, redaction boolean,
        business_label text, loan_amount double precision, status text, recommendation text, decision text, grade text,
        required_tier text, degraded boolean, error text,
        created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now())""")


def status_of(snap: dict) -> str:
    """Lifecycle status implied by a runner snapshot."""
    intr = (snap.get("interrupt") or {}).get("type")
    if intr == "approval":
        return "awaiting_approval"
    if intr == "doc_review":
        return "awaiting_doc_review"
    if snap.get("done"):
        return "decided" if snap["values"].get("final") else "finished"
    return "running"


def fields_from_snapshot(snap: dict) -> dict:
    """Headline facts to mirror into the index (never includes identity: the label is already redacted when redaction is on)."""
    v = snap["values"]
    app = v.get("application") or {}
    final = v.get("final") or {}
    return {
        "case_id": v.get("case_id"), "policy_id": v.get("policy_id"), "redaction": v.get("redaction"),
        "business_label": app.get("business_label"), "loan_amount": app.get("loan_amount"), "status": status_of(snap),
        "recommendation": v.get("recommendation"), "decision": final.get("decision"), "grade": (v.get("grade") or {}).get("grade"),
        "required_tier": v.get("required_tier"), "degraded": bool(v.get("degraded")), "error": "",  # "" clears an old error; None would be ignored
    }


def upsert(thread_id: str, **fields) -> None:
    """Insert or update a run. Unknown keys are ignored; ``None`` values do not overwrite existing data."""
    data = {k: v for k, v in fields.items() if k in _COLUMNS and k not in ("thread_id", "created_at", "updated_at") and v is not None}
    cols = ["thread_id", *data]
    sets = ", ".join(f"{k} = EXCLUDED.{k}" for k in data) + (", " if data else "") + "updated_at = now()"
    sql = f"INSERT INTO case_runs ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT (thread_id) DO UPDATE SET {sets}"
    with pool().connection() as c:
        _init(c)
        c.execute(sql, [thread_id, *data.values()])


def record_snapshot(thread_id: str, snap: dict, meta: dict | None = None) -> None:
    upsert(thread_id, **fields_from_snapshot(snap), **(meta or {}))


def record_error(thread_id: str, message: str, meta: dict | None = None) -> None:
    upsert(thread_id, status="error", error=message[:500], **(meta or {}))


def _rows(cursor) -> list[dict]:
    return [dict(zip(_COLUMNS, r)) for r in cursor.fetchall()]


def list_cases(statuses: list[str] | None = None, search: str = "", limit: int = 300) -> list[dict]:
    """Most recently updated first. ``search`` matches thread id, case id or business label (case-insensitive)."""
    where, args = [], []
    if statuses:
        where.append("status = ANY(%s)")
        args.append(list(statuses))
    if search.strip():
        where.append("(thread_id ILIKE %s OR case_id ILIKE %s OR business_label ILIKE %s)")
        args += [f"%{search.strip()}%"] * 3
    sql = f"SELECT {', '.join(_COLUMNS)} FROM case_runs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY updated_at DESC LIMIT %s"
    with pool().connection() as c:
        _init(c)
        return _rows(c.execute(sql, [*args, limit]))


def get(thread_id: str) -> dict | None:
    with pool().connection() as c:
        _init(c)
        rows = _rows(c.execute(f"SELECT {', '.join(_COLUMNS)} FROM case_runs WHERE thread_id = %s", (thread_id,)))
    return rows[0] if rows else None


def counts() -> dict[str, int]:
    with pool().connection() as c:
        _init(c)
        return {s: n for s, n in c.execute("SELECT status, count(*) FROM case_runs GROUP BY status").fetchall()}
