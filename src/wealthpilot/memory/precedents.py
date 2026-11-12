"""Semantic memory of decided cases (pgvector). Used for 'similar precedents' in memos. Informational only."""

from __future__ import annotations

from ..nim import embed
from ..nim.store import pool


def _init(c) -> None:
    c.execute("CREATE EXTENSION IF NOT EXISTS vector")
    c.execute("""CREATE TABLE IF NOT EXISTS precedents (
        case_id text PRIMARY KEY, summary text, decision text, grade text, embedding vector(768), created_at timestamptz DEFAULT now())""")


def add(case_id: str, summary: str, decision: str, grade: str) -> None:
    v = embed([summary], kind="document")[0]
    with pool().connection() as c:
        _init(c)
        c.execute("""INSERT INTO precedents (case_id, summary, decision, grade, embedding) VALUES (%s,%s,%s,%s,%s::vector)
                     ON CONFLICT (case_id) DO UPDATE SET summary=EXCLUDED.summary, decision=EXCLUDED.decision, grade=EXCLUDED.grade,
                     embedding=EXCLUDED.embedding""", (case_id, summary, decision, grade, str(v)))


def search(summary: str, k: int = 3, exclude_case: str | None = None) -> list[dict]:
    v = embed([summary], kind="query")[0]
    with pool().connection() as c:
        _init(c)
        rows = c.execute("""SELECT case_id, summary, decision, grade, 1 - (embedding <=> %s::vector) AS sim FROM precedents
                            WHERE case_id IS DISTINCT FROM %s ORDER BY embedding <=> %s::vector LIMIT %s""",
                         (str(v), exclude_case, str(v), k)).fetchall()
    return [{"case_id": r[0], "summary": r[1], "decision": r[2], "grade": r[3], "similarity": round(float(r[4]), 3)} for r in rows]
