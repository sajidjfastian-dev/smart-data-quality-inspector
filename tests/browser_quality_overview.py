"""Focused live-preview smoke check using only a tiny synthetic CSV.

Run: PLAYWRIGHT_NODEJS_PATH=$(which node) python tests/browser_quality_overview.py
No direct database access, endpoint configuration, or privacy bypass is used.
"""
from playwright.sync_api import sync_playwright


CSV = (
    "Entire row,email,event_date,amount,segment\n"
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
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def settle():
            page.wait_for_timeout(1400)
            page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden", timeout=60000)
            assert page.locator('[data-testid="stException"]').count() == 0

        def controls():
            return page.locator(".st-key-qo_panel_controls .js-plotly-plot").evaluate(
                "e=>({names:e.data[0].customdata, counts:e.data[0].x, labels:e.data[0].text})"
            )

        def coverage():
            return page.locator(".st-key-qo_panel_rows .js-plotly-plot").evaluate("e=>e.data[0].values")

        page.goto("http://127.0.0.1:5000/")
        page.locator(".st-key-sidebar_login button").wait_for(timeout=60000)
        page.locator(".st-key-sidebar_login button").click()
        settle()
        page.locator(".st-key-nav_new_request button").click()
        settle()
        page.locator('input[type="file"]').set_input_files(
            {"name": "quality-controls.csv", "mimeType": "text/csv", "buffer": CSV.encode()}
        )
        page.locator(".st-key-quality_overview .js-plotly-plot").first.wait_for(timeout=60000)
        settle()
        assert sum(controls()["counts"]) == 7
        assert coverage() == [5, 3]
        print("PASS real upload: 7 findings across 5 unique affected rows of 8")

        page.get_by_role("button", name="Settings", exact=True).first.click()
        settle()
        page.get_by_role("dialog").wait_for()
        page.get_by_role("dialog").get_by_role("tab").filter(has_text="Inspection checks").click()
        settle()
        page.get_by_role("dialog").get_by_text("Missing values", exact=True).click()
        settle()
        assert sum(controls()["counts"]) == 6
        assert "Not assessed" in controls()["labels"][0]
        print("PASS disabling Missing values updates real counts and marks it not assessed")

        rule_column = page.get_by_role("combobox", name="Rule column", exact=True)
        rule_column.focus()
        rule_column.press("ArrowDown")
        rule_column.press("End")
        rule_column.press("Enter")
        page.get_by_role("textbox", name="Expected value", exact=True).fill("North")
        page.get_by_role("button", name="Add rule", exact=True).click()
        settle()
        assert sum(controls()["counts"]) == 9
        assert coverage() == [7, 1]
        assert controls()["counts"][-1] == 3
        print("PASS configured custom rule adds 3 findings; 7 unique rows affected")
        page.keyboard.press("Escape")
        page.locator(".st-key-inspection_workspace").click(position={"x": 20, "y": 15})
        settle()

        for width, height in [(1920, 1080), (1280, 900)]:
            page.set_viewport_size({"width": width, "height": height})
            settle()
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator(".st-key-inspection_workspace").scroll_into_view_if_needed()
            page.screenshot(path=f"/tmp/quality-header-{width}.png")
            page.locator(".st-key-qo_panel_rows").scroll_into_view_if_needed()
            page.screenshot(path=f"/tmp/quality-overview-{width}.png")
            assert page.locator(".st-key-quality_overview .js-plotly-plot").count() == 6
            assert page.locator(".st-key-quality_overview table, .st-key-quality_overview [data-testid=stDataFrame]").count() == 0
            print(f"PASS {width}px: 6 charts, no tables, no horizontal overflow")

        page.get_by_role("radio", name="AR", exact=True).click()
        settle()
        page.set_viewport_size({"width": 390, "height": 844})
        settle()
        assert page.locator("html").get_attribute("dir") == "rtl"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert "الصفوف" in page.locator(".st-key-qo_panel_rows .js-plotly-plot").evaluate("e=>e.layout.title.text")
        sections = ["inspection_workspace", "inspection_privacy", "inspection_workflow",
                    "qo_panel_rows", "qo_panel_controls", "qo_panel_columns", "qo_panel_heatmap",
                    "qo_panel_multiplicity", "qo_panel_ranges"]
        for section in sections:
            element = page.locator(".st-key-" + section)
            element.scroll_into_view_if_needed()
            page.screenshot(path=f"/tmp/quality-ar-mobile-{section}.png")
            assert element.evaluate("e=>e.scrollWidth <= e.clientWidth + 1"), section
        # DOM width alone misses SVG labels clipped by a chart card.
        axes = page.locator(".st-key-quality_overview .ytick text").evaluate_all("""
es => es.map(e => {
    const r = e.getBoundingClientRect();
    const bounds = e.closest('.js-plotly-plot').getBoundingClientRect();
    return {text: e.textContent, inside: r.left >= bounds.left - 1 && r.right <= bounds.right + 1};
})
""")
        assert all(label["inside"] for label in axes), axes
        assert not errors, errors
        print("PASS Arabic mobile: localized charts, RTL, all sections without overflow; no browser errors")
        browser.close()


if __name__ == "__main__":
    run()
