"""Focused real-browser regression. Requires a running preview and Playwright.

Run with PLAYWRIGHT_NODEJS_PATH=$(which node) python tests/browser_request_reupload.py.
Only synthetic data is uploaded; no destination writes are performed.
"""
import os
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})

        def settle():
            page.wait_for_timeout(650)
            page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden", timeout=60000)

        def click(label):
            page.get_by_role("button", name=label, exact=True).click()
            settle()

        def submit_file():
            page.locator('input[type="file"]').set_input_files({
                "name": "repeat.csv", "mimeType": "text/csv",
                "buffer": b"name,amount\nAda,1\nBob,2\n",
            })
            settle()
            page.get_by_role("tab", name="3 · Review & fix", exact=True).click()
            settle()
            page.get_by_text("Ready to submit this version to the demo approver", exact=True).click()
            settle()
            click("Submit for review")
            return page.get_by_role("heading", level=2).first.inner_text()

        def assert_empty():
            assert page.locator('input[type="file"]').evaluate("(el) => el.files.length") == 0
            assert page.get_by_role("tab", name="3 · Review & fix", exact=True).count() == 0
            assert page.get_by_test_id("stException").count() == 0

        page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
        settle()
        click("Login")
        click("Continue without signing in")
        first = submit_file()
        click("New request")
        assert_empty()
        # Keep an empty draft, then deliberately leave another file selected.
        click("Request list")
        draft_row = page.locator('[class*="st-key-rd_record_"]').filter(has_text="Draft")
        assert draft_row.count() == 1
        empty_reference = draft_row.locator(".request-register-reference").inner_text()
        page.locator(".st-key-nav_new_request button").click()
        settle()
        third = submit_file()
        assert first != third
        click("Request list")
        empty_row = page.locator('[class*="st-key-rd_record_"]').filter(has_text=empty_reference)
        empty_row.get_by_role("button", name="View", exact=True).click()
        settle()
        click("Continue draft")
        assert_empty()
        reopened = submit_file()
        assert reopened == empty_reference
        click("Request list")
        assert page.get_by_test_id("stException").count() == 0
        print("PASS: new and reopened empty drafts reset browser selection; identical bytes upload intentionally.")
        browser.close()


if __name__ == "__main__":
    run()
