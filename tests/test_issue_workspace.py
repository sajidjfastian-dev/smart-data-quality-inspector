"""Focused pagination and coverage checks for the 360-degree explorer."""
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


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


class IssueWorkspaceTests(unittest.TestCase):
    def test_report_is_not_serialized_during_render_or_filter(self):
        with patch("pandas.DataFrame.to_csv", side_effect=AssertionError("Eager CSV serialization")) as export:
            app = AppTest.from_function(issue_fixture).run()
            self.assertFalse(app.exception)
            app.text_input(key="test_search").set_value("Review").run()
            self.assertFalse(app.exception)
            export.assert_not_called()

    def test_all_findings_accessible(self):
        app = AppTest.from_function(issue_fixture).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 100)
        app.number_input(key="test_page").set_value(3).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.dataframe[0].value), 50)
        self.assertEqual(app.dataframe[0].value.iloc[-1]["Row Number"], 250)

    def test_clean_file_and_uninspected_coverage(self):
        app = AppTest.from_function(clean_fixture).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value["File"].tolist(), ["clean.csv", "other.csv"])
        self.assertIn("Not inspected", app.dataframe[0].value["Findings"].tolist())


if __name__ == "__main__":
    unittest.main()
