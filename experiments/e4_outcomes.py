"""Post-process E4: classify every run's outcome against ground truth (strict policy) and append a table to e4_reliability.md.

correct                 = recommendation equals the ground truth
safe_refer              = degraded/uncertain run recommended 'refer' (a human decides)
escalated_doc_review    = run paused at the human document-review gate before any recommendation
wrongful_decline        = declined a case whose correct outcome is not decline   (harm to the applicant)
unsafe_approve          = approved a case whose correct outcome is not approve   (harm to the bank)
"""

import json

from common import RESULTS, md_table

PROFILES = ["none", "429_storm", "timeouts", "malformed_output", "mcp_flaky", "research_down", "fincalc_down"]


def main() -> None:
    d = json.loads((RESULTS / "e4_reliability.json").read_text())
    gt = json.loads((RESULTS.parent.parent / "data" / "synthetic" / "ground_truth.json").read_text())
    rows = []
    for prof in PROFILES:
        c = {"correct": 0, "safe_refer": 0, "escalated_doc_review": 0, "wrongful_decline": 0, "unsafe_approve": 0}
        rs = [r for r in d["runs"] if r["profile"] == prof]
        for r in rs:
            truth, rec = gt[r["case"]]["strict"]["recommendation"], r["rec"]
            key = "escalated_doc_review" if rec is None else "correct" if rec == truth else "safe_refer" if rec == "refer" else "unsafe_approve" if rec == "approve" else "wrongful_decline"
            c[key] += 1
        rows.append({"profile": prof, "runs": len(rs), **c})
    d["outcomes"] = rows
    (RESULTS / "e4_reliability.json").write_text(json.dumps(d, indent=2, default=str))
    md = (RESULTS / "e4_reliability.md").read_text().split("\n## Outcome classification")[0].rstrip() + "\n\n## Outcome classification (vs ground truth)\n" \
        + md_table(rows, ["profile", "runs", "correct", "safe_refer", "escalated_doc_review", "wrongful_decline", "unsafe_approve"])
    (RESULTS / "e4_reliability.md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
