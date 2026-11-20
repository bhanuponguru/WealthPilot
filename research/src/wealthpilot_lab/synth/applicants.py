"""Synthetic SME applicants with full ground truth.

Every applicant has true 3-year financial statements, a bank statement summary, a loan request,
SBA-like profile fields, a sealed protected attribute (owner gender / name origin), and planted
sanctions / adverse-media flags. Documents are rendered from this truth (see render_docs.py).
"""

from __future__ import annotations

import csv
import json
import random

from wealthpilot import screening
from wealthpilot.config import DEMO_DIR

OUT_DIR = DEMO_DIR  # applicants, documents, mock news and the watchlist: plain files the product's demo mode reads
LATEST_FY = 2024

from wealthpilot.catalog import INDUSTRIES as _INDUSTRIES  # noqa: F401
from wealthpilot.catalog import PROHIBITED as _PROHIBITED
from wealthpilot.catalog import PURPOSES

RANGES = {  # policy tag -> (gross-margin range, turnover range)
    "restaurant": ((0.55, 0.70), (0.9, 1.6)),
    "auto_repair": ((0.45, 0.60), (0.6, 1.1)),
    "software": ((0.60, 0.80), (0.8, 1.4)),
    "manufacturing": ((0.28, 0.42), (0.7, 1.2)),
    "retail": ((0.35, 0.50), (1.2, 2.2)),
    "logistics": ((0.20, 0.32), (0.8, 1.3)),
    "healthcare": ((0.55, 0.72), (0.9, 1.5)),
    "construction": ((0.22, 0.34), (1.0, 1.8)),
    "wholesale": ((0.18, 0.30), (1.5, 2.6)),
    "landscaping": ((0.40, 0.55), (1.0, 1.7)),
    "cannabis": ((0.40, 0.55), (1.0, 1.6)),
    "firearms": ((0.30, 0.42), (1.0, 1.6)),
    "gambling": ((0.50, 0.70), (0.5, 0.9)),
    "adult_entertainment": ((0.55, 0.70), (0.8, 1.3)),
    "crypto_exchange": ((0.55, 0.75), (0.4, 0.8)),
}

# (display name, policy tag, NAICS, gross-margin range, turnover range)
INDUSTRIES = [(n, t, c, *RANGES[t]) for n, t, c in _INDUSTRIES]
PROHIBITED = [(n, t, c, *RANGES[t]) for n, t, c in _PROHIBITED]  # appear with ~12% probability

# name origin groups are internal labels used only for counterfactual testing
FIRST = {
    ("g1", "male"): ["James", "Robert", "Thomas", "Daniel", "Mark", "Kevin", "Brian", "Paul"],
    ("g1", "female"): ["Mary", "Susan", "Karen", "Laura", "Emily", "Rachel", "Megan", "Julie"],
    ("g2", "male"): ["Carlos", "Miguel", "Javier", "Luis", "Diego", "Andres", "Rafael", "Hector"],
    ("g2", "female"): ["Maria", "Carmen", "Lucia", "Sofia", "Elena", "Rosa", "Isabel", "Ana"],
    ("g3", "male"): ["Rajesh", "Arjun", "Vikram", "Sanjay", "Amit", "Rohan", "Karthik", "Naveen"],
    ("g3", "female"): ["Priya", "Anita", "Sunita", "Kavya", "Neha", "Divya", "Meera", "Pooja"],
    ("g4", "male"): ["Chidi", "Kwame", "Tunde", "Emeka", "Kofi", "Jamal", "Darnell", "Malik"],
    ("g4", "female"): ["Amara", "Nia", "Imani", "Zuri", "Aisha", "Keisha", "Ngozi", "Tamika"],
}
LAST = {
    "g1": ["Whitfield", "Carlisle", "Hanson", "Prescott", "Mercer", "Garrity", "Holloway", "Sutton"],
    "g2": ["Alvarado", "Mendoza", "Fuentes", "Cordero", "Valdez", "Ibarra", "Segovia", "Zamora"],
    "g3": ["Venkataraman", "Choudhury", "Iyer", "Bhattacharya", "Nambiar", "Chaudhari", "Reddy", "Mahajan"],
    "g4": ["Okonkwo", "Adeyemi", "Boateng", "Mensah", "Washington", "Abara", "Coleman", "Nwosu"],
}
LOCATIONS = [  # city, state, zip, street
    ("Columbus", "OH", "43215", "410 Front St"), ("Tampa", "FL", "33602", "88 Bayshore Ave"),
    ("Denver", "CO", "80202", "1500 Blake St"), ("Fresno", "CA", "93721", "220 Fulton St"),
    ("Newark", "NJ", "07102", "75 Market St"), ("Houston", "TX", "77002", "930 Main St"),
    ("Detroit", "MI", "48226", "615 Griswold St"), ("Atlanta", "GA", "30303", "101 Peachtree St"),
    ("Boise", "ID", "83702", "300 Idaho St"), ("Memphis", "TN", "38103", "45 Beale St"),
    ("Tucson", "AZ", "85701", "180 Congress St"), ("Omaha", "NE", "68102", "1200 Harney St"),
]
BANK_NAMES = ["Summit Community Bank", "Riverbend Savings", "Harbor Trust"]


def _pick_person(rng: random.Random):
    origin = rng.choice(list(LAST))
    gender = rng.choice(["male", "female"])
    return origin, gender, rng.choice(FIRST[(origin, gender)]), rng.choice(LAST[origin])


def make_statements(rng: random.Random, ind, h: float, revenue: float, years: int) -> dict[str, dict]:
    """Return {fy: statements} oldest->newest, internally consistent."""
    gm = rng.uniform(*ind[3])
    turnover = rng.uniform(*ind[4])
    dep_pct = rng.uniform(0.02, 0.04)
    op_margin = min(0.02 + 0.30 * h + rng.gauss(0, 0.015), gm - dep_pct - 0.03)
    cr = max(0.7, 0.85 + 1.6 * h + rng.gauss(0, 0.12))
    de = min(6.0, max(0.25, 4.4 - 3.9 * h + rng.gauss(0, 0.35)))
    growth = [rng.gauss(0.03 + 0.10 * (h - 0.5), 0.04) for _ in range(years - 1)]
    revs = [revenue]
    for g in reversed(growth):
        revs.insert(0, revs[0] / (1 + g))
    out = {}
    ta_latest = revenue / turnover
    for i, rev in enumerate(revs):
        fy = LATEST_FY - (years - 1 - i)
        scale = rev / revenue
        jitter = lambda s=0.03: 1 + rng.gauss(0, s)  # noqa: E731
        cogs = rev * (1 - gm) * jitter(0.01)
        gp = rev - cogs
        dep = rev * dep_pct * jitter()
        oi = rev * (op_margin + rng.gauss(0, 0.008))
        opex = gp - dep - oi
        ta = ta_latest * scale * jitter()
        tl = ta * de / (1 + de)
        ca = ta * rng.uniform(0.40, 0.60)
        cl = min(ca / cr * jitter(), tl * 0.9)
        ltd_total = tl - cl
        cpltd = min(0.10 * ltd_total, cl * 0.5)
        interest = 0.07 * ltd_total
        ebt = oi - interest
        tax = max(0.0, 0.25 * ebt)
        ni = ebt - tax
        cash = ca * rng.uniform(0.25, 0.45)
        ar = ca * rng.uniform(0.30, 0.45)
        fs = {
            "revenue": rev, "cogs": cogs, "operating_expenses": opex, "depreciation": dep,
            "interest_expense": interest, "income_tax": tax, "net_income": ni,
            "cash": cash, "accounts_receivable": ar, "inventory": ca - cash - ar,
            "total_current_assets": ca, "net_fixed_assets": ta - ca, "total_assets": ta,
            "accounts_payable": cl - cpltd, "current_portion_ltd": cpltd, "total_current_liabilities": cl,
            "long_term_debt": ltd_total - cpltd, "total_liabilities": tl, "total_equity": ta - tl,
        }
        out[str(fy)] = {k: round(v) for k, v in fs.items()}
        # keep integers consistent
        f = out[str(fy)]
        f["net_income"] = f["revenue"] - f["cogs"] - f["operating_expenses"] - f["depreciation"] - f["interest_expense"] - f["income_tax"]
        f["inventory"] = f["total_current_assets"] - f["cash"] - f["accounts_receivable"]
        f["net_fixed_assets"] = f["total_assets"] - f["total_current_assets"]
        f["accounts_payable"] = f["total_current_liabilities"] - f["current_portion_ltd"]
        f["long_term_debt"] = f["total_liabilities"] - f["total_current_liabilities"]
        f["total_equity"] = f["total_assets"] - f["total_liabilities"]
    return out


def make_bank(rng: random.Random, latest: dict, owner: str, bank_name: str) -> dict:
    deposits_total = latest["revenue"] * rng.uniform(0.93, 1.03)
    wd_total = (latest["cogs"] + latest["operating_expenses"] + latest["interest_expense"]) * rng.uniform(0.95, 1.03)
    bal = max(5000, latest["cash"] * rng.uniform(0.5, 1.0))
    months = []
    seasonal = [rng.uniform(0.8, 1.2) for _ in range(12)]
    s = sum(seasonal)
    for m in range(12):
        dep = round(deposits_total * seasonal[m] / s)
        wd = round(wd_total * seasonal[(m + 3) % 12] / s)
        closing = bal + dep - wd
        notes = []
        if m in (2, 8):
            notes.append(f"Owner draw - {owner}")
        months.append({"month": f"2024-{m + 1:02d}", "opening": round(bal), "deposits": dep, "withdrawals": wd,
                       "closing": round(closing), "notes": notes})
        bal = closing
    return {"bank_name": bank_name, "months": months}


def generate(n: int = 80, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    applicants, watch = [], []
    for k in range(n):
        origin, gender, first, last = _pick_person(rng)
        # avoid accidental real-SDN hits for ordinary (non-planted) names
        while screening.screen(f"{first} {last}", threshold=88.0):
            origin, gender, first, last = _pick_person(rng)
        ind = rng.choice(PROHIBITED) if rng.random() < 0.12 else rng.choice(INDUSTRIES)
        h = min(1.0, max(0.0, rng.betavariate(2.8, 1.7)))
        revenue = round(rng.lognormvariate(13.5, 0.7), -3)  # ~ 700k median
        revenue = min(max(revenue, 250_000), 9_000_000)
        yib = rng.choice([1, 2, 3, 3, 4, 5, 5, 6, 8, 10, 12, 15, 20])
        n_years = min(3, yib) if yib < 3 else rng.choices([2, 3], weights=[0.15, 0.85])[0]
        n_years = max(n_years, 1)
        loan = round(revenue * rng.uniform(0.03, 0.38), -3)
        loan = max(loan, 25_000)
        term = rng.choice([60, 84, 84, 120, 120])
        statements = make_statements(rng, ind, h, revenue, n_years)
        collateral = round(loan * rng.choice([0, 0.4, 0.7, 0.9, 1.0, 1.1, 1.3, 1.6]), -3)
        loc = rng.choice(LOCATIONS)
        biz = f"{last} {ind[0].split(' and ')[0].split()[0]} {rng.choice(['LLC', 'Inc.', 'Co.', 'Group'])}"
        owner = f"{first} {last}"
        sev = rng.choices([None, "low", "medium", "high"], weights=[0.74, 0.10, 0.09, 0.07])[0]
        sanctions = rng.random() < 0.06
        if sanctions:
            # owner appears on the synthetic watchlist in "LAST, First" form
            watch.append({"name": f"{last.upper()}, {first}", "type": "individual", "program": "SYNTH-CRIME"})
        latest = statements[str(LATEST_FY)]
        applicants.append({
            "case_id": f"C{k + 1:03d}", "business_name": biz, "owner_name": owner, "owner_gender": gender, "name_origin": origin,
            "address": {"street": loc[3], "city": loc[0], "state": loc[1], "zip": loc[2]},
            "industry": {"name": ind[0], "tag": ind[1], "naics": ind[2]},
            "years_in_business": yib, "incorporation_year": 2025 - yib,
            "loan_amount": loan, "term_months": term, "purpose": rng.choice(PURPOSES),
            "collateral_value": collateral, "guarantor_provided": rng.random() < 0.80,
            "profile": {"state": loc[1], "business_type": rng.choices(["CORPORATION", "INDIVIDUAL", "PARTNERSHIP"], [0.8, 0.12, 0.08])[0],
                        "fixed_or_variable": rng.choice(["F", "V"]), "jobs_supported": rng.choice([0, 2, 4, 8, 15, 30]),
                        "franchise": rng.random() < 0.1},
            "statements": statements,
            "bank": make_bank(rng, latest, owner, rng.choice(BANK_NAMES)),
            "planted": {"sanctions_hit": sanctions, "adverse_severity": sev, "health": round(h, 3)},
        })
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(screening.WATCHLIST_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "type", "program"])
        w.writeheader()
        w.writerows(watch)
    screening.reload()
    (OUT_DIR / "applicants.json").write_text(json.dumps(applicants, indent=1))
    return applicants


def load() -> list[dict]:
    return json.loads((OUT_DIR / "applicants.json").read_text())


def truth_of(a: dict) -> dict:
    """Subset of an applicant consumed by the reference engine."""
    return {
        "years_in_business": a["years_in_business"], "industry_tag": a["industry"]["tag"], "statements": a["statements"],
        "loan_amount": a["loan_amount"], "term_months": a["term_months"], "collateral_value": a["collateral_value"],
        "guarantor_provided": a["guarantor_provided"], "sanctions_hit": a["planted"]["sanctions_hit"],
        "adverse_severity": a["planted"]["adverse_severity"],
    }


if __name__ == "__main__":
    apps = generate()
    print(f"generated {len(apps)} applicants -> {OUT_DIR / 'applicants.json'}")
