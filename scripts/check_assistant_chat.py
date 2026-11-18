"""Focused live chat checks using a controlled upload; no external model."""
import os
from playwright.sync_api import sync_playwright


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.set_default_timeout(60000)

    def settle():
        page.wait_for_timeout(850)
        page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
        assert page.get_by_test_id("stException").count() == 0

    def click(name):
        page.get_by_role("button", name=name, exact=True).click()
        settle()

    def ask(question):
        field = page.get_by_test_id("stChatInputTextArea")
        field.fill(question)
        field.press("Enter")
        settle()
        return page.get_by_test_id("stChatMessage").last.inner_text()

    page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
    settle()
    click("Continue with SSO")
    page.locator(".st-key-nav_new_request button").click()
    settle()
    page.locator('input[type="file"]').set_input_files({
        "name": "assistant-check.csv", "mimeType": "text/csv",
        "buffer": b"region,amount,email\nNorth,10,a@example.test\nNorth,30,b@example.test\nSouth,50,c@example.test\nSouth,,d@example.test\nSouth,50,c@example.test\n",
    })
    settle()
    page.get_by_role("tab", name="4 · AI assistant", exact=True).click()
    settle()
    click("Summarize my data")
    assert "5 rows" in page.get_by_test_id("stChatMessage").last.inner_text()
    answer = ask("Average amount")
    assert "Average: 35" in answer and "Total: 140" in answer
    assert "Continuing with" in ask("What is its maximum?")
    answer = ask("Average amount by region")
    assert "North: 20" in answer and "South: 50" in answer
    assert "distinct non-null values" in ask("Top values in region")
    assert "protected columns" in ask("Top values in email")
    assert "cannot reliably evaluate" in ask("Average amount where region = North")
    click("Which quality rules are active?")
    assert "Active built-in checks" in page.get_by_test_id("stChatMessage").last.inner_text()
    click("What changed after fixes?")
    assert "No corrected copy" in page.get_by_test_id("stChatMessage").last.inner_text()
    page.get_by_role("tab", name="2 · Review & fix", exact=True).click()
    settle()
    click("Apply automatic fixes")
    page.get_by_role("tab", name="4 · AI assistant", exact=True).click()
    settle()
    click("What changed after fixes?")
    answer = page.get_by_test_id("stChatMessage").last.inner_text()
    assert "Rows: 5 → 4" in answer and "Findings under current rules: 2 → 0" in answer
    assert "Removed duplicate row" in answer and "Filled missing value" in answer
    click("Is this ready for review?")
    assert "No findings remain under the configured controls" in page.get_by_test_id("stChatMessage").last.inner_text()
    answer = ask("Average amount? Top values in region?")
    assert "Numeric summary" in answer and "distinct non-null values" in answer
    assert "a@example.test" not in page.locator('[role="tabpanel"]:visible').inner_text()
    page.locator(".st-key-data_assistant_header").scroll_into_view_if_needed()
    page.screenshot(path="/tmp/assistant-desktop.png")
    page.set_viewport_size({"width": 390, "height": 844})
    settle()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    print("PASS summaries, exact numeric/grouped results, follow-up context, protected values, unsupported conditions, rules, correction deltas, readiness and mobile layout.")
    browser.close()
