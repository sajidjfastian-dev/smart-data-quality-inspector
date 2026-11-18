"""Exercise the real inspection/insights/chat flow at desktop and phone sizes."""
import os
from playwright.sync_api import sync_playwright


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        for width in (1440, 390):
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.set_default_timeout(45000)

            def settle():
                page.wait_for_timeout(700)
                page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
                assert page.get_by_test_id("stException").count() == 0

            def tab(name):
                page.get_by_role("tab", name=name, exact=True).click()
                settle()
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")

            page.goto("https://" + os.environ["REPLIT_DEV_DOMAIN"])
            settle()
            if width < 500:
                page.get_by_role("button", name="Expand sidebar", exact=True).click()
            page.get_by_role("button", name="Continue with SSO", exact=True).click()
            settle()
            page.locator(".st-key-nav_new_request button").click()
            settle()
            if width < 500:
                page.get_by_role("button", name="Collapse sidebar", exact=True).click()
            page.locator('input[type="file"]').set_input_files({
                "name": "responsive.csv", "mimeType": "text/csv",
                "buffer": b"region,amount,email\n North ,10,bad-email\nSouth,,bob@example.test\nEast,30,c@example.test\nEast,30,c@example.test\n",
            })
            settle()
            tab("5 · Data insights")
            page.get_by_role("heading", name="Data summary", exact=True).wait_for()
            assert "4 rows and 3 fields" in page.locator(".st-key-dataset_summary").inner_text()
            assert page.locator(".st-key-insights_workspace .js-plotly-plot").count() > 0
            assert page.get_by_role("button", name="Generate AI summary").count() == 0
            tab("2 · Review & fix")
            page.get_by_role("button", name="Apply automatic fixes").click()
            settle()
            assert page.get_by_text("Review unresolved issues", exact=True).count() == 1
            assert page.get_by_text("Remaining findings", exact=True).count() >= 1
            page.get_by_text("Review unresolved issues", exact=True).click()
            settle()
            assert "bad-email" not in page.get_by_test_id("stMain").inner_text()
            tab("3 · Preview & export")
            assert page.get_by_role("button", name="Download a clean copy").is_enabled()
            assert page.get_by_text("Upload multiple files to export the full batch as one ZIP.").count() == 0
            tab("4 · AI assistant")
            chat = page.get_by_placeholder("Ask about responsive.csv…")
            chat.fill("How many rows are duplicates?")
            chat.press("Enter")
            settle()
            assert page.get_by_test_id("stChatMessage").count() >= 3
            print(f"PASS {width}px: intake, charts, summary, safe review, export and chatbot")
            page.close()
        browser.close()


if __name__ == "__main__":
    run()
