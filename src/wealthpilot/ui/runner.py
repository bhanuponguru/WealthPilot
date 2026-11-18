"""Background run manager: underwriting runs must not depend on the browser tab staying open.

A Streamlit script runs on the page's script thread and is stopped as soon as the user switches page or closes the tab, which
would abandon a run half-way and leave the case marked "running". Instead, runs execute on one long-lived worker thread with
its own event loop. The page only *watches* a run (``progress``); leaving and coming back loses nothing.

If the whole console process is restarted mid-run the worker dies with it; such cases show as "interrupted" (status running, but
not active here) and ``continue_run`` resumes them from their last checkpoint.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..graph.builder import session


@dataclass
class RunProgress:
    thread_id: str
    label: str = ""
    started: float = field(default_factory=time.time)
    events: list[tuple[str, float]] = field(default_factory=list)   # (graph node, seconds since start)
    done: bool = False
    error: str | None = None
    snapshot: dict | None = None


class RunManager:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._runs: dict[str, RunProgress] = {}
        self._lock = threading.Lock()
        threading.Thread(target=self._loop.run_forever, name="wealthpilot-runs", daemon=True).start()

    def progress(self, thread_id: str) -> RunProgress | None:
        return self._runs.get(thread_id)

    def is_active(self, thread_id: str) -> bool:
        p = self._runs.get(thread_id)
        return bool(p and not p.done)

    def active_threads(self) -> list[str]:
        return [t for t, p in self._runs.items() if not p.done]

    def _submit(self, thread_id: str, work: Callable[[Any, Callable[[dict], None]], Any], label: str = "") -> RunProgress:
        with self._lock:
            if self.is_active(thread_id):
                return self._runs[thread_id]
            prog = self._runs[thread_id] = RunProgress(thread_id, label)

        def on_update(ev: dict) -> None:
            for node in (k for k in ev if k != "__interrupt__"):
                prog.events.append((node, time.time() - prog.started))

        async def go() -> None:
            try:
                async with session() as runner:
                    prog.snapshot = await work(runner, on_update)
            except BaseException as e:  # noqa: BLE001 - recorded for the page to show
                prog.error = f"{type(e).__name__}: {e}"[:500]
            finally:
                prog.done = True

        asyncio.run_coroutine_threadsafe(go(), self._loop)
        return prog

    def start(self, state_in: dict, thread_id: str, meta: dict) -> RunProgress:
        return self._submit(thread_id, lambda r, cb: r.start(state_in, thread_id, cb, meta), (state_in.get("application") or {}).get("business_label", ""))

    def resume(self, thread_id: str, value: dict) -> RunProgress:
        return self._submit(thread_id, lambda r, cb: r.resume(thread_id, value, cb))

    def continue_run(self, thread_id: str) -> RunProgress:
        return self._submit(thread_id, lambda r, cb: r.continue_run(thread_id, cb))


_manager: RunManager | None = None
_manager_lock = threading.Lock()


def manager() -> RunManager:
    """The process-wide manager (shared by every browser session of this console)."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = RunManager()
        return _manager
