"""The product must never depend on the research package, and must not ship the hidden answer keys."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIRS = [ROOT / "src" / "wealthpilot", ROOT / "mcp_servers"]


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def test_product_code_does_not_import_the_research_package():
    offenders = [f"{p.relative_to(ROOT)}: {m}" for d in PRODUCT_DIRS for p in d.rglob("*.py") for m in _imports(p) if m.split(".")[0] == "wealthpilot_lab"]
    assert not offenders, offenders


def test_policy_folders_hold_only_policy_text():
    for d in (ROOT / "policies").iterdir():
        assert {f.name for f in d.iterdir()} == {"policy.md"}, f"{d.name} contains more than the policy text (answer keys belong to the research package)"


def test_console_has_no_research_pages():
    from wealthpilot.ui import nav
    titles = [p.title for specs in nav.SECTIONS.values() for p in specs]
    assert titles == ["Inbox", "New case", "Cases", "History", "Credit policies", "System"]
