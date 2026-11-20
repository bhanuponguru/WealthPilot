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


@app.command("demo-run")
def demo_run(case_id: str, policy: str = "strict", variant: str = "clean", redaction: bool = True, thread: str = typer.Option(None, help="thread id (default: case id)")):
    """Run one sample applicant (demonstration data) through the workflow until it needs a human."""
    from . import demo
    from .graph.builder import session

    rec = next((a for a in demo.applicants() if a["case_id"] == case_id), None)
    if rec is None:
        typer.secho("No such sample applicant. Demonstration data is needed (see the documentation).", fg="red")
        raise typer.Exit(1)

    async def go():
        async with session() as runner:
            snap = await runner.start(demo.make_input(rec, policy, variant, redaction), thread or case_id,
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
    """(Re)build the policy search indexes for every credit policy."""
    from .config import POLICIES_DIR
    from .rag import index
    for pid in sorted(p.name for p in POLICIES_DIR.iterdir() if (p / "policy.md").exists()):
        for st in index.STRATEGIES:
            typer.echo(f"{pid}/{st}: {index.ingest(pid, st)} chunks")


@app.command()
def bootstrap():
    """Prepare a fresh deployment: create data folders and fetch the sanctions list."""
    from . import bootstrap as b
    raise typer.Exit(b.main())


@app.command("fetch-ofac")
def fetch_ofac(force: bool = typer.Option(False, help="download again even if the list is already present")):
    """Download the OFAC SDN sanctions list used for screening."""
    from .bootstrap import fetch_ofac as fetch
    path = fetch(force=force)
    typer.echo(f"sanctions list: {path} ({path.stat().st_size // 1024} KB)")


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


@app.command()
def ui(port: int = typer.Option(8501, help="port to serve on"), host: str = typer.Option("127.0.0.1", help="address to bind (keep 127.0.0.1: there is no login)"),
       headless: bool = typer.Option(False, help="do not open a browser tab")):
    """Launch the Streamlit console (needs Postgres, Ollama, the MCP servers and a NIM key; see `wealthpilot doctor`)."""
    import subprocess
    import sys
    from pathlib import Path

    app_path = Path(__file__).parent / "ui" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port), "--server.address", host,
           "--browser.gatherUsageStats", "false", "--server.maxUploadSize", "25", *(["--server.headless", "true"] if headless else [])]
    typer.echo(f"Console: http://{host}:{port}")
    raise typer.Exit(subprocess.call(cmd))


@app.command()
def doctor():
    """Check that every service and data artifact is ready, and print the command that fixes anything missing."""
    from . import health

    checks = health.run_all()
    for c in checks:
        mark = "✓" if c.ok else ("!" if not c.required else "✗")
        typer.secho(f" {mark} {c.name:<24} {c.detail}", fg="green" if c.ok else ("yellow" if not c.required else "red"))
        if not c.ok and c.fix:
            typer.echo(f"     fix: {c.fix}")
    bad = health.blocking(checks)
    typer.secho("\nReady to underwrite." if not bad else f"\nNot ready: {', '.join(c.name for c in bad)}.", fg="green" if not bad else "red")
    raise typer.Exit(0 if not bad else 1)


@app.command("mcp-up")
def mcp_up():
    """Start the three MCP servers (fincalc 8101, policydocs 8102, research 8103)."""
    from . import mcp_up as m
    m.main()


if __name__ == "__main__":
    app()
