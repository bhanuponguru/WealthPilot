"""End-to-end check in a real browser: a run keeps going when the user leaves the page that started it.

Needs the stack and a console running (see scripts/capture_screenshots.py for the scratch-database recipe):

    CONSOLE_URL=http://127.0.0.1:8502 uv run --no-project --with playwright python scripts/check_run_survives_navigation.py [CASE_ID] [VARIANT]

Starts the sample applicant (default C012, noisy documents, so the first run is not served from the cache), leaves for the Cases page
as soon as the run starts, then polls the Inbox until the case shows up under "Needs your decision" without ever returning to New case.
"""

from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = os.environ.get("CONSOLE_URL", "http://127.0.0.1:8501")


def settle(page, extra: float = 0.8) -> None:
    page.wait_for_selector('[data-testid="stApp"][data-test-script-state="notRunning"]', timeout=120_000)
    time.sleep(extra)


def main() -> int:
    case = sys.argv[1] if len(sys.argv) > 1 else "C012"
    variant = sys.argv[2] if len(sys.argv) > 2 else "noisy"
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 1000})
        page.goto(f"{BASE}/new-case")
        settle(page, 1.5)
        page.get_by_role("tab", name="Try a sample applicant").click()
        time.sleep(1)
        page.get_by_role("combobox", name="Applicant").click()
        page.keyboard.type(case)
        page.keyboard.press("Enter")
        settle(page, 1.5)
        if variant != "clean":
            page.get_by_text("Advanced options").last.click()
            page.get_by_text(variant, exact=True).first.click()
            settle(page, 1.0)
        page.get_by_role("button", name="Run underwriting").last.click()
        page.get_by_text("steps").first.wait_for(timeout=60_000)          # the live progress bar is showing
        print("run started; leaving the page")
        page.get_by_role("link", name="Cases").click()
        settle(page, 1.0)
        t0 = time.time()
        while time.time() - t0 < 900:
            page.get_by_role("link", name="Inbox").click()
            settle(page, 1.5)
            if page.get_by_text("Needs your decision (1)").count():
                print(f"case reached the inbox after {time.time() - t0:.0f}s without returning to the New case page")
                return 0
            if page.get_by_text("Stopped with an error").count():
                print("FAIL: the run stopped with an error", file=sys.stderr)
                return 1
            time.sleep(10)
        print("FAIL: timed out waiting for the case to reach the inbox", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
