"""Ground truth per applicant: PD (from the trained SBA model) + reference-engine results under every policy."""

from __future__ import annotations

import json

from ..policy_ref import evaluate_case, load_reference
from ..risk import pd_model
from .applicants import OUT_DIR, load, truth_of

GT_PATH = OUT_DIR / "ground_truth.json"
POLICIES = ["strict", "lenient"]


def score_applicant(a: dict) -> dict:
    X = pd_model.applicant_features(a["profile"], a["loan_amount"], a["term_months"], a["years_in_business"],
                                    a["industry"]["naics"], a["collateral_value"] > 0)
    return pd_model.score(X)


def build() -> dict:
    gt = {}
    for a in load():
        risk = score_applicant(a)
        gt[a["case_id"]] = {"pd": risk["pd"], "reasons": risk["reasons"],
                            **{p: evaluate_case(truth_of(a), risk["pd"], load_reference(p)) for p in POLICIES}}
    GT_PATH.write_text(json.dumps(gt, indent=1))
    return gt


def load_gt() -> dict:
    return json.loads(GT_PATH.read_text())


if __name__ == "__main__":
    import collections
    gt = build()
    pds = sorted(v["pd"] for v in gt.values())
    print("PD quantiles:", [pds[int(q * (len(pds) - 1))] for q in (0, .1, .25, .5, .75, .9, 1)])
    for p in POLICIES:
        print(p, dict(collections.Counter(v[p]["recommendation"] for v in gt.values())),
              "grades", dict(sorted(collections.Counter(v[p]["grade"]["grade"] for v in gt.values()).items())))
    print("decision differs between policies:", sum(v["strict"]["recommendation"] != v["lenient"]["recommendation"] for v in gt.values()))
