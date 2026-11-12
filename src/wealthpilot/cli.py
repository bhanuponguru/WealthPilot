"""WealthPilot CLI.  `uv run wealthpilot --help`"""

from __future__ import annotations

import asyncio
import json

import typer

app = typer.Typer(help="WealthPilot: SME loan underwriting assistant", no_args_is_help=True)


def _print_snapshot(snap: dict) -> None:
    v = snap["values"]
    typer.echo(f"recommendation: {v.get('recommendation')}   required approver: {v.get('required_tier')}   grade: {(v.get('grade') or {}).get('grade')}")
    if v.get("degraded"):
        typer.secho(f"DEGRADED: {v.get('degraded_reasons')}", fg="yellow")
    for c in v.get("policy_checks", []):
        typer.echo(f"  {c['rule_id']:<6} {c['status']:<15} {c.get('reason', '')[:90]}")
    if snap["interrupt"]:
        typer.secho(f"\nWaiting for human input ({snap['interrupt'].get('type')}). Resume with `wealthpilot approve {v['case_id']} ...`", fg="cyan")
    elif snap["done"]:
        typer.secho(f"\nFINAL: {json.dumps(v.get('final'), indent=1)}", fg="green")


@app.command()
def run(case_id: str, policy: str = "strict", variant: str = "clean", redaction: bool = True, thread: str = typer.Option(None, help="thread id (default: case id)")):
    """Run one synthetic case through the graph until it needs a human."""
    from .graph.builder import make_input, session
    from .synth.applicants import load

    rec = next(a for a in load() if a["case_id"] == case_id)

    async def go():
        async with session() as runner:
            snap = await runner.start(make_input(rec, policy, variant, redaction), thread or case_id,
                                      on_update=lambda ev: typer.echo("  ✓ " + ", ".join(k for k in ev if k != "__interrupt__")))
            _print_snapshot(snap)
    asyncio.run(go())


@app.command()
def approve(thread: str, decision: str = typer.Option(..., help="approve | decline | revise"), tier: str = typer.Option(..., help="Analyst | Senior Credit Officer | Credit Committee"),
            approver: str = "cli-user", reason: str = ""):
    """Resume a paused case with a human decision."""
    from .graph.builder import session

    async def go():
        async with session() as runner:
            snap = await runner.resume(thread, {"decision": decision, "approver_tier": tier, "approver_id": approver, "reason": reason})
            _print_snapshot(snap)
    asyncio.run(go())


@app.command()
def show(thread: str):
    """Show the current state of a case thread."""
    from .graph.builder import session

    async def go():
        async with session() as runner:
            _print_snapshot(await runner.snapshot(thread))
    asyncio.run(go())


@app.command("ingest-policy")
def ingest_policy():
    """(Re)build the policy RAG indexes (structure + fixed chunking, both policies)."""
    from .rag import index
    for pid in ("strict", "lenient"):
        for st in index.STRATEGIES:
            typer.echo(f"{pid}/{st}: {index.ingest(pid, st)} chunks")


@app.command("train-pd")
def train_pd():
    """Train the SBA probability-of-default model and register it in MLflow."""
    from .risk import pd_model
    typer.echo(json.dumps(pd_model.train(), indent=2))


@app.command("audit-verify")
def audit_verify():
    """Verify the hash-chained audit log."""
    from .compliance import audit
    res = audit.verify()
    typer.secho(json.dumps(res), fg="green" if res["ok"] else "red")
    raise typer.Exit(0 if res["ok"] else 1)


@app.command("mcp-up")
def mcp_up():
    """Start the three MCP servers (fincalc 8101, policydocs 8102, research 8103)."""
    from . import mcp_up as m
    m.main()


if __name__ == "__main__":
    app()
