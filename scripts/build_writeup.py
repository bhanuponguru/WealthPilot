"""Render the writeup (Markdown with Mermaid diagrams) to a standalone HTML file and a PDF.

Needs two tools that are not project dependencies and a browser:

    uv run --no-project --with markdown --with playwright python -m playwright install chromium     # once
    uv run --no-project --with markdown --with playwright python scripts/build_writeup.py

Output: writeup/WealthPilot-writeup.html and writeup/WealthPilot-writeup.pdf (diagrams are rendered by Mermaid in the browser,
so the machine needs internet access to fetch the pinned Mermaid script, or MERMAID_JS pointing at a local copy).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "writeup" / "WealthPilot-writeup.md"
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


def render() -> None:
    text = SRC.read_text()
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    html = re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', lambda m: f'<pre class="mermaid">{m.group(1)}</pre>', html, flags=re.S)
    doc = (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>WealthPilot</title><style>{CSS}</style></head><body>{html}"
           f"<script src='{MERMAID}'></script><script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', flowchart: {{htmlLabels: true}}}});</script></body></html>")
    out_html = ROOT / "writeup" / "WealthPilot-writeup.html"
    out_html.write_text(doc)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(out_html.as_uri())
        page.wait_for_function("() => [...document.querySelectorAll('pre.mermaid')].every(e => e.querySelector('svg') || e.dataset.processed)", timeout=60_000)
        page.pdf(path=str(ROOT / "writeup" / "WealthPilot-writeup.pdf"), format="A4", print_background=True,
                 margin={"top": "20mm", "bottom": "20mm", "left": "16mm", "right": "16mm"})
        browser.close()
    print("wrote", out_html, "and the PDF")


if __name__ == "__main__":
    render()
