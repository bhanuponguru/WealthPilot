"""research MCP server: sanctions screening (real OFAC SDN + synthetic watchlist), adverse media, registry, SBA industry stats.

adverse_media and registry_lookup are MOCK external sources backed by the synthetic world, clearly labelled as such.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from rapidfuzz import fuzz

from wealthpilot import screening
from wealthpilot.config import PROJECT_ROOT

PORT = 8103
mcp = FastMCP("research", host="127.0.0.1", port=PORT)
SYN = PROJECT_ROOT / "data" / "synthetic"
STATS = PROJECT_ROOT / "data" / "sba" / "industry_stats.json"


def _json(path):
    return json.loads(path.read_text()) if path.exists() else []


@mcp.tool()
def ofac_screen(name: str) -> dict:
    """Screen a person or company name against the OFAC SDN list (and a synthetic watchlist). Fuzzy match, score 0-100.
    Returns matches with score >= 92; an empty list means no match."""
    hits = screening.screen(name)
    return {"name": name, "match_count": len(hits), "matches": hits}


@mcp.tool()
def adverse_media(subject: str, owner: str = "") -> dict:
    """Adverse-media search (MOCK corpus). Returns articles about the business or its owner with severity low|medium|high|none."""
    arts = []
    for a in _json(SYN / "news.json"):
        if fuzz.token_set_ratio(subject.lower(), a["subject"].lower()) >= 92 or (owner and a.get("owner", "").lower() == owner.lower()):
            arts.append({k: a[k] for k in ("headline", "severity", "date", "source")})
    rank = {"high": 3, "medium": 2, "low": 1, "none": 0}
    worst = max((a["severity"] for a in arts), key=lambda s: rank[s], default=None)
    return {"subject": subject, "article_count": len(arts), "max_severity": worst if worst != "none" else None, "articles": arts}


@mcp.tool()
def registry_lookup(business_name: str, state: str = "") -> dict:
    """Business registry lookup (MOCK). Returns registration status and incorporation year if found."""
    for a in _json(SYN / "applicants.json"):
        if fuzz.ratio(business_name.lower(), a["business_name"].lower()) >= 95 and (not state or state == a["address"]["state"]):
            return {"found": True, "status": "active", "incorporation_year": a["incorporation_year"], "state": a["address"]["state"]}
    return {"found": False}


@mcp.tool()
def industry_default_stats(naics2: str) -> dict:
    """5-year default rate for SBA 7(a) loans in a 2-digit NAICS sector (FY2010-2019), with sample size."""
    stats = json.loads(STATS.read_text()) if STATS.exists() else {}
    return stats.get(str(naics2), {"naics2": str(naics2), "default_rate": None, "n": 0})


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
