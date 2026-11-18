"""Browser check of pre-upload rule authoring and real correction previews."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
    page.get_by_role("button", name="Continue with SSO", exact=True).click(timeout=60000)
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("tab", name="Business rules", exact=True).click()
    page.get_by_role("textbox", name="Target column name", exact=True).fill("status")
    page.get_by_role("combobox", name="Business rule type", exact=True).click()
    page.get_by_role("option", name="Value mapping", exact=True).click()
    page.get_by_role("textbox", name="Business rule value", exact=True).fill('{"pending":"Approved"}')
    page.get_by_role("combobox", name="Rule behavior", exact=True).click()
    page.get_by_role("option", name="Correct automatically", exact=True).click()
    page.get_by_role("button", name="Add business rule", exact=True).click()
    page.wait_for_timeout(600)
    assert page.get_by_test_id("stException").count() == 0
    page.keyboard.press("Escape")
    page.locator(".st-key-nav_new_request button").click()
    page.locator('input[type=file]').set_input_files(
        {"name": "rules.csv", "mimeType": "text/csv", "buffer": b"status,amount\npending,10\nother,20\n"})
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click(timeout=60000)
    page.get_by_role("button", name="Apply automatic fixes", exact=True).click()
    page.get_by_text("Business rule: Value mapping", exact=False).first.wait_for(timeout=30000)
    page.get_by_role("tab", name="3 · Preview & export", exact=True).click()
    # Tabs rerun Streamlit; wait for the current deferred download registration
    # rather than clicking the button from the outgoing render.
    page.wait_for_timeout(700)
    page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
    assert page.locator(".fixed-preview-cell").count() > 0
    with page.expect_download() as download:
        page.get_by_role("button", name="Download a clean copy", exact=True).click()
    payload = Path(download.value.path()).read_bytes()
    assert b"Approved" in payload and b"pending" not in payload
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_role("tab", name="Business rules", exact=True).click()
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(500)
    assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
    page.screenshot(path="/tmp/business-rules-mobile.png")
    assert page.get_by_test_id("stException").count() == 0
    browser.close()
    print("PASS pre-upload rule → upload → automatic mapping → highlighted preview → exact CSV; mobile settings.")
