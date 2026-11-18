"""Focused browser check of the real sample API and approved public-data download."""
import os
from io import BytesIO
import pandas as pd
from pandas.testing import assert_frame_equal
from playwright.sync_api import sync_playwright
from public_sample import original


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width":1440, "height":1000})
        page.set_default_timeout(45000)
        def settle():
            page.wait_for_timeout(900)
            page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
            assert page.get_by_test_id("stException").count() == 0
        def click(text):
            page.get_by_role("button", name=text, exact=True).click()
            settle()
        def check(text):
            page.get_by_role("checkbox", name=text, exact=True).locator("xpath=ancestor::label").click()
            settle()
        def confirm(text):
            click(text)
            click("Confirm")
        page.goto("https://"+os.environ["REPLIT_DEV_DOMAIN"])
        settle()
        click("Continue with SSO")
        page.locator(".st-key-nav_new_request button").click()
        settle()
        click("Explore sample workspace")
        page.get_by_text("ecb_fx_demo_errors.csv", exact=True).first.wait_for()
        assert page.get_by_text("Source: European Central Bank.", exact=False).count() > 0
        page.locator(".st-key-nav_new_request button").click()
        settle()
        page.get_by_role("button", name="Settings", exact=True).first.click()
        page.get_by_role("tab", name="Data APIs", exact=True).click()
        click("Try sample API")
        page.get_by_role("tab", name="2 · Review & fix", exact=True).wait_for()
        page.keyboard.press("Escape")
        page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
        click("Apply automatic fixes")
        page.get_by_role("checkbox", name="I reviewed all changes and remaining findings; this version is ready for review", exact=True).wait_for()
        assert page.get_by_text("Continue as a private request", exact=True).count() == 0
        check("I reviewed all changes and remaining findings; this version is ready for review")
        click("Submit for review")
        check("I reviewed the changes and remaining findings")
        confirm("Approve request")
        confirm("Approve ticket")
        confirm("Approve CAB step")
        with page.expect_download() as event:
            page.get_by_role("button", name="Download approved file", exact=True).click()
        from pathlib import Path
        result = pd.read_csv(BytesIO(Path(event.value.path()).read_bytes()))
        assert_frame_equal(result, original())
        page.screenshot(path="/tmp/ecb-approved-flow.png")
        print("PASS: workspace attribution, actual API, shared correction/review/CAB flow and exact 600-row original-value download.")
        browser.close()


if __name__ == "__main__":
    run()
