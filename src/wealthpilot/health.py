"""Service and artifact health checks, shared by `wealthpilot doctor` and the console's Overview/System pages.

Every check is fast (short timeouts), never raises, and returns a :class:`Check` with a plain-language detail and the command
that fixes it. Nothing here calls a paid or rate-limited API: the NIM key is only checked for presence.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

import httpx

from .config import PROJECT_ROOT, get_settings
from .mcp_client import SERVERS


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True


def _tcp(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_postgres() -> Check:
    fix = "docker compose up -d postgres"
    try:
        import psycopg
        with psycopg.connect(get_settings().database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return Check("Postgres", True, "reachable", fix)
    except Exception as e:  # noqa: BLE001
        return Check("Postgres", False, f"not reachable ({type(e).__name__})", fix)


def check_ollama() -> Check:
    s = get_settings()
    fix = f"ollama serve  &&  ollama pull {s.embed_model}"
    try:
        tags = httpx.get(f"{s.ollama_url}/api/tags", timeout=3).json().get("models", [])
        have = any(m.get("name", "").split(":")[0] == s.embed_model for m in tags)
        return Check("Ollama (embeddings)", have, "ready" if have else f"running, but model '{s.embed_model}' is not pulled", fix)
    except Exception as e:  # noqa: BLE001
        return Check("Ollama (embeddings)", False, f"not reachable ({type(e).__name__})", fix)


def check_mcp() -> list[Check]:
    out = []
    for name, port in SERVERS.items():
        ok = _tcp(port)
        out.append(Check(f"MCP: {name}", ok, f"port {port} {'open' if ok else 'closed'}", "uv run wealthpilot mcp-up"))
    return out


def check_mlflow() -> Check:
    uri = get_settings().mlflow_tracking_uri
    try:
        ok = httpx.get(f"{uri}/health", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        ok = False
    return Check("MLflow (traces)", ok, "reachable" if ok else "not reachable: tracing is skipped (non-fatal)", "make mlflow", required=False)


def check_nim_key() -> Check:
    try:
        get_settings()
        return Check("NVIDIA NIM key", True, "found (not validated)", "")
    except Exception:  # noqa: BLE001
        return Check("NVIDIA NIM key", False, "missing", "export NVIDIA_NIM_API_KEY=...   (or set it in .env)")


def check_artifacts() -> list[Check]:
    items = [
        ("Risk model", PROJECT_ROOT / "models" / "pd_model.joblib", "uv run wealthpilot train-pd", True),
        ("Synthetic applicants", PROJECT_ROOT / "data" / "synthetic" / "applicants.json", "uv run python -m wealthpilot.synth.applicants", False),
        ("Ground truth", PROJECT_ROOT / "data" / "synthetic" / "ground_truth.json", "uv run python -m wealthpilot.synth.groundtruth", False),
        ("OFAC list", PROJECT_ROOT / "data" / "ofac" / "sdn.csv", "see Installation: download the OFAC SDN list", False),
    ]
    return [Check(n, p.exists(), "present" if p.exists() else "missing", fix, required=req) for n, p, fix, req in items]


def run_all() -> list[Check]:
    return [check_postgres(), check_ollama(), *check_mcp(), check_nim_key(), *check_artifacts(), check_mlflow()]


def blocking(checks: list[Check]) -> list[Check]:
    """Failed checks that stop a run from working at all (Postgres, key, risk model, embeddings)."""
    must = {"Postgres", "NVIDIA NIM key", "Risk model", "Ollama (embeddings)"}
    return [c for c in checks if not c.ok and c.name in must]
