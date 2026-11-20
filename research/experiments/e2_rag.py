"""E2: policy RAG ablation. Gold = which rule section answers the query. Metrics: recall@1, recall@3, MRR, 95% bootstrap CI.

Arms: chunking (structure-aware vs fixed windows) x retrieval (BM25 / dense / hybrid RRF) x NIM rerank (off/on).
A hit means the gold rule id is among the rules the retrieved chunk covers (generous to 'fixed' chunks, which can span rules).
"""

from __future__ import annotations

from common import bootstrap_ci, log_mlflow, md_table, save

from wealthpilot.rag import index

QUERIES = {
    "CP-1": ["What is the minimum operating history required?", "How long must a business have been operating to qualify?",
             "Our applicant was incorporated recently; is that a problem?", "years in business requirement"],
    "CP-2": ["Which industries are prohibited?", "Can the bank lend to a casino operator?", "list of businesses the bank will not finance",
             "is a cryptocurrency exchange an eligible borrower"],
    "CP-3": ["What is the minimum DSCR?", "What debt service coverage ratio is needed to pass?", "cash flow is thin compared with the loan payments; what does the policy say",
             "is there an exception if coverage is slightly below the minimum"],
    "CP-4": ["What is the maximum debt-to-equity ratio?", "how much leverage is allowed?", "what if the borrower has negative equity", "limit on total liabilities relative to equity"],
    "CP-5": ["What is the minimum current ratio?", "liquidity requirement for applicants", "what working capital cushion is required", "minimum ratio of current assets to current liabilities"],
    "CP-6": ["What is the maximum loan relative to revenue?", "how large can the loan be compared with annual sales", "loan-to-revenue cap", "requested amount versus yearly revenue limit"],
    "CP-7": ["How many years of financial statements must be provided?", "documentation required from the applicant", "does a company with only one year of accounts qualify",
             "income statement and balance sheet requirement"],
    "CP-8": ["When is collateral required?", "What collateral coverage is needed for larger loans?", "loan above the threshold with no security pledged", "minimum collateral coverage percentage"],
    "CP-9": ["Is a personal guarantee required?", "when must the owner personally guarantee the loan", "can a small loan be made without a guarantor", "guarantee requirement for newer businesses"],
    "CP-10": ["How must sanctions screening be handled?", "what happens if the applicant matches a sanctions list", "OFAC screening requirement", "confirmed watchlist hit action"],
    "CP-11": ["How is adverse media treated?", "negative news about the owner; what does the policy say", "which severity of adverse media triggers referral to committee", "media findings exceptions"],
    "CP-12": ["What risk grades are acceptable?", "worst internal grade that can be approved", "is grade D acceptable", "risk rating cutoff"],
    "CP-13": ["Who has authority to approve a loan?", "approval limits for analysts", "which approver tier is needed for a large loan", "delegation of authority thresholds"],
}
ARMS = [  # (chunking, mode, rerank)
    ("structure", "bm25", False), ("structure", "dense", False), ("structure", "hybrid", False),
    ("structure", "bm25", True), ("structure", "dense", True), ("structure", "hybrid", True),
    ("fixed", "bm25", False), ("fixed", "dense", False), ("fixed", "hybrid", False), ("fixed", "hybrid", True),
]


def main() -> dict:
    index.ensure_indexed()
    gold = [(pid, rid, q) for pid in ("strict", "lenient") for rid, qs in QUERIES.items() for q in qs]
    results, rows = {}, []
    for chunking, mode, rerank in ARMS:
        name = f"{chunking}/{mode}{'+rerank' if rerank else ''}"
        rr1, rr3, rrr, degraded = [], [], [], 0
        for pid, rid, q in gold:
            res = index.search(q, pid, strategy=chunking, mode=mode, use_rerank=rerank, k=3)
            degraded += res["degraded"] and rerank
            ranks = [i for i, r in enumerate(res["results"], 1) if rid in r["rule_ids"]]
            first = ranks[0] if ranks else None
            rr1.append(1.0 if first == 1 else 0.0)
            rr3.append(1.0 if first else 0.0)
            rrr.append(1.0 / first if first else 0.0)
        r = {"arm": name, "n_queries": len(gold), "recall@1": round(sum(rr1) / len(rr1), 3), "recall@3": round(sum(rr3) / len(rr3), 3), "MRR": round(sum(rrr) / len(rrr), 3),
             "MRR_95CI": bootstrap_ci(rrr), "rerank_degraded": int(degraded)}
        results[name] = r
        rows.append({**r, "MRR_95CI": f"{r['MRR_95CI'][0]}-{r['MRR_95CI'][1]}"})
        print(name, r["recall@1"], r["recall@3"], r["MRR"], flush=True)
        log_mlflow("wealthpilot-E2-rag", name, {"chunking": chunking, "mode": mode, "rerank": rerank}, {"recall_at_1": r["recall@1"], "recall_at_3": r["recall@3"], "mrr": r["MRR"]})
    md = "# E2: Policy RAG ablation\n\n" + md_table(rows, ["arm", "n_queries", "recall@1", "recall@3", "MRR", "MRR_95CI", "rerank_degraded"])
    save("e2_rag", {"arms": results}, md)
    return results


if __name__ == "__main__":
    main()
