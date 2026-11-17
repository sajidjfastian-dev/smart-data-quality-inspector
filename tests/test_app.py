"""End-to-end quick-sample regressions against the real Streamlit script."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal
import streamlit as st
from streamlit.testing.v1 import AppTest
from sample_fixtures import load_test_fixture


APP = Path(__file__).resolve().parents[1] / "app.py"
SAMPLE = "Sample messy dataset"
COLUMNS = [
    "customer_id", "name", "email", "signup_date",
    "age", "annual_spend", "region", "is_active",
]
EXPECTED_ISSUES = {
    (8, "name", "Missing Value"),
    (33, "name", "Missing Value"),
    (25, "email", "Missing Value"),
    (4, "email", "Invalid Email"),
    (9, "email", "Invalid Email"),
    (13, "signup_date", "Inconsistent Date Format"),
    (20, "signup_date", "Invalid Date"),
    (16, "annual_spend", "Missing Value"),
    (39, "annual_spend", "Numeric Outlier"),
    (50, "Entire row", "Duplicate Row"),
}
FIX_LABELS = [
    "Remove exact duplicate rows",
    "Trim leading and trailing whitespace",
    "Fill missing values in selected Numeric columns with the median",
    "Standardize valid dates to YYYY-MM-DD",
]


class QuickSampleTests(unittest.TestCase):
    def setUp(self):
        # Each test gets its own session; never import app.py as a helper module.
        self.app = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assert_no_exception()

    def assert_no_exception(self, app=None):
        app = app if app is not None else self.app
        self.assertEqual([error.message for error in app.exception], [])

    def widget(self, kind, label):
        matches = [item for item in getattr(self.app, kind) if item.label == label]
        self.assertEqual(len(matches), 1, f"Expected one {kind}: {label}")
        return matches[0]

    def click(self, label):
        self.widget("button", label).click().run()
        self.assert_no_exception()

    def load_sample(self):
        load_test_fixture(self.app)
        self.assert_no_exception()
        return self.app.session_state["inspector_datasets"][SAMPLE]

    def issue_keys(self, issues):
        self.assertEqual(
            list(issues.columns),
            ["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"],
        )
        return set(issues.iloc[:, :3].itertuples(index=False, name=None))

    def test_initial_screen_and_sample_scan_survive_rerun(self):
        self.assertNotIn("inspector_datasets", self.app.session_state)
        landing = next(item.value for item in self.app.markdown if 'class="welcome-panel"' in item.value)
        self.assertIn("Turn data into", landing)
        self.assertIn("Start in the sidebar", landing)
        for check in ("missing values", "duplicates", "formats", "outliers"):
            self.assertIn(check, landing)
        self.assertNotIn("Explore with 50-row quick sample", [button.label for button in self.app.button])
        self.assertFalse(self.widget("button", "Explore sample workspace").disabled)
        self.assertNotIn(
            "Download 5-file sample pack",
            [item.proto.label for item in self.app.sidebar.get("download_button")],
        )
        original = self.load_sample().copy(deep=True)
        self.assertEqual(original.shape, (50, 8))
        self.assertEqual(list(original.columns), COLUMNS)
        self.assertEqual(self.widget("selectbox", "Active file").value, SAMPLE)
        self.assertEqual(self.app.session_state["fixed_datasets"], {})
        scan = self.app.session_state["quality_scan_cache"][SAMPLE]
        self.assertEqual(scan["duplicates"], 1)
        self.assertEqual(len(scan["issues"]), 10)
        self.assertEqual(self.issue_keys(scan["issues"]), EXPECTED_ISSUES)
        self.assertEqual(
            scan["issues"].set_index(["Row Number", "Column Name"]).loc[
                (4, "email"), "Current Value"
            ],
            "not-an-email",
        )
        self.app.run()
        self.assert_no_exception()
        assert_frame_equal(self.app.session_state["inspector_datasets"][SAMPLE], original)
        assert_frame_equal(
            self.app.session_state["quality_scan_cache"][SAMPLE]["issues"], scan["issues"]
        )

    def test_inspection_workflow_stays_visible_with_and_without_findings(self):
        self.load_sample()

        def workflow(app):
            return next(item.value for item in app.markdown if 'class="workflow-panel"' in item.value)

        self.assertNotIn("Inspection workflow", [item.label for item in self.app.expander])
        self.assertIn("10 findings · 1 duplicate row", workflow(self.app))
        for stage in ("File loaded", "Inspection complete", "Findings", "Review &amp; fix", "Export"):
            self.assertIn(stage, workflow(self.app))
        self.app.run()
        self.assertIn("10 findings · 1 duplicate row", workflow(self.app))

        clean = AppTest.from_file(str(APP), default_timeout=30).run()
        clean.session_state["inspector_datasets"] = {"Clean data": pd.DataFrame({"id": [1, 2]})}
        clean.session_state["active_dataset"] = "Clean data"
        clean.run()
        self.assert_no_exception(clean)
        self.assertIn("No findings under enabled checks", workflow(clean))
        self.assertIn("workflow-step-clear", workflow(clean))

    def test_issue_report_download_matches_visible_filtered_findings(self):
        # AppTest exposes the download button but not its bytes. Capture the
        # actual argument while still rendering the real Streamlit button.
        downloads = []
        original_download_button = st.download_button

        def capture_download(*args, **kwargs):
            if args and args[0] == "Download issue report":
                downloads.append(kwargs.copy())
            return original_download_button(*args, **kwargs)

        def assert_report(expected_keys):
            self.assert_no_exception()
            report = downloads[-1]
            self.assertEqual(report["file_name"], "Sample messy dataset_issue_report.csv")
            self.assertEqual(report["mime"], "text/csv")
            report_data = report["data"]() if callable(report["data"]) else report["data"]
            self.assertTrue(report_data.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(report["disabled"], not expected_keys)
            csv = pd.read_csv(BytesIO(report_data), keep_default_na=False)
            self.assertEqual(self.issue_keys(csv), expected_keys)
            self.assertEqual(len(csv), len(expected_keys))
            issue_tab = next(tab for tab in self.app.tabs if tab.label == "2 · Issue log")
            if expected_keys:
                self.assertEqual(len(issue_tab.dataframe), 1)
                assert_frame_equal(csv, issue_tab.dataframe[0].value.reset_index(drop=True))
            else:
                self.assertEqual(len(issue_tab.dataframe), 0)
                self.assertTrue(any(
                    "No findings match" in info.value for info in issue_tab.info
                ))

        with patch.object(st, "download_button", side_effect=capture_download):
            self.load_sample()
            self.assertTrue(downloads[-1]["disabled"])
            self.widget("checkbox", "I reviewed all columns for sensitive data").check().run()
            assert_report(EXPECTED_ISSUES)

            self.widget("selectbox", "Filter findings").select("Missing Value").run()
            assert_report({key for key in EXPECTED_ISSUES if key[2] == "Missing Value"})

            self.widget("selectbox", "Filter by column").select("name").run()
            assert_report({(8, "name", "Missing Value"), (33, "name", "Missing Value")})

            # Search trims whitespace and narrows an already type- and
            # column-filtered report.
            self.widget("text_input", "Search findings").set_value("  33  ").run()
            assert_report({(33, "name", "Missing Value")})

            self.widget("text_input", "Search findings").set_value("no such finding").run()
            assert_report(set())

            self.widget("text_input", "Search findings").set_value("").run()
            assert_report({(8, "name", "Missing Value"), (33, "name", "Missing Value")})

    def test_connected_sample_loads_all_files(self):
        self.app.default_timeout = 120
        self.click("Explore sample workspace")
        datasets = self.app.session_state["inspector_datasets"]
        self.assertEqual(
            {name: len(frame) for name, frame in datasets.items()},
            {
                "customers.csv": 5000,
                "orders.xlsx": 20000,
                "products.csv": 1200,
                "support_tickets.xlsx": 6000,
                "web_events.csv": 25000,
            },
        )
        self.assertEqual(self.widget("selectbox", "Active file").value, "customers.csv")

    def test_model_settings_are_session_only_and_sharing_is_opt_in(self):
        self.assertFalse(self.widget("checkbox", "Allow sending the active dataset to this endpoint").value)
        self.widget("text_input", "Chat Completions URL").set_value(
            "https://example.invalid/v1/chat/completions"
        )
        self.widget("text_input", "Model ID").set_value("example-model")
        self.widget("text_input", "API key").set_value("test-session-key")
        self.app.run()
        self.assert_no_exception()
        self.assertFalse(self.app.session_state["assistant_share_dataset"])
        self.load_sample()
        self.click("🧾 Summarize quality issues")
        self.assertTrue(any("Local mode is active" in item.value for item in self.app.info))
        self.assertFalse(any("model request failed" in item.value.lower() for item in self.app.error))
        self.widget("checkbox", "Allow sending the active dataset to this endpoint").check().run()
        self.assert_no_exception()
        self.assertTrue(self.app.session_state["assistant_share_dataset"])
        self.click("Clear model settings")
        self.assertFalse(self.app.session_state["assistant_share_dataset"])
        self.assertEqual(self.app.session_state["assistant_api_url"], "")
        self.assertEqual(self.app.session_state["assistant_model_id"], "")
        self.assertEqual(self.app.session_state["assistant_api_key"], "")

    def test_each_builtin_check_can_be_disabled_and_restored(self):
        self.load_sample()
        categories = {
            "Missing values": {"Missing Value"},
            "Duplicate rows": {"Duplicate Row"},
            "Invalid email formats": {"Invalid Email"},
            "Invalid and inconsistent dates": {"Invalid Date", "Inconsistent Date Format"},
            "Numeric outliers": {"Numeric Outlier"},
        }
        for label, disabled_types in categories.items():
            with self.subTest(label=label):
                self.widget("checkbox", label).uncheck().run()
                self.assert_no_exception()
                issues = self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]
                self.assertTrue(disabled_types.isdisjoint(set(issues["Issue Type"])))
                if label == "Duplicate rows":
                    self.assertEqual(self.app.session_state["quality_scan_cache"][SAMPLE]["duplicates"], 0)
                self.widget("checkbox", label).check().run()
                self.assert_no_exception()
                self.assertEqual(
                    self.issue_keys(self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]),
                    EXPECTED_ISSUES,
                )

    def test_custom_rule_add_edit_delete_and_fixed_preview_rescan(self):
        data = self.load_sample()
        self.widget("selectbox", "Rule column").select("age")
        self.widget("selectbox", "Rule type").select("Minimum number")
        self.widget("text_input", "Expected value").set_value("30")
        self.click("Add rule")
        issues = self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]
        custom = issues[issues["Issue Type"] == "Custom: Minimum number"]
        expected_rows = {
            index + 1 for index, value in enumerate(data["age"])
            if value is not None and value == value and float(value) < 30
        }
        self.assertEqual(set(custom["Row Number"]), expected_rows)
        self.click("Apply selected fixes")
        self.assertTrue(any(
            self.app.session_state["review_scan_cache"][SAMPLE]["issues"]["Issue Type"]
            == "Custom: Minimum number"
        ))
        self.widget("selectbox", "Rule to edit").select(1).run()
        self.assert_no_exception()
        self.widget("text_input", "Expected value").set_value("100")
        self.click("Save changes")
        updated = self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]
        self.assertGreater(
            len(updated[updated["Issue Type"] == "Custom: Minimum number"]), len(custom)
        )
        review_updated = self.app.session_state["review_scan_cache"][SAMPLE]["issues"]
        self.assertGreater(
            len(review_updated[review_updated["Issue Type"] == "Custom: Minimum number"]),
            len(custom),
        )
        self.click("Delete selected rule")
        self.assertNotIn(
            "Custom: Minimum number",
            set(self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]["Issue Type"]),
        )
        self.assertNotIn(
            "Custom: Minimum number",
            set(self.app.session_state["review_scan_cache"][SAMPLE]["issues"]["Issue Type"]),
        )

    def test_custom_rule_rejects_invalid_numeric_limit(self):
        self.load_sample()
        self.widget("selectbox", "Rule column").select("age")
        self.widget("selectbox", "Rule type").select("Minimum number")
        self.widget("text_input", "Expected value").set_value("not-a-number")
        self.click("Add rule")
        self.assertTrue(any("finite number" in error.value for error in self.app.error))
        self.assertEqual(
            self.issue_keys(self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]),
            EXPECTED_ISSUES,
        )

    def test_custom_text_allowed_values_and_maximum_rules(self):
        data = self.load_sample()
        cases = [
            ("name", "Must contain", "a", lambda value: "a" not in str(value).strip().lower()),
            ("region", "Allowed values", "North, South", lambda value: str(value).strip() not in {"North", "South"}),
            ("age", "Maximum number", "40", lambda value: float(value) > 40),
        ]
        for column, kind, expected, is_invalid in cases:
            with self.subTest(kind=kind):
                self.widget("selectbox", "Rule column").select(column)
                self.widget("selectbox", "Rule type").select(kind)
                self.widget("text_input", "Expected value").set_value(expected)
                self.click("Add rule")
                issues = self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]
                observed = set(issues.loc[issues["Issue Type"] == f"Custom: {kind}", "Row Number"])
                expected_rows = {
                    index + 1 for index, value in enumerate(data[column])
                    if value is not None and value == value
                    and str(value).strip() and is_invalid(value)
                }
                self.assertEqual(observed, expected_rows)

    def test_assistant_reports_duplicate_check_disabled(self):
        self.load_sample()
        self.widget("checkbox", "Duplicate rows").uncheck().run()
        self.assert_no_exception()
        self.click("🔁 How many rows are duplicates?")
        self.assertTrue(any(
            "duplicate check is turned off" in item.value.lower()
            for item in self.app.markdown
        ))

    def test_default_fixes_change_only_safe_cells_and_one_duplicate(self):
        original = self.load_sample().copy(deep=True)
        for label in FIX_LABELS:
            self.assertTrue(self.widget("checkbox", label).value)
        self.click("Apply selected fixes")
        fixed = self.app.session_state["fixed_datasets"][SAMPLE]
        # Independent expected result, not computed by the app's cleaning helper.
        expected = original.iloc[:49].copy()
        expected.loc[32, "name"] = ""
        expected.loc[15, "annual_spend"] = original.iloc[:49]["annual_spend"].median()
        expected.loc[12, "signup_date"] = "2024-03-18"
        assert_frame_equal(fixed, expected)
        assert_frame_equal(self.app.session_state["inspector_datasets"][SAMPLE], original)
        self.assertEqual(fixed.shape, (49, 8))
        self.assertTrue(self.widget("toggle", "Show fixed preview").value)
        remaining = self.app.session_state["review_scan_cache"][SAMPLE]["issues"]
        resolved = {
            (50, "Entire row", "Duplicate Row"),
            (16, "annual_spend", "Missing Value"),
            (13, "signup_date", "Inconsistent Date Format"),
        }
        self.assertEqual(len(remaining), 7)
        self.assertEqual(self.issue_keys(remaining), EXPECTED_ISSUES - resolved)
        metrics = {metric.label: metric.value for metric in self.app.metric}
        self.assertEqual(metrics["Rows removed"], "1")
        self.assertEqual(metrics["Findings resolved"], "3")
        self.assertEqual(metrics["Needs manual review"], "7")
        # Switching previews and applying twice must not mutate the source or drift.
        self.widget("toggle", "Show fixed preview").set_value(False).run()
        self.assert_no_exception()
        self.assertTrue(any("Original data: 50 rows" in item.value for item in self.app.info))
        self.click("Apply selected fixes")
        assert_frame_equal(self.app.session_state["fixed_datasets"][SAMPLE], expected)
        assert_frame_equal(self.app.session_state["inspector_datasets"][SAMPLE], original)

    def test_fix_options_are_honored_and_no_selection_disables_apply(self):
        original = self.load_sample().copy(deep=True)
        for label in FIX_LABELS:
            self.widget("checkbox", label).uncheck()
        self.app.run()
        self.assert_no_exception()
        self.assertTrue(self.widget("button", "Apply selected fixes").disabled)
        self.assertEqual(self.app.session_state["fixed_datasets"], {})
        # Exercise every checkbox in isolation, including preserving duplicates
        # when that option is off and replacing an earlier fixed copy.
        for label in FIX_LABELS:
            with self.subTest(fix=label):
                for option in FIX_LABELS:
                    self.widget("checkbox", option).set_value(option == label)
                self.app.run()
                self.assert_no_exception()
                self.click("Apply selected fixes")
                expected = original.copy(deep=True)
                if label == FIX_LABELS[0]:
                    expected = expected.iloc[:49].copy()
                elif label == FIX_LABELS[1]:
                    expected.loc[32, "name"] = ""
                elif label == FIX_LABELS[2]:
                    expected.loc[15, "annual_spend"] = original["annual_spend"].median()
                else:
                    expected.loc[12, "signup_date"] = "2024-03-18"
                assert_frame_equal(self.app.session_state["fixed_datasets"][SAMPLE], expected)
                assert_frame_equal(self.app.session_state["inspector_datasets"][SAMPLE], original)

    def test_reload_clears_fixes_and_new_session_has_no_dataset(self):
        original = self.load_sample().copy(deep=True)
        self.click("Apply selected fixes")
        self.assertIn(SAMPLE, self.app.session_state["review_scan_cache"])
        self.load_sample()
        assert_frame_equal(self.app.session_state["inspector_datasets"][SAMPLE], original)
        self.assertEqual(self.app.session_state["fixed_datasets"], {})
        self.assertEqual(self.app.session_state["review_scan_cache"], {})
        self.assertEqual(
            self.issue_keys(self.app.session_state["quality_scan_cache"][SAMPLE]["issues"]),
            EXPECTED_ISSUES,
        )
        fresh = AppTest.from_file(str(APP), default_timeout=30).run()
        self.assert_no_exception(fresh)
        self.assertNotIn("inspector_datasets", fresh.session_state)
        self.assertNotIn("fixed_datasets", fresh.session_state)


if __name__ == "__main__":
    unittest.main()
