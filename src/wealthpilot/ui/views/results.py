"""Results page: the experiment reports that ship with the project (read from report/results)."""

from __future__ import annotations

import json

import streamlit as st

from ...config import PROJECT_ROOT

RESULTS = PROJECT_ROOT / "report" / "results"
EXPERIMENTS = [
    ("E0 · Policy adherence", "e0_policy.md", "Does it apply a policy written in prose correctly, and change its answer when the policy changes?"),
    ("E1 · Document parsing", "e1_parsing.md", "Field-level accuracy on clean, noisy-layout and scanned PDFs."),
    ("E2 · Policy RAG", "e2_rag.md", "Which retrieval design finds the right rule?"),
    ("E3 · Fairness (audit)", "e3_fairness_ab.md", "Proxy-group audit on real SBA data and planted-bias detection."),
    ("E3 · Identity counterfactuals", "e3_counterfactual.md", "Do names, gender or ZIP codes change outcomes? Does redaction work?"),
    ("E4 · Reliability", "e4_reliability.md", "Behaviour under injected faults, with outcome classes and crash/resume."),
]


def _headline() -> None:
    try:
        e0 = json.loads((RESULTS / "e0_policy.json").read_text())["per_policy"]
    except (OSError, KeyError, ValueError):
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Decision accuracy — strict policy", f"{e0['strict']['decision_acc']:.0%}")
    c2.metric("Decision accuracy — lenient policy", f"{e0['lenient']['decision_acc']:.0%}")
    c3.metric("Policy thresholds read correctly", f"{min(e0['strict']['threshold_acc'], e0['lenient']['threshold_acc']):.0%}")


def render() -> None:
    st.title("Experiments")
    st.caption("These reports are produced by the scripts in `experiments/` and stored in `report/results/`. Sample sizes are small (free model tier); they show "
               "mechanisms and failure modes rather than precise rates. The documentation site has the full write-up of each experiment.")
    if not RESULTS.exists():
        st.info("No results found. Run the experiment scripts (see the documentation) to generate them.")
        return
    _headline()
    tabs = st.tabs([name for name, _, _ in EXPERIMENTS] + ["Full report", "Ablations"])
    for tab, (name, fname, blurb) in zip(tabs, EXPERIMENTS):
        with tab:
            st.caption(blurb)
            f = RESULTS / fname
            if f.exists():
                st.markdown(f.read_text())
                if (RESULTS / fname.replace(".md", ".json")).exists():
                    st.download_button("⬇️ Raw results (JSON)", (RESULTS / fname.replace(".md", ".json")).read_bytes(), file_name=fname.replace(".md", ".json"),
                                       mime="application/json", key=f"dl-{fname}")
            else:
                st.info(f"`{fname}` has not been generated yet.")
    with tabs[len(EXPERIMENTS)]:
        rep = PROJECT_ROOT / "report" / "REPORT.md"
        st.markdown(rep.read_text() if rep.exists() else "_No report found._")
    with tabs[len(EXPERIMENTS) + 1]:
        st.caption("Earlier results superseded by a bug fix or design change, kept because each documents something the experiments caught.")
        dirs = sorted(d for d in list(RESULTS.glob("ablation_*")) + list(RESULTS.glob("_first_attempt")) if d.is_dir())
        if not dirs:
            st.info("No ablation results.")
        for d in dirs:
            with st.expander(d.name):
                for f in sorted(d.glob("*.md")):
                    st.markdown(f.read_text())
