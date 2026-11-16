"""End-to-end quick-sample regressions against the real Streamlit script."""

from pathlib import Path
import unittest

from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest


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
        self.click("Explore with 50-row quick sample")
        return self.app.session_state["inspector_datasets"][SAMPLE]

    def issue_keys(self, issues):
        self.assertEqual(
            list(issues.columns),
            ["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"],
        )
        return set(issues.iloc[:, :3].itertuples(index=False, name=None))

    def test_initial_screen_and_sample_scan_survive_rerun(self):
        self.assertNotIn("inspector_datasets", self.app.session_state)
        self.assertFalse(self.widget("button", "Explore with 50-row quick sample").disabled)
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
