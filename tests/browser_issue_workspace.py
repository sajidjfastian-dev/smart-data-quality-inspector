"""Focused real-preview checks. Uses genuine demo sign-in, upload and fixes.

Run: PLAYWRIGHT_NODEJS_PATH=$(which node) python tests/browser_issue_workspace.py
"""
from io import BytesIO
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright


HEADER = "Entire row,email,event_date,amount,segment\n"
ROWS = (
    "A,bad,2024-01-01,10,North\n"
    "B,b@example.test,bad-date,15,South\n"
    ",bad,2024-02-01,18,North\n"
    "C,c@example.test,2024-01-05,22,South\n"
    "D,d@example.test,2024-01-06,21,North\n"
    "E,e@example.test,2024-01-07,24,South\n"
    "F,f@example.test,2024-01-08,900,North\n"
    "A,bad,2024-01-01,10,North\n"
)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settle():
            page.wait_for_timeout(1100)
            # The app deliberately hides Streamlit's toolbar. A hidden Stop
            # button therefore does not mean the script finished: acting then
            # can type into an old combobox which the rerun immediately replaces.
            page.locator(
                '[data-testid="stApp"][data-test-script-state="notRunning"]'
            ).wait_for(state="attached", timeout=60000)
            failures = page.locator('[data-testid="stException"]')
            if failures.count():
                page.screenshot(path="/tmp/issue-browser-error.png")
                raise AssertionError(failures.all_inner_texts())

        def workspace():
            return page.locator(".st-key-issue_workspace")

        def results():
            return workspace().locator(".issue-results").inner_text()

        def export():
            with page.expect_download() as event:
                workspace().get_by_role("button", name="Download issue report", exact=True).click()
            downloaded = event.value
            return pd.read_csv(BytesIO(Path(downloaded.path()).read_bytes()), keep_default_na=False)

        def snapshot(name, target):
            target.scroll_into_view_if_needed()
            page.screenshot(path=f"/tmp/issue-{name}.png")

        def choose_native(locator, last=False):
            locator.focus()
            locator.press("ArrowDown")
            locator.press("End" if last else "Home")
            locator.press("Enter")
            settle()

        def select_version(index):
            versions = workspace().get_by_role("radiogroup", name="Findings version", exact=True)
            versions.evaluate("e=>e.scrollIntoView({block:'center'})")
            # The input itself is visually hidden; click its visible native
            # label, not its tiny input box beneath the pinned app header.
            versions.locator("label").nth(index).click()
            settle()
            assert versions.get_by_role("radio").nth(index).is_checked()

        page.goto("http://127.0.0.1:5000/")
        page.locator(".st-key-sidebar_login button").wait_for(timeout=60000)
        page.locator(".st-key-sidebar_login button").click()
        settle()
        active = page.locator(".st-key-nav_requests button")
        assert active.evaluate("e=>getComputedStyle(e).backgroundColor") == "rgb(21, 95, 80)"
        snapshot("navigation-1920", active)
        page.locator(".st-key-nav_new_request button").click()
        settle()
        assert page.locator(".st-key-nav_new_request button").evaluate(
            "e=>getComputedStyle(e).backgroundColor"
        ) == "rgb(21, 95, 80)"
        page.locator('input[type="file"]').set_input_files([
            {"name": "issue-review.csv", "mimeType": "text/csv", "buffer": (HEADER + ROWS * 32).encode()},
            {"name": "not-yet-opened.csv", "mimeType": "text/csv", "buffer": b"reference,total\nA,3\nB,8\n"},
        ])
        page.locator(".st-key-quality_overview .js-plotly-plot").first.wait_for(timeout=60000)
        settle()
        page.get_by_role("tab").filter(has_text="2 · Issue log").click()
        settle()
        assert "441 matching / 441" in results(), results()
        report = export()
        assert len(report) == 441
        assert set(report.loc[report["Column Name"] == "email", "Current Value"]) == {"••••"}
        assert page.locator(".issue-context").inner_text().find("256 rows") >= 0
        print("PASS genuine upload: 441 findings; protected email values masked in full report")

        for width, height in ((1920, 1080), (1280, 900)):
            page.set_viewport_size({"width": width, "height": height})
            settle()
            snapshot(f"original-{width}", workspace().locator(".issue-intro"))
            snapshot(f"filters-{width}", workspace().get_by_role("textbox", name="Search findings", exact=True))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            print(f"PASS {width}px EN: scoped layout, no horizontal page overflow")

        pager = workspace().get_by_role("spinbutton", name="Findings page", exact=True)
        pager.fill("3")
        pager.press("Enter")
        settle()
        assert pager.input_value() == "3"
        assert len(export()) == 441, "Report must include every matching page"
        search = workspace().get_by_role("textbox", name="Search findings", exact=True)
        search.fill("Review")
        search.press("Enter")
        settle()
        assert workspace().get_by_role("spinbutton", name="Findings page", exact=True).input_value() == "1"
        search.fill("bad")
        search.press("Enter")
        settle()
        # The email value 'bad' is masked. Only the unprotected date 'bad-date'
        # remains searchable; this also checks search does not use raw issues.
        assert "32 matching / 441" in results(), results()
        assert set(export()["Column Name"]) == {"event_date"}
        workspace().get_by_text("Row-level issue detail", exact=True).click()
        row = workspace().get_by_role("spinbutton", name="Row number to inspect", exact=True)
        row.fill("3")
        row.press("Enter")
        settle()
        assert workspace().get_by_text("All findings on this row", exact=True).is_visible()
        assert workspace().locator('[data-testid="stDataFrame"]').count() == 4  # coverage, results, values, all row findings
        snapshot("row-detail-1280", row)
        print("PASS pagination reset, whole-filter download and independently complete row detail")

        workspace().get_by_role("button", name="Clear filters", exact=True).click()
        settle()
        column = workspace().get_by_role("combobox", name="Columns", exact=True)
        column.click()
        column.press_sequentially("Entire row", delay=60)
        # Actual native popup accessible name is "Columns Open", not "Columns":
        # aria-labelledby also includes the open button. Follow aria-controls
        # rather than guessing the portal's computed accessible name.
        popup_id = column.get_attribute("aria-controls")
        assert popup_id, "Columns combobox did not open its associated listbox"
        page.locator(f'[id="{popup_id}"]').get_by_role(
            "option", name="Entire row", exact=True
        ).click()
        # Multiselects intentionally stay open; dismiss the popup so the rest
        # of the page is available to keyboard/accessibility role locators.
        page.keyboard.press("Escape")
        settle()
        assert "32 matching / 441" in results(), results()
        assert set(export()["Issue Type"]) == {"Missing Value"}
        workspace().get_by_role("button", name="Clear filters", exact=True).click()
        settle()
        scope = workspace().get_by_role("combobox", name="Finding scope", exact=True)
        choose_native(scope, last=True)
        assert "249 matching / 441" in results(), results()
        assert set(export()["Issue Type"]) == {"Duplicate Row"}
        print("PASS literal Entire row column is separate from whole-row duplicate scope")

        page.get_by_role("tab").filter(has_text="Review & fix").click()
        settle()
        page.get_by_role("button", name="Apply selected fixes", exact=True).click()
        settle()
        page.get_by_role("tab").filter(has_text="2 · Issue log").click()
        settle()
        select_version(1)
        assert "7 rows" in workspace().locator(".issue-context").inner_text()
        fixed_report = export()
        assert len(fixed_report) == 5
        assert "5 matching / 5" in results()
        for width, height in ((1920, 1080), (1280, 900)):
            page.set_viewport_size({"width": width, "height": height})
            settle()
            snapshot(f"fixed-{width}", workspace().locator(".issue-intro"))
            snapshot(f"fixed-findings-{width}", workspace().locator(".issue-results"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        select_version(0)
        assert "256 rows" in workspace().locator(".issue-context").inner_text()
        assert "441 matching / 441" in results()
        print("PASS real fixes: original 256 rows/441 findings preserved; fixed 7 rows/5 findings")

        page.get_by_role("radio", name="AR", exact=True).click()
        settle()
        page.set_viewport_size({"width": 390, "height": 844})
        settle()
        assert page.locator("html").get_attribute("dir") == "rtl"
        assert workspace().get_by_text("سجل المشكلات", exact=True).is_visible()
        assert workspace().get_by_role("radio").nth(0).is_checked(), (
            "Arabic version indicator is stale. If these native widget keys lack "
            "the _ar suffix, the running process still has the pre-fix module: "
            + str(workspace().locator('[class*="st-key-issues_version_"]').evaluate_all(
                "es=>es.map(e=>e.className)"
            ))
        )
        ar_scope = workspace().get_by_role("combobox", name="نطاق النتائج", exact=True)
        assert ar_scope.input_value() == "جميع النتائج"
        snapshot("ar-mobile-header", workspace().locator(".issue-intro"))
        snapshot("ar-mobile-filters", workspace().get_by_role("textbox", name="البحث في النتائج", exact=True))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        choose_native(ar_scope, last=True)
        assert results().startswith("249 "), results()
        page.get_by_role("radio", name="EN", exact=True).click()
        settle()
        assert workspace().get_by_role("radio").nth(0).is_checked()
        assert workspace().get_by_role("combobox", name="Finding scope", exact=True).input_value() == "Whole-row duplicates"
        assert results().startswith("249 "), results()
        page.get_by_role("radio", name="AR", exact=True).click()
        settle()
        assert ar_scope.input_value() == "تكرار الصف الكامل"
        assert results().startswith("249 "), results()
        workspace().get_by_role("button", name="مسح عوامل التصفية", exact=True).click()
        settle()
        assert results().startswith("441 "), results()
        assert ar_scope.input_value() == "جميع النتائج"
        versions = workspace().get_by_role("radiogroup")
        versions.get_by_role("radio").nth(1).focus()
        versions.get_by_role("radio").nth(1).press("Space")
        settle()
        assert versions.get_by_role("radio").nth(1).is_checked()
        assert "7 صفوف" in workspace().locator(".issue-context").inner_text()
        assert results().startswith("5 "), results()
        snapshot("ar-mobile-fixed", workspace().locator(".issue-context"))
        snapshot("ar-mobile-fixed-findings", workspace().locator(".issue-results"))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        print("PASS Arabic mobile: original/fixed, keyboard version toggle, localized RTL controls, no page overflow or browser errors")
        browser.close()


if __name__ == "__main__":
    run()
