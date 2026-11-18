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
    page.get_by_role("dialog").get_by_role("tab").filter(has_text="Inspection checks").click()
    choose("Rule column", 0)
    choose("Rule type", 1)
    page.get_by_role("textbox", name="Expected value", exact=True).fill("North,South,East")
    click("Add rule")
    page.keyboard.press("Escape")
    page.locator(".st-key-inspection_workspace").click(position={"x": 20, "y": 15})
    settle()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    settle()
    if not page.get_by_role("checkbox", name="Normalize case and spacing to allowed values", exact=True).is_checked():
        check("Normalize case and spacing to allowed values")
    click("Apply selected fixes")
    assert page.get_by_role("heading", name="2 · Resolve remaining findings").is_visible()
    page.get_by_text("All matching rows", exact=True).click()
    settle()
    page.get_by_role("textbox", name="Verified replacement value", exact=True).fill("still-invalid")
    check("I verified this value and the selected rows")
    click("Save correction and recheck")
    assert page.get_by_text("This value still fails an active rule", exact=False).is_visible()
    page.get_by_role("textbox", name="Verified replacement value", exact=True).fill("verified@example.test")
    click("Save correction and recheck")
    if not page.get_by_text("No findings remain under the enabled quality controls.", exact=True).is_visible():
        print(page.locator(".st-key-correction_workspace").inner_text()[:8000])
    assert page.get_by_text("No findings remain under the enabled quality controls.", exact=True).is_visible()
    assert page.get_by_role("button", name="Apply selected fixes", exact=True).is_disabled()
    page.get_by_role("heading", name="1 · Apply rule-based corrections").scroll_into_view_if_needed()
    page.screenshot(path="/tmp/correction-workbench-desktop.png")
    page.get_by_role("tab", name="3 · Preview & export", exact=True).click()
    settle()
    assert page.locator(".fixed-preview-cell:visible").count() == 4
    titles = page.locator(".fixed-preview-cell:visible").evaluate_all("els=>els.map(e=>e.title)")
    assert "Normalized to allowed value" in titles
    assert any("Manual correction" in title for title in titles)
    assert "verified@example.test" not in page.locator(".fixed-preview-table:visible").inner_text()
    page.locator(".fixed-preview-table:visible").scroll_into_view_if_needed()
    page.screenshot(path="/tmp/correction-preview-desktop.png")
    page.get_by_role("tab", name="4 · AI assistant", exact=True).click()
    settle()
    page.get_by_role("button").filter(has_text="What should I fix first?").click()
    settle()
    assert "0 findings" in page.locator('[role="tabpanel"]:visible').inner_text()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    settle()
    for width, height in [(1280, 900), (390, 844)]:
        page.set_viewport_size({"width": width, "height": height})
        settle()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    print("PASS custom-rule normalization, duplicate removal, median fill, rejected invalid edit, bulk manual correction, masked fix tooltips, current-copy assistant, responsive layout.")
    browser.close()
