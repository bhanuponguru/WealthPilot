"""Client side of the MCP integration: connections, tool loading, and a helper to call tools from code."""

from __future__ import annotations

import json

from langchain_mcp_adapters.client import MultiServerMCPClient

from .config import MCP_HOST, MCP_PORTS

SERVERS = MCP_PORTS
CONNECTIONS = {name: {"transport": "streamable_http", "url": f"http://{MCP_HOST}:{port}/mcp"} for name, port in SERVERS.items()}


def make_client(servers: list[str] | None = None) -> MultiServerMCPClient:
    names = servers or list(SERVERS)
    return MultiServerMCPClient({n: CONNECTIONS[n] for n in names})


async def load_tools(servers: list[str] | None = None) -> dict:
    """Return {tool_name: langchain tool}. Raises if a server is unreachable (caller decides how to degrade)."""
    client = make_client(servers)
    return {t.name: t for t in await client.get_tools()}


def parse_result(res):
    """MCP tool results arrive as text blocks (or a string). Parse the JSON payload back into Python."""
    if isinstance(res, tuple):  # (content, artifact)
        return parse_result(res[0])
    if isinstance(res, list):  # content blocks; a multi-item list result arrives as one block per item
        parsed = [parse_result(b.get("text", "") if isinstance(b, dict) else str(b)) for b in res]
        return parsed[0] if len(parsed) == 1 else parsed
    if isinstance(res, str):
        try:
            return json.loads(res)
        except json.JSONDecodeError:
            return res
    return res


async def call(tools: dict, tool_name: str, /, **args):
    """Call an MCP tool by name. Positional-only so tool arguments named `name` etc. never collide."""
    return parse_result(await tools[tool_name].ainvoke(args))
