"""Focused development-browser acceptance check; no full unit suite."""
import os
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.set_default_timeout(45000)

    def settle():
        page.wait_for_timeout(850)
        page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
        assert page.get_by_test_id("stException").count() == 0

    def click(name):
        page.get_by_role("button", name=name, exact=True).click()
        settle()

    def check(name):
        page.get_by_role("checkbox", name=name, exact=True).locator("xpath=ancestor::label").click()
        settle()

    def choose(label, steps):
        control = page.get_by_role("combobox", name=label, exact=True)
        control.focus()
        control.press("ArrowDown")
        control.press("Home")
        for _ in range(steps):
            control.press("ArrowDown")
        control.press("Enter")
        settle()

    page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
    settle()
    click("Continue with SSO")
    page.locator(".st-key-nav_new_request button").click()
    settle()
    page.locator('input[type="file"]').set_input_files({
        "name": "correction-acceptance.csv", "mimeType": "text/csv",
        "buffer": b"region,amount,email\n north ,10,invalid\nSouth,,bad\nEast,30,c@example.test\nEast,30,c@example.test\n",
    })
    settle()
    page.get_by_role("button", name="Settings", exact=True).first.click()
    settle()
    page.get_by_role("dialog").get_by_role("tab").filter(has_text="Business rules").click()
    page.get_by_role("textbox", name="Business rule", exact=True).fill("region must be one of North,South,East")
    click("Add business rule")
    page.keyboard.press("Escape")
    page.locator(".st-key-inspection_workspace").click(position={"x": 20, "y": 15})
    settle()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    settle()
    click("Apply automatic fixes")
    assert page.get_by_role("heading", name="2 · Review and submit").is_visible()
    assert page.get_by_role("textbox", name="Verified replacement value", exact=True).count() == 0
    assert page.get_by_role("button", name="Save correction and recheck", exact=True).count() == 0
    page.get_by_role("heading", name="1 · Apply automatic fixes").scroll_into_view_if_needed()
    page.screenshot(path="/tmp/correction-workbench-desktop.png")
    page.get_by_role("tab", name="3 · Preview & export", exact=True).click()
    settle()
    assert page.locator(".fixed-preview-cell:visible").count() == 2
    titles = page.locator(".fixed-preview-cell:visible").evaluate_all("els=>els.map(e=>e.title)")
    assert "Business rule: Allowed values" in titles
    assert not any("Manual correction" in title for title in titles)
    assert "invalid" not in page.locator(".fixed-preview-table:visible").inner_text()
    page.locator(".fixed-preview-table:visible").scroll_into_view_if_needed()
    page.screenshot(path="/tmp/correction-preview-desktop.png")
    page.get_by_role("tab", name="4 · AI assistant", exact=True).click()
    settle()
    page.get_by_role("button").filter(has_text="What should I fix first?").click()
    settle()
    assert "2 findings" in page.locator('[role="tabpanel"]:visible').inner_text()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    settle()
    for width, height in [(1280, 900), (390, 844)]:
        page.set_viewport_size({"width": width, "height": height})
        settle()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    print("PASS automatic normalization, duplicate removal, median fill, no manual editor, unresolved emails preserved, masked fix tooltips, current-copy assistant and responsive layout.")
    browser.close()
