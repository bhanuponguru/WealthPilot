"""Shared experiment helpers: bootstrap CIs, result files, MLflow logging (never fatal)."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from wealthpilot.config import PROJECT_ROOT

RESULTS = PROJECT_ROOT / "report" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(c - h, 4), round(c + h, 4))


def bootstrap_ci(values: list[float], n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    if not values:
        return (0.0, 0.0)
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(values) for _ in values) / len(values) for _ in range(n_boot))
    return (round(means[int(0.025 * n_boot)], 4), round(means[int(0.975 * n_boot)], 4))


def save(name: str, data: dict, markdown: str = "") -> Path:
    (RESULTS / f"{name}.json").write_text(json.dumps(data, indent=2, default=str))
    if markdown:
        (RESULTS / f"{name}.md").write_text(markdown)
    return RESULTS / f"{name}.json"


def log_mlflow(experiment: str, run_name: str, params: dict, metrics: dict, artifact: Path | None = None) -> None:
    try:
        import mlflow

        from wealthpilot.config import get_settings
        mlflow.set_tracking_uri(get_settings().mlflow_tracking_uri)
        mlflow.set_experiment(experiment)
        with mlflow.start_run(run_name=run_name):
            mlflow.log_params({k: str(v)[:250] for k, v in params.items()})
            mlflow.log_metrics({k: float(v) for k, v in metrics.items() if isinstance(v, (int, float))})
            if artifact:
                mlflow.log_artifact(str(artifact))
    except Exception as e:  # noqa: BLE001
        print("MLflow logging skipped:", type(e).__name__)


def md_table(rows: list[dict], cols: list[str]) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|\n"
    return head + "\n".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows) + "\n"
