"""Capture screenshots of the running console for the documentation (docs/assets/screenshots/).

Playwright is NOT a project dependency. Run it on demand, with the stack and the console already running:

    uv run --no-project --with playwright python -m playwright install chromium      # once
    uv run wealthpilot ui --headless &                                                 # console on :8501
    uv run --no-project --with playwright python scripts/capture_screenshots.py

For clean, repeatable images run the console against a SCRATCH database (copy the real one to keep the model cache, then
empty the case/audit tables), and point the script at it:

    DATABASE_URL=postgresql://wealthpilot:wealthpilot@127.0.0.1:5432/wealthpilot_demo uv run wealthpilot ui --headless --port 8502 &
    CONSOLE_URL=http://127.0.0.1:8502 uv run --no-project --with playwright python scripts/capture_screenshots.py

The script signs in as a reviewer, runs sample applicant C004 under the strict policy and records a decision, then starts C020 under the
lenient policy and leaves it waiting, so the Inbox, Cases and History pages show realistic content. Cached model replies make this fast.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

BASE = os.environ.get("CONSOLE_URL", "http://127.0.0.1:8501")
OUT = Path(__file__).resolve().parents[1] / "docs" / "assets" / "screenshots"
VIEWPORT = {"width": 1440, "height": 1000}
TALL = {"width": 1440, "height": 2600}      # Streamlit scrolls an inner container, so a tall viewport is how to capture a whole page


def settle(page: Page, seconds: float = 1.0) -> None:
    """Wait until Streamlit reports that the script run has finished (a fixed sleep is not reliable: content appears progressively)."""
    page.wait_for_selector('[data-testid="stApp"]', timeout=30_000)
    time.sleep(0.8)                                              # let the state flip to "running" after a navigation or click
    page.wait_for_selector('[data-testid="stApp"][data-test-script-state="notRunning"]', timeout=600_000)
    page.wait_for_function("document.querySelectorAll('[data-testid=\"stSkeleton\"]').length === 0", timeout=60_000)   # frontend placeholders gone
    time.sleep(seconds)


def shot(page: Page, name: str, tall: bool = True) -> None:
    """Screenshot the page; `tall` temporarily enlarges the viewport and crops to the content height."""
    OUT.mkdir(parents=True, exist_ok=True)
    if tall:
        page.set_viewport_size(TALL)
        time.sleep(1.0)
        h = page.evaluate("() => { const el = document.querySelector('[data-testid=\"stMainBlockContainer\"]'); return el ? Math.ceil(el.getBoundingClientRect().bottom) : 1000; }")
        page.screenshot(path=str(OUT / f"{name}.png"), clip={"x": 0, "y": 0, "width": TALL["width"], "height": min(max(h + 60, 700), TALL["height"])})
        page.set_viewport_size(VIEWPORT)
    else:
        page.screenshot(path=str(OUT / f"{name}.png"))
    print("saved", name)


def goto(page: Page, path: str) -> None:
    page.goto(f"{BASE}/{path}")
    settle(page)


def set_profile(page: Page, name: str, tier: str) -> None:
    """Fill the sidebar's 'Signed in as' block (the decision form is pre-filled from it)."""
    page.get_by_role("textbox", name="Your name or id").fill(name)
    page.keyboard.press("Enter")
    settle(page, 1.0)
    page.get_by_role("combobox", name="Your authority").click()
    page.keyboard.type(tier)
    page.keyboard.press("Enter")
    settle(page, 1.0)


def run_sample(page: Page, case_id: str, policy: str) -> bool:
    """On New case -> Try a sample applicant: pick an applicant and policy, run it, and wait for the decision form."""
    page.get_by_role("tab", name="Try a sample applicant").click()
    time.sleep(1.0)
    page.get_by_role("combobox", name="Applicant").click()
    page.keyboard.type(case_id)
    page.keyboard.press("Enter")
    settle(page, 1.5)
    if policy != "strict":
        page.get_by_text(policy, exact=True).last.click()
        settle(page, 1.0)
    page.get_by_role("button", name="Run underwriting").last.click()
    try:
        page.get_by_role("heading", name="Your decision").first.wait_for(timeout=600_000)
    except PWTimeout:
        print(f"{case_id} did not reach the decision form in time", file=sys.stderr)
        return False
    settle(page, 2)
    return True


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport=VIEWPORT)

        goto(page, "")
        shot(page, "inbox-empty")
        goto(page, "new-case")
        shot(page, "new-case-application")
        page.get_by_role("tab", name="Try a sample applicant").click()
        time.sleep(1.5)
        shot(page, "new-case-sample")
        set_profile(page, "j.rivera", "Senior Credit Officer")

        # case 1: C004 under the strict policy -> review screens -> record the decision
        if not run_sample(page, "C004", "strict"):
            return 1
        shot(page, "case-review-memo")
        for tab, name in (("Policy checklist", "case-policy-checklist"), ("Financials", "case-financials"), ("Risk", "case-risk"),
                          ("Research", "case-research"), ("Timeline", "case-timeline")):
            page.get_by_role("tab", name=tab).first.click()
            time.sleep(1.2)
            shot(page, name)
        page.get_by_role("tab", name="Memo").first.click()
        page.get_by_role("heading", name="Your decision").first.scroll_into_view_if_needed()
        time.sleep(0.8)
        page.get_by_role("textbox", name="Reason / comments").fill("Loan-to-revenue above the policy maximum (CP-6).")
        shot(page, "case-decision-form", tall=False)
        page.get_by_role("button", name="Submit decision").click()
        page.get_by_text("Decision recorded").first.wait_for(timeout=120_000)
        settle(page, 2)
        shot(page, "case-decided")

        # case 2: C020 under the lenient policy, left waiting for a human
        goto(page, "new-case")
        if not run_sample(page, "C020", "lenient"):
            return 1

        for path, name in (("", "inbox"), ("cases", "cases"), ("history", "history"), ("policies", "policies"),
                           ("experiments", "experiments"), ("system", "system")):
            goto(page, path)
            shot(page, name)
        goto(page, "cases")                                        # the case view reached from the list
        page.get_by_role("tab", name="All").click() if page.get_by_role("tab", name="All").count() else page.get_by_text("All", exact=True).first.click()
        settle(page, 1.0)
        shot(page, "cases-all")
        goto(page, "policies")
        page.get_by_role("tab", name="Compare policies").click()
        time.sleep(1.5)
        shot(page, "policies-compare")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
