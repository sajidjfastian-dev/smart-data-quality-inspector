"""Real-browser smoke check: desktop register, private uploads, Arabic mobile."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright


def run():
    output = Path("generated-artifacts")
    output.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width":1440,"height":1000})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        def settle():
            page.wait_for_timeout(800)
            page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden", timeout=60000)
            assert page.get_by_test_id("stException").count() == 0
        def click(label):
            page.get_by_role("button", name=label, exact=True).click()
            settle()
        page.goto("https://"+os.environ["REPLIT_DEV_DOMAIN"])
        settle()
        response = page.request.get("https://"+os.environ["REPLIT_DEV_DOMAIN"]+"/api/demo/sample")
        assert response.status == 200 and response.json()["count"] == 520
        assert page.locator('input[type="file"]').count() == 0
        click("Continue with SSO")
        page.get_by_role("heading", name="Request dashboard").wait_for()
        assert page.locator('input[type="file"]').count() == 0
        assert page.locator(".signed-in-guide").is_visible()
        page.screenshot(path=str(output/"demo-dashboard-desktop.png"))
        # Session filter must show exactly four of the initial twenty examples.
        combo = page.get_by_role("combobox", name="Session", exact=True)
        combo.click()
        page.get_by_role("option", name="DEMO-HISTORY-01", exact=True).click()
        settle()
        assert page.locator(".request-register-row:not(.request-register-header)").count() == 4
        click("Clear filters")
        page.locator(".st-key-nav_new_request button").click()
        settle()
        uploader = page.locator('input[type="file"]')
        assert uploader.count() == 1
        assert page.get_by_test_id("stSidebar").locator('input[type="file"]').count() == 0
        uploader.set_input_files({"name":"private-browser.csv",
                                 "mimeType":"text/csv",
                                 "buffer":b"name,email,amount\nPRIVATE_BROWSER_SENTINEL,bad-email,10\nB,b@example.test,20\n"})
        settle()
        page.get_by_role("tab", name="3 · Review & fix", exact=True).click()
        settle()
        page.get_by_text("Ready to submit this version to the demo approver", exact=True).click()
        settle()
        click("Submit for review")
        reference = page.get_by_role("heading", level=2).first.inner_text()
        click("Log out")
        click("Continue with SSO")
        assert page.get_by_text(reference, exact=True).count() == 0
        # Arabic narrow sidebar and collapsed-content checks.
        page.get_by_text("AR", exact=True).click()
        settle()
        page.set_viewport_size({"width":390,"height":844})
        settle()
        expand = page.get_by_test_id("stExpandSidebarButton")
        if expand.is_visible():
            expand.click()
            settle()
        assert page.locator(".signed-in-guide").is_visible()
        page.screenshot(path=str(output/"demo-sidebar-arabic-mobile.png"))
        collapse = page.get_by_test_id("stSidebarCollapseButton").get_by_role("button")
        collapse.click()
        settle()
        assert not page.locator(".signed-in-guide").is_visible()
        page.screenshot(path=str(output/"demo-dashboard-arabic-mobile.png"))
        assert not errors, errors
        browser.close()
        print("Browser checks passed: desktop register, session filter, private upload/logout, Arabic mobile sidebar.")


if __name__ == "__main__":
    run()
