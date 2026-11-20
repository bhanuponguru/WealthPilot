"""Service and artifact health checks, shared by `wealthpilot doctor` and the console's sidebar and System page.

Every check is fast (short timeouts), never raises, and returns a :class:`Check` with a plain-language detail and the command
that fixes it. Nothing here calls a paid or rate-limited API: the NIM key is only checked for presence.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

import httpx

from .config import ARTIFACTS_DIR, DATA_DIR, DEMO_DIR, DEMO_MODE, MCP_HOST, get_settings
from .mcp_client import SERVERS


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    fix: str = ""
    required: bool = True


def _tcp(port: int, host: str = MCP_HOST, timeout: float = 1.0) -> bool:
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
    fix = f"docker compose up -d ollama ollama-pull   (local install: ollama serve && ollama pull {s.embed_model})"
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
        out.append(Check(f"MCP: {name}", ok, f"port {port} {'open' if ok else 'closed'}", "docker compose up -d mcp   (local install: uv run wealthpilot mcp-up)"))
    return out


def check_mlflow() -> Check:
    uri = get_settings().mlflow_tracking_uri
    try:
        ok = httpx.get(f"{uri}/health", timeout=2).status_code == 200
    except Exception:  # noqa: BLE001
        ok = False
    return Check("MLflow (traces)", ok, "reachable" if ok else "not reachable: tracing is skipped (non-fatal)", "docker compose up -d mlflow   (local install: make mlflow)", required=False)


def check_nim_key() -> Check:
    try:
        get_settings()
        return Check("Model API key", True, "found (not validated)", "")
    except Exception:  # noqa: BLE001
        return Check("Model API key", False, "missing", "set NVIDIA_API_KEY (or NVIDIA_NIM_API_KEY) in the environment or .env, then restart the services")


def check_artifacts() -> list[Check]:
    items = [
        ("Risk model", ARTIFACTS_DIR / "pd_model.joblib", "restore the artifacts folder (local install: uv run wealthpilot train-pd, which needs the SBA data)", True),
        ("Sanctions list", DATA_DIR / "ofac" / "sdn.csv", "docker compose run --rm bootstrap   (local install: uv run wealthpilot fetch-ofac)", False),
    ]
    if DEMO_MODE:
        items.append(("Demo data", DEMO_DIR / "applicants.json", "generate it with the research package (see the documentation)", False))
    out = []
    for n, p, fix, req in items:
        ok = p.exists()
        detail = "present" if ok else ("missing: screening will find no matches" if n == "Sanctions list" else "missing")
        out.append(Check(n, ok, detail, fix, required=req))
    return out


def run_all() -> list[Check]:
    return [check_postgres(), check_ollama(), *check_mcp(), check_nim_key(), *check_artifacts(), check_mlflow()]


def blocking(checks: list[Check]) -> list[Check]:
    """Failed checks that stop a run from working at all (Postgres, key, risk model, embeddings)."""
    must = {"Postgres", "Model API key", "Risk model", "Ollama (embeddings)"}
    return [c for c in checks if not c.ok and c.name in must]
