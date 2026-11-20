"""Where the research package keeps its inputs and outputs (all inside the research folder)."""

from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
RESULTS = LAB_ROOT / "results"            # experiment reports (committed)
DATA = LAB_ROOT / "data"                  # generated research data: ground truth, counterfactual documents (not committed)
REFERENCE = LAB_ROOT / "reference"        # the hidden answer key for each credit policy
