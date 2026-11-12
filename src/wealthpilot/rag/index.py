"""Policy RAG: chunking (structure-aware vs fixed), pgvector index, BM25, hybrid RRF fusion, NIM rerank.

Every stage is switchable so experiment E2 can ablate it. The hidden reference.yaml is never indexed.
"""

from __future__ import annotations

import re
from functools import lru_cache

from rank_bm25 import BM25Okapi

from ..config import PROJECT_ROOT
from ..nim import embed, gateway
from ..nim.store import pool

POLICY_DIR = PROJECT_ROOT / "data" / "policies"
RULE_HEAD = re.compile(r"^## (CP-\d+)\s+(.*)$")
STRATEGIES = ("structure", "fixed")


def _sections(text: str) -> list[dict]:
    """Split markdown into '## ' sections, keeping the leading title block as its own section."""
    secs, cur = [], {"title": "Document header", "rule_id": None, "lines": []}
    for line in text.splitlines():
        if line.startswith("## "):
            secs.append(cur)
            m = RULE_HEAD.match(line)
            cur = {"title": m.group(2) if m else line[3:], "rule_id": m.group(1) if m else None, "lines": [line]}
        else:
            cur["lines"].append(line)
    secs.append(cur)
    return [dict(s, text="\n".join(s["lines"]).strip()) for s in secs if "\n".join(s["lines"]).strip()]


def chunk(policy_id: str, strategy: str, size: int = 450, overlap: int = 90) -> list[dict]:
    text = (POLICY_DIR / policy_id / "policy.md").read_text()
    secs = _sections(text)
    if strategy == "structure":
        return [{"title": s["title"], "rule_ids": [s["rule_id"]] if s["rule_id"] else [], "text": s["text"]} for s in secs]
    # fixed windows over the raw text, ignoring headings; record which rule sections each window overlaps
    spans, pos = [], 0
    for s in secs:
        i = text.find(s["text"][:60], pos)
        spans.append((i, i + len(s["text"]), s["rule_id"]))
        pos = max(pos, i)
    out, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        rids = sorted({r for a, b, r in spans if r and a < end and b > start})
        out.append({"title": f"window@{start}", "rule_ids": rids, "text": text[start:end]})
        if end == len(text):
            break
        start = end - overlap
    return out


def ingest(policy_id: str, strategy: str = "structure") -> int:
    chunks = chunk(policy_id, strategy)
    vecs = embed([f"{c['title']}\n{c['text']}" for c in chunks], kind="document")
    with pool().connection() as c:
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("""CREATE TABLE IF NOT EXISTS policy_chunks (
            id serial PRIMARY KEY, policy_id text, strategy text, chunk_idx int, rule_ids text[], title text, text text,
            embedding vector(768))""")
        c.execute("DELETE FROM policy_chunks WHERE policy_id = %s AND strategy = %s", (policy_id, strategy))
        for i, (ch, v) in enumerate(zip(chunks, vecs)):
            c.execute("INSERT INTO policy_chunks (policy_id, strategy, chunk_idx, rule_ids, title, text, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                      (policy_id, strategy, i, ch["rule_ids"], ch["title"], ch["text"], str(v)))
    _load.cache_clear()
    return len(chunks)


def ensure_indexed() -> None:
    for pid in sorted(p.name for p in POLICY_DIR.iterdir() if (p / "policy.md").exists()):
        for st in STRATEGIES:
            try:
                with pool().connection() as c:
                    n = c.execute("SELECT count(*) FROM policy_chunks WHERE policy_id=%s AND strategy=%s", (pid, st)).fetchone()[0]
            except Exception:
                n = 0
            if n == 0:
                ingest(pid, st)


@lru_cache
def _load(policy_id: str, strategy: str):
    with pool().connection() as c:
        rows = c.execute("SELECT id, rule_ids, title, text FROM policy_chunks WHERE policy_id=%s AND strategy=%s ORDER BY chunk_idx",
                         (policy_id, strategy)).fetchall()
    chunks = [{"id": r[0], "rule_ids": r[1] or [], "title": r[2], "text": r[3]} for r in rows]
    bm25 = BM25Okapi([_tok(c["title"] + " " + c["text"]) for c in chunks]) if chunks else None
    return chunks, bm25


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9\.]+", s.lower())


def search(query: str, policy_id: str, strategy: str = "structure", mode: str = "hybrid", use_rerank: bool = True,
           k: int = 4, pool_size: int = 10) -> dict:
    """mode: 'dense' | 'bm25' | 'hybrid' (RRF). Returns {'results': [...], 'degraded': bool}."""
    chunks, bm25 = _load(policy_id, strategy)
    if not chunks:
        return {"results": [], "degraded": True, "note": "policy not indexed"}
    ranks: dict[int, float] = {}

    def add(order: list[int]):
        for r, i in enumerate(order):
            ranks[i] = ranks.get(i, 0.0) + 1.0 / (60 + r + 1)

    if mode in ("bm25", "hybrid"):
        sc = bm25.get_scores(_tok(query))
        add(sorted(range(len(chunks)), key=lambda i: -sc[i])[:20])
    if mode in ("dense", "hybrid"):
        qv = embed([query], kind="query")[0]
        with pool().connection() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM policy_chunks WHERE policy_id=%s AND strategy=%s ORDER BY embedding <=> %s::vector LIMIT 20",
                                           (policy_id, strategy, str(qv))).fetchall()]
        by_id = {ch["id"]: i for i, ch in enumerate(chunks)}
        add([by_id[i] for i in ids if i in by_id])
    cand = sorted(ranks, key=lambda i: -ranks[i])[:pool_size]
    degraded = False
    if use_rerank and len(cand) > 1:
        try:
            scores = gateway.rerank(query, [chunks[i]["title"] + "\n" + chunks[i]["text"] for i in cand])
            cand = [i for _, i in sorted(zip(scores, cand), key=lambda t: -t[0])]
        except Exception:
            degraded = True  # reranker unavailable -> keep fused order, flag it
    out = [{"rank": r + 1, "rule_ids": chunks[i]["rule_ids"], "title": chunks[i]["title"], "text": chunks[i]["text"]} for r, i in enumerate(cand[:k])]
    return {"results": out, "degraded": degraded}


def list_rules(policy_id: str) -> list[dict]:
    chunks, _ = _load(policy_id, "structure")
    return [{"rule_id": c["rule_ids"][0], "title": c["title"]} for c in chunks if c["rule_ids"]]


def get_rule(policy_id: str, rule_id: str) -> dict | None:
    chunks, _ = _load(policy_id, "structure")
    for c in chunks:
        if rule_id in c["rule_ids"]:
            return {"rule_id": rule_id, "title": c["title"], "text": c["text"]}
    return None
