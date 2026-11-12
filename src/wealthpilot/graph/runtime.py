"""Runtime resources for the graph: MCP tools with retry + per-server circuit breaker, shared LLMs."""

from __future__ import annotations

import asyncio
import time

from ..mcp_client import SERVERS, load_tools, parse_result
from ..nim import chaos, get_chat
from ..nim.gateway import is_retryable

TOOL_SERVER = {
    **dict.fromkeys(["compute_ratios", "amortize", "trend", "stress_test", "compare", "scorecard", "grade", "score_pd"], "fincalc"),
    **dict.fromkeys(["list_rules", "search_policy", "get_rule", "similar_precedents"], "policydocs"),
    **dict.fromkeys(["ofac_screen", "adverse_media", "registry_lookup", "industry_default_stats"], "research"),
}


class ToolUnavailable(Exception):
    def __init__(self, server: str, tool: str, err: str):
        super().__init__(f"{server}.{tool} unavailable: {err}")
        self.server, self.tool = server, tool


class AsyncBreaker:
    """closed -> (fail_max consecutive failures) -> open for reset_timeout s -> half-open (one trial) -> closed/open."""

    def __init__(self, fail_max: int = 3, reset_timeout: float = 20.0):
        self.fail_max, self.reset_timeout = fail_max, reset_timeout
        self.failures, self.opened_at = 0, None

    @property
    def is_open(self) -> bool:
        return self.opened_at is not None and time.monotonic() - self.opened_at < self.reset_timeout

    def success(self) -> None:
        self.failures, self.opened_at = 0, None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_max:
            self.opened_at = time.monotonic()


class Runtime:
    def __init__(self):
        self.tools: dict = {}
        self.unavailable: set[str] = set()
        self.breakers = {s: AsyncBreaker() for s in SERVERS}
        self._llm = None
        self.store = None  # LangGraph long-term memory store, set by builder.session()

    async def connect(self) -> None:
        """Load tools server by server so one dead server does not prevent the others (degraded mode)."""
        self.tools, self.unavailable = {}, set()
        self.breakers = {s: AsyncBreaker() for s in SERVERS}
        for s in SERVERS:
            try:
                self.tools.update(await load_tools([s]))
            except Exception:  # noqa: BLE001
                self.unavailable.add(s)

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_chat(max_tokens=3000)
        return self._llm

    @staticmethod
    def _injected_outage(server: str) -> bool:
        return server in chaos.current().get("down_servers", [])

    def agent_tools(self, names: list[str]) -> list:
        for n in names:
            if self._injected_outage(TOOL_SERVER[n]):
                raise ToolUnavailable(TOOL_SERVER[n], n, "injected outage")
        missing = [n for n in names if n not in self.tools]
        if missing:
            raise ToolUnavailable(TOOL_SERVER.get(missing[0], "?"), missing[0], "not loaded")
        for n in names:
            if self.breakers[TOOL_SERVER[n]].is_open:
                raise ToolUnavailable(TOOL_SERVER[n], n, "circuit open")
        return [self.tools[n] for n in names]

    async def call(self, tool: str, /, **args):
        """Call an MCP tool: 3 attempts with backoff, behind the server's circuit breaker. Raises ToolUnavailable."""
        server = TOOL_SERVER[tool]
        if self._injected_outage(server):
            raise ToolUnavailable(server, tool, "injected outage")
        if tool not in self.tools:
            raise ToolUnavailable(server, tool, "server was not reachable at startup")
        br = self.breakers[server]
        if br.is_open:
            raise ToolUnavailable(server, tool, "circuit open")
        last: Exception | None = None
        for i in range(3):
            try:
                chaos.inject("mcp")
                out = parse_result(await self.tools[tool].ainvoke(args))
                br.success()
                return out
            except Exception as e:  # noqa: BLE001
                last = e
                retryable = is_retryable(e) or any(w in str(e).lower() for w in ("connect", "closed", "refused", "unavailable"))
                if i < 2 and retryable:
                    await asyncio.sleep(0.5 * (i + 1))
                    continue
                break
        br.failure()
        raise ToolUnavailable(server, tool, f"{type(last).__name__}: {str(last)[:120]}")


rt = Runtime()
