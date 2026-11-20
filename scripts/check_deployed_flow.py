"""End-to-end check of a running deployment, as a user would do it: upload two PDFs, wait for the case, record a decision.

    CONSOLE_URL=http://127.0.0.1:8501 uv run --no-project --with playwright python scripts/check_deployed_flow.py <financials.pdf> <bank_statement.pdf>

Checks, in a real browser: the New case page offers only the real application form (no sample-applicant tab), an uploaded application runs to
the decision gate, a decision can be recorded with the reviewer profile, and the decision appears in History with an intact audit chain.
Exit status 0 on success.
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


def pick(page, label: str, value: str) -> None:
    page.get_by_role("combobox", name=label).click()
    page.keyboard.type(value)
    page.keyboard.press("Enter")
    settle(page, 0.6)


def main() -> int:
    fin, bank = sys.argv[1], sys.argv[2]
    with sync_playwright() as p:
        page = p.chromium.launch().new_page(viewport={"width": 1440, "height": 1100})
        page.goto(f"{BASE}/new-case")
        settle(page, 1.5)
        assert page.get_by_role("tab", name="Try a sample applicant").count() == 0, "demonstration mode is unexpectedly on"

        page.get_by_role("textbox", name="Your name or id").fill("j.rivera")
        page.keyboard.press("Enter")
        settle(page, 0.8)
        pick(page, "Your authority", "Senior Credit Officer")

        page.get_by_role("textbox", name="Business name", exact=True).fill("Ibarra Restaurant Co.")
        page.get_by_role("textbox", name="Principal owner (first and last name)", exact=True).fill("Hector Ibarra")
        page.get_by_role("textbox", name="Street", exact=True).fill("180 Congress St")
        page.get_by_role("textbox", name="City", exact=True).fill("Tucson")
        page.get_by_role("textbox", name="ZIP", exact=True).fill("85701")
        pick(page, "State", "AZ")
        pick(page, "Legal form", "PARTNERSHIP")
        page.get_by_role("spinbutton", name="Years in business").fill("15")
        page.get_by_role("spinbutton", name="Jobs supported").fill("15")
        page.get_by_role("spinbutton", name="Loan amount ($)").fill("100000")
        page.get_by_role("spinbutton", name="Term (months)").fill("84")
        pick(page, "Purpose", "equipment purchase")
        page.get_by_role("spinbutton", name="Collateral value ($)").fill("160000")
        pick(page, "Rate type", "Fixed")
        page.get_by_text("Personal guarantee provided").click()
        page.locator('input[type="file"]').nth(0).set_input_files(fin)
        page.locator('input[type="file"]').nth(1).set_input_files(bank)
        settle(page, 1.5)
        page.get_by_role("button", name="Run underwriting").click()
        page.get_by_text("steps").first.wait_for(timeout=60_000)
        print("run started")

        page.get_by_role("heading", name="Your decision").first.wait_for(timeout=1_200_000)
        print("decision gate reached")
        page.get_by_role("textbox", name="Reason / comments").fill("Recorded by the deployment check.")
        page.get_by_role("button", name="Submit decision").click()
        page.get_by_text("Decision recorded").first.wait_for(timeout=180_000)
        print("decision recorded")

        page.goto(f"{BASE}/history")
        settle(page, 1.5)
        assert page.get_by_text("Audit chain intact").count(), "audit chain banner missing"
        assert page.get_by_text("j.rivera").count(), "decision not listed in History"
        print("history shows the decision; audit chain intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
