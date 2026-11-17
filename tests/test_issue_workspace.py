"""Focused pagination and coverage checks for the 360-degree explorer."""
import unittest
from unittest.mock import patch
from io import BytesIO

import pandas as pd
from streamlit.testing.v1 import AppTest
from issue_workspace import filter_safe_findings, workspace_coverage
from review_approval import frame_digest
from security_guardrails import MASK, mask_findings


def issue_fixture():
    import pandas as pd
    from issue_workspace import render_findings
    issues = pd.DataFrame({
        "Row Number": range(1, 251),
        "Column Name": ["amount"] * 250,
        "Issue Type": ["Missing Value"] * 250,
        "Current Value": ["(empty)"] * 250,
        "Suggested Fix": ["Review"] * 250,
    })
    data = pd.DataFrame({"amount": [None] * 250})
    render_findings(issues, {"amount"}, "test", data)


def clean_fixture():
    import pandas as pd
    from issue_workspace import render_issue_workspace
    data = pd.DataFrame({"amount": [1, 2]})
    issues = pd.DataFrame(columns=["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"])
    render_issue_workspace({"clean.csv": data, "other.csv": data.copy()}, "clean.csv",
                           data, issues, None, None, set(), True, "version")


def mixed_fixture():
    import pandas as pd
    from issue_workspace import render_findings
    data = pd.DataFrame({"Entire row": ["a", "b", "c"], "email": ["private[mail]"] * 3, "amount": [1, 2, 900]})
    issues = pd.DataFrame([
        (1, "Entire row", "Missing Value", "", "Review"),
        (2, "Entire row", "Duplicate Row", "Exact match to an earlier row", "Remove duplicate"),
        (2, "email", "Invalid Email", "private[mail]", "Review address"),
        (3, "amount", "Numeric Outlier", "900", "Review"),
        (3, "email", "Custom: Must contain", "private[mail]", "Include SECRET-EXPECTED"),
        (3, "Entire row", "Missing Value", "[a]+", "Review"),
    ], columns=["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"])
    render_findings(issues, {"email"}, "mixed", data)


def comparison_fixture():
    import pandas as pd
    import streamlit as st
    from issue_workspace import render_issue_workspace
    st.radio("Language", ["English", "العربية"], key="interface_language")
    original = pd.DataFrame({"amount": [1, 2, 3]})
    fixed = pd.DataFrame({"amount": [1, 9]})
    names = ["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"]
    before = pd.DataFrame([(1, "amount", "Missing Value", "", "Review"),
                           (2, "amount", "Missing Value", "", "Review")], columns=names)
    after = pd.DataFrame([(1, "amount", "Numeric Outlier", "1", "Review"),
                          (1, "amount", "Custom: Maximum number", "1", "Review")], columns=names)
    render_issue_workspace({"versions.csv": original}, "versions.csv", original, before,
                           fixed, after, {"amount"}, True, "compare")


def arabic_fixture():
    import pandas as pd
    import streamlit as st
    from issue_workspace import render_findings
    st.session_state["interface_language"] = "العربية"
    data = pd.DataFrame({"Entire row": ["private", "b"], "Findings": [9, 8]})
    issues = pd.DataFrame([
        (1, "Entire row", "Missing Value", "private", "Review"),
        (1, "Findings", "Numeric Outlier", "9", "Review"),
        (2, "Entire row", "Duplicate Row", "Exact match to an earlier row", "Remove duplicate"),
    ], columns=["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"])
    render_findings(issues, {"Entire row"}, "ar", data, downloads=False)


class IssueWorkspaceTests(unittest.TestCase):
    def test_report_is_not_serialized_during_render_or_filter(self):
        with patch("pandas.DataFrame.to_csv", side_effect=AssertionError("Eager CSV serialization")) as export:
            app = AppTest.from_function(issue_fixture, default_timeout=15).run()
            self.assertFalse(app.exception)
            app.text_input(key="test_search").set_value("Review").run()
            self.assertFalse(app.exception)
            export.assert_not_called()

    def test_all_findings_accessible(self):
        app = AppTest.from_function(issue_fixture, default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 100)
        app.number_input(key="test_page").set_value(3).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 50)
        self.assertEqual(app.dataframe[0].value.iloc[-1]["Row Number"], 250)

    def test_clean_file_and_uninspected_coverage(self):
        app = AppTest.from_function(clean_fixture, default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["File"].tolist(), ["clean.csv", "other.csv"])
        self.assertIn("Not inspected", app.dataframe[0].value["Findings"].tolist())

    def test_pagination_resets_even_when_new_filter_still_has_three_pages(self):
        app = AppTest.from_function(issue_fixture, default_timeout=15).run()
        app.number_input(key="test_page").set_value(3).run()
        app.text_input(key="test_search").set_value("Review").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.number_input(key="test_page").value, 1)
        self.assertEqual(app.dataframe[0].value.iloc[0]["Row Number"], 1)

    def test_literal_column_entire_row_never_includes_duplicates(self):
        app = AppTest.from_function(mixed_fixture, default_timeout=15).run()
        app.multiselect(key="mixed_columns").set_value(["Entire row"]).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["Issue Type"].tolist(), ["Missing Value", "Missing Value"])
        app.button(key="mixed_clear").click().run()
        app.selectbox(key="mixed_scope").select("Whole-row duplicates").run()
        self.assertEqual(app.dataframe[0].value["Issue Type"].tolist(), ["Duplicate Row"])

    def test_zero_matches_do_not_remove_complete_row_detail(self):
        app = AppTest.from_function(mixed_fixture, default_timeout=15).run()
        app.text_input(key="mixed_search").set_value("no matching evidence").run()
        self.assertFalse(app.exception)
        app.number_input(key="mixed_row").set_value(3).run()
        self.assertFalse(app.exception)
        related = app.dataframe[-1].value
        self.assertEqual(len(related), 3)
        self.assertEqual(related["Row Number"].tolist(), [3, 3, 3])
        self.assertEqual(related.loc[related["Column Name"] == "email", "Current Value"].iloc[0], MASK)

    def test_sensitive_values_and_custom_expectations_not_searchable(self):
        app = AppTest.from_function(mixed_fixture, default_timeout=15).run()
        for search in ("private[mail]", "SECRET-EXPECTED"):
            app.text_input(key="mixed_search").set_value(search).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("No findings match" in item.value for item in app.info))
        app.text_input(key="mixed_search").set_value("[a]+").run()
        self.assertEqual(len(app.dataframe[0].value), 1)
        self.assertEqual(app.dataframe[0].value.iloc[0]["Current Value"], "[a]+")

    def test_full_filtered_download_is_lazy_and_masked_not_only_current_page(self):
        import streamlit as native
        captured = []
        original = native.download_button

        def capture(*args, **kwargs):
            captured.append(kwargs.copy())
            return original(*args, **kwargs)

        with patch.object(native, "download_button", side_effect=capture):
            app = AppTest.from_function(issue_fixture, default_timeout=15).run()
            app.number_input(key="test_page").set_value(3).run()
        self.assertFalse(app.exception)
        self.assertTrue(callable(captured[-1]["data"]))
        report = pd.read_csv(BytesIO(captured[-1]["data"]()))
        self.assertEqual(len(report), 250)
        self.assertEqual(set(report["Current Value"]), {MASK})
        self.assertEqual(len(app.dataframe[0].value), 50)

    def test_comparison_counts_are_version_specific_and_not_claimed_resolved(self):
        app = AppTest.from_function(comparison_fixture, default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["2", "2", "2"])
        app.radio(key="issues_version_compare").set_value("Fixed copy").run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["2", "2", "1"])
        self.assertTrue(any("Net count change: +0" in item.value for item in app.caption))
        self.assertTrue(any("Counts alone do not identify resolved" in item.value for item in app.caption))

    def test_coverage_marks_stale_and_uninspected_files(self):
        data = pd.DataFrame({"x": [1, 2]})
        empty = pd.DataFrame(columns=["Row Number", "Column Name", "Issue Type"])
        cache = {"stale.csv": {"issues": empty, "digest": frame_digest(data)}}
        changed = pd.DataFrame({"x": [8, 9]})
        rows = workspace_coverage({"active.csv": data, "stale.csv": changed, "new.csv": data},
                                  "active.csv", empty, cache)
        self.assertEqual(rows[0]["Findings"], "0")
        self.assertEqual(rows[1]["Coverage"], "Data changed · open to rescan")
        self.assertEqual(rows[2]["Findings"], "Not inspected")

    def test_filter_helper_matches_literals_only_after_masking(self):
        raw = pd.DataFrame([
            (1, "email", "Invalid Email", "SECRET[1]", "Review"),
            (2, "Entire row", "Duplicate Row", "exact", "Review"),
            (3, "Entire row", "Missing Value", "[a]+", "Review"),
        ], columns=["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"])
        safe = mask_findings(raw, {"email"})
        self.assertTrue(filter_safe_findings(safe, search="SECRET[1]").empty)
        self.assertEqual(len(filter_safe_findings(safe, search="[a]+")), 1)
        self.assertEqual(filter_safe_findings(safe, selected_columns=["Entire row"])["Row Number"].tolist(), [3])

    def test_arabic_preserves_literal_names_masks_values_and_readonly_reuse(self):
        from localization import translate
        app = AppTest.from_function(arabic_fixture, default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.multiselect(key="ar_columns").options, ["Entire row", "Findings"])
        table = app.dataframe[0].value
        self.assertEqual(table[translate("Column Name", "العربية")].iloc[:2].tolist(), ["Entire row", "Findings"])
        self.assertEqual(table[translate("Current Value", "العربية")].iloc[0], MASK)
        self.assertEqual(len(app.get("download_button")), 0)

    def test_locale_switch_preserves_version_and_scope_with_fresh_native_labels(self):
        app = AppTest.from_function(comparison_fixture, default_timeout=15).run()
        app.radio(key="issues_version_compare").set_value("Fixed copy").run()
        scope_key = "issues_compare_Fixed copy_scope"
        app.selectbox(key=scope_key).select("Column findings").run()
        app.radio(key="interface_language").set_value("العربية").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="issues_version_compare_ar").value, "Fixed copy")
        self.assertEqual(app.selectbox(key=scope_key + "_ar").value, "Column findings")
        self.assertIn("نتائج الأعمدة", app.selectbox(key=scope_key + "_ar").options)
        app.radio(key="interface_language").set_value("English").run()
        self.assertFalse(app.exception)
        self.assertEqual(app.radio(key="issues_version_compare").value, "Fixed copy")
        self.assertEqual(app.selectbox(key=scope_key).value, "Column findings")


if __name__ == "__main__":
    unittest.main()
