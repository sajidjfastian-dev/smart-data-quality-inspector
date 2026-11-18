"""Focused browser smoke check using controlled uploads, never production writes.

Run against the development preview only:
PLAYWRIGHT_NODEJS_PATH=$(which node) python scripts/check_judges_flow.py
"""
import csv
import io
import os
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.set_default_timeout(45000)

        def settle():
            page.wait_for_timeout(900)
            page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
            assert page.get_by_test_id("stException").count() == 0

        def click(name):
            page.get_by_role("button", name=name, exact=True).click()
            settle()

        def checked(name):
            page.get_by_role("checkbox", name=name, exact=True).locator("xpath=ancestor::label").click()
            settle()

        def upload(name):
            page.locator(".st-key-nav_new_request button").click()
            settle()
            page.locator('input[type="file"]').set_input_files({
                "name": name, "mimeType": "text/csv",
                "buffer": b"region,amount,email\n North ,10,a@example.test\nSouth,,b@example.test\nEast,30,c@example.test\nEast,30,c@example.test\n",
            })
            settle()

        def submit():
            page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
            checked("I reviewed all changes and remaining findings; this version is ready for review")
            click("Submit for review")
            return page.get_by_role("heading", level=2).first.inner_text()

        def confirm(action):
            click(action)
            page.get_by_role("dialog").wait_for()
            click("Confirm")

        def download_disabled():
            assert page.get_by_role("button", name="Download approved file", exact=True).is_disabled()

        page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
        settle()
        click("Continue with SSO")
        upload("judges-readiness.csv")
        page.locator(".st-key-quality_overview .js-plotly-plot").nth(5).wait_for()
        assert page.locator(".st-key-quality_overview .js-plotly-plot").count() == 6
        assert page.get_by_role("tab", name="2 · Issue log", exact=True).count() == 0
        page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
        click("Apply selected fixes")
        page.get_by_role("tab", name="3 · Preview & export", exact=True).click()
        settle()
        assert page.locator(".fixed-preview-cell:visible").count() == 2
        assert "a@example.test" not in page.locator(".fixed-preview-table:visible").inner_text()
        reference = submit()
        download_disabled()
        assert page.get_by_role("button", name="Approve request", exact=True).is_disabled()
        checked("I reviewed the changes and remaining findings")
        click("Approve request")
        click("Cancel")
        download_disabled()
        confirm("Approve request")
        download_disabled()
        assert page.get_by_role("button", name="Approve CAB step", exact=True).is_disabled()
        confirm("Approve ticket")
        download_disabled()
        confirm("Approve CAB step")
        download = page.get_by_role("button", name="Download approved file", exact=True)
        assert download.is_enabled()
        with page.expect_download() as event:
            download.click()
        payload = open(event.value.path(), encoding="utf-8-sig").read()
        rows = list(csv.DictReader(io.StringIO(payload)))
        assert len(rows) == 3 and rows[0]["region"] == "North"
        assert float(rows[1]["amount"]) == 20
        assert "@example.test" not in payload
        assert reference in event.value.suggested_filename
        page.locator(".st-key-demo_approval_steps").scroll_into_view_if_needed()
        page.screenshot(path="/tmp/judges-approved-download.png")
        print("PASS upload → charts/issues → applied fixes → masked comparison → submission → approvals → exact approved download.")
        click("Create new draft revision")
        assert page.get_by_role("button", name="Download approved file", exact=True).count() == 0
        click("Request list")
        page.locator('[class*="st-key-rd_record_"]').filter(has_text=reference).get_by_role("button", name="View", exact=True).click()
        settle()
        download_disabled()
        revision = page.get_by_role("combobox", name="Revision", exact=True)
        revision.focus()
        revision.press("ArrowDown")
        revision.press("Home")
        revision.press("Enter")
        settle()
        download_disabled()
        print("PASS new draft and historical revision cannot download as current approved data.")
        upload("judges-rejection.csv")
        rejected_reference = submit()
        page.get_by_role("textbox", name="Rejection reason", exact=True).fill("Review remaining issues before approval")
        page.get_by_role("textbox", name="Rejection reason", exact=True).press("Tab")
        settle()
        click("Reject request")
        download_disabled()
        assert page.locator(".approval-step-header--rejected").count() == 1
        print("PASS rejected request cannot proceed to approval/download.")
        click("Log out")
        click("Continue with SSO")
        for value in (reference, rejected_reference):
            page.get_by_role("textbox", name="Reference contains", exact=True).fill(value)
            page.get_by_role("textbox", name="Reference contains", exact=True).press("Enter")
            settle()
            assert page.locator('[class*="st-key-rd_record_"]').count() == 0
        print("PASS private uploads and requests cleared on logout. Shared demo data not modified.")
        browser.close()


if __name__ == "__main__":
    run()
