"""First-start preparation: fetch the public data the product needs and index the credit policies."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

from .config import DATA_DIR

OFAC_URL = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
OFAC_PATH = DATA_DIR / "ofac" / "sdn.csv"


def fetch_ofac(force: bool = False) -> Path:
    """Download the OFAC SDN list unless it is already present. Raises on failure."""
    if OFAC_PATH.exists() and not force:
        return OFAC_PATH
    OFAC_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OFAC_PATH.with_suffix(".part")
    with httpx.stream("GET", OFAC_URL, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    if tmp.stat().st_size < 100_000:  # a real list is megabytes; anything tiny is an error page
        tmp.unlink()
        raise RuntimeError("the downloaded sanctions list looks incomplete")
    tmp.replace(OFAC_PATH)
    return OFAC_PATH


def main() -> int:
    """Prepare a fresh deployment. Failing to fetch the sanctions list is reported but does not stop start-up."""
    (DATA_DIR / "uploads").mkdir(parents=True, exist_ok=True)
    try:
        path = fetch_ofac()
        print(f"sanctions list ready: {path}")
    except Exception as e:  # noqa: BLE001
        print(f"WARNING: could not fetch the sanctions list ({type(e).__name__}: {e}). Screening will find no matches until it is available.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
