"""Start the three MCP servers as separate processes: `uv run python -m wealthpilot.mcp_up` (Ctrl-C stops all)."""

from __future__ import annotations

import signal
import subprocess
import sys
import time

from .config import PROJECT_ROOT

MODULES = ["mcp_servers.fincalc.server", "mcp_servers.policydocs.server", "mcp_servers.research.server"]


def start() -> list[subprocess.Popen]:
    return [subprocess.Popen([sys.executable, "-m", m], cwd=PROJECT_ROOT) for m in MODULES]


def stop(procs: list[subprocess.Popen]) -> None:
    for p in procs:
        p.terminate()
    for p in procs:
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> None:
    procs = start()
    signal.signal(signal.SIGTERM, lambda *_: (stop(procs), sys.exit(0)))
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop(procs)


if __name__ == "__main__":
    main()
