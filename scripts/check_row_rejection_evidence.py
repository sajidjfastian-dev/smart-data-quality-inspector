"""Focused browser contract for private row overrides and approval evidence."""
import os
from pathlib import Path
from io import BytesIO
import pandas as pd
from playwright.sync_api import sync_playwright


with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page.set_default_timeout(45000)

    def settle():
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
        assert page.get_by_test_id("stException").count() == 0

    def click(name):
        page.get_by_role("button", name=name, exact=True).click()
        settle()

    page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
    page.get_by_text("Inspect. Improve. Trust your data.", exact=True).wait_for()
    assert page.get_by_text("Log in to get started", exact=True).count() == 0
    click("Continue with SSO")
    page.locator(".st-key-nav_new_request button").click()
    settle()
    page.locator('input[type="file"]').set_input_files({
        "name": "row-review.csv", "mimeType": "text/csv",
        "buffer": b"region,amount,observation_date\n North ,10,2024/01/20\n North ,10,2024/01/20\n South ,,2024/02/21\n",
    })
    settle()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    click("Apply automatic fixes")
    assert page.locator('[class*="_reject_2"] button:visible').count() == 0
    page.locator('[class*="_reject_3"] button:visible').first.click()
    settle()
    assert "Rejected rows keep their original values" in page.locator("body").inner_text()
    page.set_viewport_size({"width": 390, "height": 844})
    settle()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.get_by_role("button", name="Reject fix", exact=True).first.scroll_into_view_if_needed()
    page.screenshot(path="/tmp/row-rejection-mobile.png")
    page.set_viewport_size({"width": 1440, "height": 1000})
    click("Apply automatic fixes")
    page.get_by_role("tab", name="3 · Preview & export", exact=True).click()
    settle()
    with page.expect_download() as event:
        page.get_by_role("button", name="Download a clean copy", exact=True).click()
    frame = pd.read_csv(event.value.path())
    assert frame.region.tolist() == ["North", " South "], frame
    assert frame.amount.iloc[0] == 10 and pd.isna(frame.amount.iloc[1])
    assert frame.observation_date.tolist() == ["2024-01-20", "2024/02/21"]
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    page.get_by_text("I reviewed all changes and remaining findings; this version is ready for review", exact=True).click()
    click("Submit for review")
    page.get_by_text("I reviewed the changes and remaining findings", exact=True).click()
    click("Approve request")
    click("Confirm")
    click("Approve ticket")
    page.get_by_role("dialog").locator('input[type="file"]').set_input_files({
        "name": "ticket-proof.txt", "mimeType": "text/plain", "buffer": b"Private ticket approval confirmation",
    })
    settle()
    click("Confirm")
    click("Approve CAB step")
    page.get_by_role("dialog").locator('input[type="file"]').set_input_files({
        "name": "cab-proof.txt", "mimeType": "text/plain", "buffer": b"Private CAB approval confirmation",
    })
    settle()
    click("Confirm")
    page.get_by_text("Private approval evidence", exact=True).click()
    page.get_by_text("cab-proof.txt", exact=True).wait_for()
    assert page.get_by_role("button", name="Download evidence", exact=True).count() == 2
    with page.expect_download() as event:
        page.get_by_role("button", name="Download evidence", exact=True).last.click()
    assert Path(event.value.path()).read_bytes() == b"Private CAB approval confirmation"
    with page.expect_download() as event:
        page.get_by_role("button", name="Download approved file", exact=True).click()
    approved = pd.read_csv(event.value.path())
    pd.testing.assert_frame_equal(approved, frame)
    assert b"Private CAB" not in Path(event.value.path()).read_bytes()
    page.set_viewport_size({"width": 390, "height": 844})
    settle()
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.screenshot(path="/tmp/approval-evidence-mobile.png")
    page.set_viewport_size({"width": 1440, "height": 1000})
    page.get_by_role("radio", name="AR", exact=True).click()
    settle()
    assert page.locator("html").get_attribute("dir") == "rtl"
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.get_by_role("radio", name="EN", exact=True).click()
    settle()
    click("Log out")
    click("Continue with SSO")
    assert page.get_by_text("cab-proof.txt", exact=True).count() == 0
    browser.close()
    print("PASS: retained-row rejection, duplicate removals preserved, reapplication, exact export, ticket/CAB evidence, mobile/Arabic and logout.")
