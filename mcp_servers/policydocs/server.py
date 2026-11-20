"""policydocs MCP server: policy RAG (hybrid search + rerank), rule lookup, and similar-case precedents."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from wealthpilot.config import MCP_BIND
from wealthpilot.memory import precedents
from wealthpilot.rag import index

PORT = 8102
mcp = FastMCP("policydocs", host=MCP_BIND, port=PORT)


@mcp.tool()
def list_rules(policy_id: str) -> dict:
    """List the numbered rules in a credit policy as {'rules': [{rule_id, title}]}. Start here to discover what must be checked."""
    return {"rules": index.list_rules(policy_id)}


@mcp.tool()
def search_policy(query: str, policy_id: str, k: int = 4) -> dict:
    """Search the policy text (hybrid BM25 + vector, then rerank). Returns the best passages with their rule ids.
    Read the passage text carefully: thresholds and exceptions are stated there."""
    return index.search(query, policy_id, strategy="structure", mode="hybrid", use_rerank=True, k=k)


@mcp.tool()
def get_rule(policy_id: str, rule_id: str) -> dict:
    """Return the full text of one rule section, e.g. rule_id='CP-3'."""
    return index.get_rule(policy_id, rule_id) or {"error": f"unknown rule {rule_id} in policy {policy_id}"}


@mcp.tool()
def similar_precedents(summary: str, k: int = 3) -> dict:
    """Past decided cases most similar to this one (semantic memory), as {'precedents': [...]}.
    Informational only, never a basis for a decision."""
    return {"precedents": precedents.search(summary, k)}


if __name__ == "__main__":
    index.ensure_indexed()
    mcp.run(transport="streamable-http")
