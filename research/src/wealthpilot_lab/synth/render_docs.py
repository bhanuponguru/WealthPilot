"""Render applicant ground truth into PDFs: clean, noisy-layout, scanned (image-only)."""

from __future__ import annotations

import io
import random
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from wealthpilot.parsing.fields import ALL_FIELDS, BS_FIELDS, IS_FIELDS, LABELS  # noqa: F401

from .applicants import OUT_DIR, load

DOCS_DIR = OUT_DIR / "docs"



def _money(v: int, style: str) -> str:
    if style == "paren" and v < 0:
        return f"({abs(v):,})"
    if style == "dollar":
        return f"-${abs(v):,}" if v < 0 else f"${v:,}"
    return f"{v:,}"


def _draw_statement(c: canvas.Canvas, a: dict, title: str, fields: list[str], noisy: bool, rng: random.Random, years: list[str]) -> None:
    w, h = letter
    font = rng.choice(["Helvetica", "Times-Roman", "Courier"]) if noisy else "Helvetica"
    c.setFont(font + ("-Bold" if font == "Helvetica" else ""), 13)
    y = h - 60
    c.drawString(60, y, a["business_name"])
    c.setFont(font, 9)
    addr = a["address"]
    c.drawString(60, y - 14, f"{addr['street']}, {addr['city']}, {addr['state']} {addr['zip']}")
    c.setFont(font + ("-Bold" if font == "Helvetica" else ""), 12)
    c.drawString(60, y - 42, title)
    c.setFont(font, 9)
    if noisy:
        c.drawString(60, y - 56, rng.choice([f"Prepared by owner {a['owner_name']} - unaudited", "Management accounts - unaudited",
                                             f"Compiled for {a['owner_name']}, sole signatory"]))
    ys = list(reversed(years)) if (noisy and rng.random() < 0.5) else years
    xcols = [330 + 85 * i for i in range(len(ys))]
    c.setFont(font + ("-Bold" if font == "Helvetica" else ""), 10)
    for x, fy in zip(xcols, ys):
        c.drawRightString(x + 50, y - 80, f"FY{fy}" if not noisy or rng.random() < 0.5 else f"Year ended Dec 31, {fy}")
    c.setFont(font, 10)
    style = rng.choice(["plain", "paren", "dollar"]) if noisy else "plain"
    yy = y - 104
    for fld in fields:
        clean, syn = LABELS[fld]
        label = rng.choice([clean] + syn) if noisy else clean
        bold = fld.startswith("total_") or fld == "net_income"
        c.setFont(font + ("-Bold" if bold and font == "Helvetica" else ""), 10)
        c.drawString(60, yy, label)
        for x, fy in zip(xcols, ys):
            v = a["statements"][fy][fld]
            c.drawRightString(x + 50, yy, _money(v, style))
        yy -= 20
    if noisy:
        c.setFont(font, 8)
        c.drawString(60, 50, rng.choice(["See accompanying notes. Figures in US dollars.", "All amounts in USD. Subject to year-end adjustments.", "Unaudited - for lending purposes only."]))
    c.showPage()


def render_financials(a: dict, path: Path, noisy: bool, seed: int) -> None:
    rng = random.Random(seed)
    years = sorted(a["statements"])
    c = canvas.Canvas(str(path), pagesize=letter)
    pages = [("Income Statement", IS_FIELDS), ("Balance Sheet", BS_FIELDS)]
    if noisy and rng.random() < 0.5:
        pages.reverse()
    for title, fields in pages:
        _draw_statement(c, a, title if not noisy else rng.choice([title, title.replace("Income Statement", "Profit and Loss"), title.replace("Balance Sheet", "Statement of Financial Position")]),
                        fields, noisy, rng, years)
    c.save()


def render_bank(a: dict, path: Path, noisy: bool, seed: int) -> None:
    random.Random(seed + 1)
    bank = a["bank"]
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    font = "Courier" if noisy else "Helvetica"
    c.setFont(font + ("" if noisy else "-Bold"), 14)
    c.drawString(60, h - 60, bank["bank_name"])
    c.setFont(font, 10)
    c.drawString(60, h - 80, f"Business checking - account holder: {a['business_name']}")
    c.drawString(60, h - 94, f"Authorised signatory: {a['owner_name']}")
    ad = a["address"]
    c.drawString(60, h - 108, f"{ad['street']}, {ad['city']}, {ad['state']} {ad['zip']}")
    c.drawString(60, h - 122, "Statement period: 2024-01-01 to 2024-12-31 (monthly summary)")
    cols = [60, 140, 260, 360, 460]
    c.setFont(font + ("" if noisy else "-Bold"), 10)
    for x, t in zip(cols, ["Month", "Opening", "Deposits", "Withdrawals", "Closing"]):
        c.drawString(x, h - 150, t)
    c.setFont(font, 10)
    yy = h - 170
    for m in bank["months"]:
        for x, t in zip(cols, [m["month"], f"{m['opening']:,}", f"{m['deposits']:,}", f"{m['withdrawals']:,}", f"{m['closing']:,}"]):
            c.drawString(x, yy, t)
        yy -= 16
        for n in m["notes"]:
            c.setFont(font, 8)
            c.drawString(80, yy, f"  memo: {n}")
            c.setFont(font, 10)
            yy -= 13
    c.save()


def scanify(pdf_path: Path, out_path: Path, seed: int, dpi: int = 110) -> None:
    """Rasterise a PDF, add scanner noise/skew, write an image-only PDF."""
    rng = np.random.default_rng(seed)
    src = pymupdf.open(pdf_path)
    out = pymupdf.open()
    for page in src:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        img = img.rotate(float(rng.uniform(-1.2, 1.2)), resample=Image.BICUBIC, fillcolor=255)
        arr = np.asarray(img, dtype=np.float32)
        arr = arr * rng.uniform(0.88, 0.97) + rng.normal(0, 7, arr.shape)
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        newp = out.new_page(width=page.rect.width, height=page.rect.height)
        newp.insert_image(newp.rect, stream=buf.getvalue())
    out.save(out_path)


def render_case(a: dict, variant: str, out_root: Path = DOCS_DIR, seed: int = 0) -> Path:
    assert variant in ("clean", "noisy", "scanned")
    d = out_root / a["case_id"] / variant
    d.mkdir(parents=True, exist_ok=True)
    s = (seed or int(a["case_id"][1:])) * 17
    fin, bank = d / "financials.pdf", d / "bank_statement.pdf"
    render_financials(a, fin, noisy=variant == "noisy", seed=s)
    render_bank(a, bank, noisy=variant == "noisy", seed=s)
    if variant == "scanned":
        # scanned = noisy-layout content, rasterised
        tmp_f, tmp_b = d / "_f.pdf", d / "_b.pdf"
        render_financials(a, tmp_f, noisy=True, seed=s)
        render_bank(a, tmp_b, noisy=True, seed=s)
        scanify(tmp_f, fin, s)
        scanify(tmp_b, bank, s + 1)
        tmp_f.unlink()
        tmp_b.unlink()
    return d


def render_all(variants=("clean", "noisy", "scanned")) -> int:
    n = 0
    for a in load():
        for v in variants:
            render_case(a, v)
            n += 1
    return n


if __name__ == "__main__":
    print("rendered", render_all(), "document sets ->", DOCS_DIR)
