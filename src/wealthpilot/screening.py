"""Sanctions-list screening: the OFAC SDN list, plus an optional extra watchlist (the demonstration data ships one)."""

from __future__ import annotations

import csv
import re
from functools import lru_cache

from rapidfuzz import fuzz, process

from .config import DATA_DIR, DEMO_DIR

SDN_CSV = DATA_DIR / "ofac" / "sdn.csv"
WATCHLIST_CSV = DEMO_DIR / "watchlist.csv"
THRESHOLD = 92.0


def normalize(name: str) -> str:
    name = name.strip()
    if "," in name:  # "LAST, First" -> "First LAST"
        last, _, first = name.partition(",")
        name = f"{first} {last}"
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


@lru_cache
def _entries() -> tuple[list[str], list[dict]]:
    names, meta = [], []
    if SDN_CSV.exists():
        with open(SDN_CSV, newline="", encoding="latin-1") as f:
            for row in csv.reader(f):
                if len(row) < 4:
                    continue
                names.append(normalize(row[1]))
                meta.append({"list": "OFAC-SDN", "name": row[1], "type": row[2].strip(), "program": row[3].strip()})
    if WATCHLIST_CSV.exists():
        with open(WATCHLIST_CSV, newline="") as f:
            for row in csv.DictReader(f):
                names.append(normalize(row["name"]))
                meta.append({"list": "WATCHLIST", "name": row["name"], "type": row.get("type", ""), "program": row.get("program", "")})
    return names, meta


def reload() -> None:
    _entries.cache_clear()


def screen(name: str, threshold: float = THRESHOLD, limit: int = 3) -> list[dict]:
    """Fuzzy-match `name` against all lists. Returns matches with score >= threshold."""
    names, meta = _entries()
    if not names or not name.strip():
        return []
    q = normalize(name)
    hits = process.extract(q, names, scorer=fuzz.token_sort_ratio, score_cutoff=threshold, limit=limit)
    return [dict(meta[i], score=round(score, 1)) for _, score, i in hits]
