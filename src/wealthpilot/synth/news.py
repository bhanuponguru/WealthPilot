"""Synthetic adverse-media corpus: planted articles for flagged applicants plus decoys."""

from __future__ import annotations

import json
import random

from .applicants import OUT_DIR, load

NEWS_PATH = OUT_DIR / "news.json"

HIGH = ["was named in a federal investigation over alleged tax fraud", "faces a regulatory enforcement action for deceptive lending practices",
        "is the subject of a class-action lawsuit alleging wage theft"]
MEDIUM = ["was fined by a state regulator for repeated safety violations", "lost a major customer after a publicised contract dispute",
          "was cited for late payment of supplier invoices in a trade press report"]
LOW = ["received a minor consumer complaint that was later resolved", "was mentioned in a local report about a delayed permit"]
DECOY = ["opened a second location and hired twelve new employees", "sponsored a local youth sports league",
         "won a regional small-business award"]


def build(seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    arts = []
    for a in load():
        sev = a["planted"]["adverse_severity"]
        subject = a["business_name"]
        if sev:
            pool = {"high": HIGH, "medium": MEDIUM, "low": LOW}[sev]
            arts.append({"subject": subject, "owner": a["owner_name"], "severity": sev, "date": f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                         "headline": f"{subject} {rng.choice(pool)}", "source": rng.choice(["Regional Business Journal", "State Gazette", "Trade Weekly"])})
        if rng.random() < 0.25:  # benign decoy so a non-empty result is not itself a signal
            arts.append({"subject": subject, "owner": a["owner_name"], "severity": "none", "date": f"2024-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                         "headline": f"{subject} {rng.choice(DECOY)}", "source": "Local Chronicle"})
    NEWS_PATH.write_text(json.dumps(arts, indent=1))
    return arts


if __name__ == "__main__":
    print(len(build()), "articles ->", NEWS_PATH)
