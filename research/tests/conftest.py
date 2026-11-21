"""Research tests build their own synthetic world in a temporary folder, so they need no generated data and leave none behind."""

import pytest
from wealthpilot_lab.synth import applicants, groundtruth

from wealthpilot import screening


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    """(applicants, ground truth) for the 80-applicant population with seed 7, generated into a temporary folder."""
    root = tmp_path_factory.mktemp("lab")
    mp = pytest.MonkeyPatch()
    mp.setattr(applicants, "OUT_DIR", root / "demo")
    mp.setattr(screening, "WATCHLIST_CSV", root / "demo" / "watchlist.csv")
    mp.setattr(groundtruth, "DATA", root / "data")
    mp.setattr(groundtruth, "GT_PATH", root / "data" / "ground_truth.json")
    screening.reload()
    apps = applicants.generate(80, 7)
    gt = groundtruth.build()
    yield apps, gt
    mp.undo()
    screening.reload()
