"""Render a Markdown document with Mermaid diagrams to a PDF (default: the project writeup).

Needs two tools that are not project dependencies and a browser:

    uv run --no-project --with markdown --with playwright python -m playwright install chromium     # once
    uv run --no-project --with markdown --with playwright python scripts/build_writeup.py            # the writeup
    uv run --no-project --with markdown --with playwright python scripts/build_writeup.py docs/Project_Report.md docs/Project_Report.pdf --compact

Default output: writeup/WealthPilot-writeup.html and writeup/WealthPilot-writeup.pdf. For any other source the intermediate HTML is
written to a temporary folder. Diagrams are rendered by Mermaid in the browser, so the machine needs internet access to fetch the
pinned Mermaid script, or MERMAID_JS pointing at a local copy.

Relative links in the source are rewritten to absolute repository URLs at the release tag (RELEASE_TAG, default cs5903-final-2026),
resolved against the folder of the source file. A link whose target does not exist stops the build.
"""

from __future__ import annotations

import argparse
import os
import posixpath
import re
import sys
import tempfile
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "writeup" / "WealthPilot-writeup.md"
REPO_URL = "https://github.com/bhanuponguru/WealthPilot"
TAG = os.environ.get("RELEASE_TAG", "cs5903-final-2026")
MERMAID = os.environ.get("MERMAID_JS", "https://cdn.jsdelivr.net/npm/mermaid@11.4.0/dist/mermaid.min.js")

CSS = """
@page { size: A4; margin: 22mm 18mm; }
body { font-family: 'Georgia', 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.5; color: #1d2433; max-width: 175mm; margin: 0 auto; }
h1 { font-size: 24pt; margin: 0 0 4pt; color: #1b2a5a; }
h2 { font-size: 15pt; margin-top: 22pt; border-bottom: 1px solid #c9cfe3; padding-bottom: 3pt; color: #1b2a5a; page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 14pt; color: #2b3a73; page-break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; width: 100%; margin: 10pt 0; font-size: 9pt; page-break-inside: avoid; }
th { background: #eef0f8; text-align: left; }
th, td { border: 1px solid #c9cfe3; padding: 4pt 6pt; vertical-align: top; }
code { font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; background: #f3f4f8; padding: 0 2pt; }
pre.mermaid { text-align: center; background: #fff; margin: 12pt 0; page-break-inside: avoid; }
pre.mermaid svg { width: auto !important; height: auto !important; max-width: 100% !important; max-height: 215mm !important; }
blockquote { border-left: 3px solid #b5bddb; margin-left: 0; padding-left: 10pt; color: #3d4663; }
"""


COMPACT_CSS = """
body { font-size: 9.4pt; line-height: 1.4; max-width: none; }
h1 { font-size: 20pt; } h2 { font-size: 13pt; margin-top: 14pt; } h3 { font-size: 10.5pt; margin-top: 9pt; }
table { font-size: 8pt; margin: 6pt 0; page-break-inside: auto; } tr { page-break-inside: avoid; }
th, td { padding: 2.5pt 4pt; } p { margin: 4pt 0; } pre.mermaid svg { max-height: 120mm !important; }
"""


def absolutize(html: str, src: Path) -> str:
    """Rewrite relative links to repository URLs at the release tag; fail on a missing target."""
    base = src.resolve().parent.relative_to(ROOT).as_posix()
    missing: list[str] = []

    def fix(m: re.Match) -> str:
        target = m.group(1)
        if re.match(r"^(https?:|mailto:|#)", target):
            return m.group(0)
        path, _, frag = target.partition("#")
        rel = posixpath.normpath(posixpath.join(base, path))
        full = ROOT / rel
        if not full.exists():
            missing.append(target)
            return m.group(0)
        kind = "tree" if full.is_dir() else "blob"
        return f'href="{REPO_URL}/{kind}/{TAG}/{rel}' + (f"#{frag}" if frag else "") + '"'

    html = re.sub(r'href="([^"]+)"', fix, html)
    if missing:
        sys.exit("broken relative links: " + ", ".join(sorted(set(missing))))
    return html


def render(src: Path = SRC, out_pdf: Path | None = None, compact: bool = False) -> None:
    default = src == SRC
    out_pdf = out_pdf or src.with_suffix(".pdf")
    text = src.read_text()
    title = (re.search(r"^# (.+)$", text, re.MULTILINE) or [None, "WealthPilot"])[1]
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    html = absolutize(html, src)
    html = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', html, flags=re.DOTALL)
    css = CSS + (COMPACT_CSS if compact else "")
    doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{title}</title><style>{css}</style></head><body>{html}"
           f"<script src='{MERMAID}'></script><script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', flowchart: {{htmlLabels: true}}}});</script></body></html>")
    out_html = (ROOT / "writeup" / "WealthPilot-writeup.html") if default else Path(tempfile.mkdtemp()) / "document.html"
    out_html.write_text(doc)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(out_html.as_uri())
        page.wait_for_function("() => [...document.querySelectorAll('pre.mermaid')].every(e => e.querySelector('svg') || e.dataset.processed)", timeout=60_000)
        footer = ("<div style='width:100%;font-size:8px;color:#667;text-align:center;font-family:sans-serif'>"
                  "<span class='pageNumber'></span> / <span class='totalPages'></span></div>")
        page.pdf(path=str(out_pdf), format="A4", print_background=True, display_header_footer=True,
                 header_template="<span></span>", footer_template=footer,
                 margin={"top": "18mm", "bottom": "18mm", "left": "15mm", "right": "15mm"} if compact
                 else {"top": "20mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
        browser.close()
    print("wrote", out_pdf)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("source", nargs="?", default=str(SRC))
    ap.add_argument("pdf", nargs="?")
    ap.add_argument("--compact", action="store_true", help="smaller type, for page-limited documents")
    a = ap.parse_args()
    render(Path(a.source).resolve(), Path(a.pdf).resolve() if a.pdf else None, a.compact)
