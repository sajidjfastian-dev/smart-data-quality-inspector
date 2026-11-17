import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from data_insights import category_counts, date_counts, insight_sample, numeric_relationship, numeric_summary
from streamlit.testing.v1 import AppTest
from sample_fixtures import load_test_fixture


class DataInsightsTests(unittest.TestCase):
    def test_even_sample_covers_both_ends_and_is_disclosed(self):
        series = pd.Series(range(250_000))
        sample, sampled = insight_sample(series)
        self.assertTrue(sampled)
        self.assertEqual(len(sample), 100_000)
        self.assertEqual((sample.iloc[0], sample.iloc[-1]), (0, 249_999))
        small, sampled = insight_sample(series.head(2))
        self.assertFalse(sampled)
        self.assertEqual(len(small), 2)

    def test_category_counts_exclude_blanks_and_keep_exact_values(self):
        counts = category_counts(pd.Series([" A ", "A", "", None, "B"]))
        self.assertEqual(counts.to_dict("records"), [{"Value": "A", "Rows": 2}, {"Value": "B", "Rows": 1}])
        self.assertTrue(category_counts(pd.Series([None, " "])).empty)

    def test_numeric_summary_excludes_nonfinite_values(self):
        def parser(series):
            return pd.to_numeric(series, errors="coerce")

        summary = numeric_summary(pd.Series([1, 2, None, np.inf, "bad"]), parser)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["mean"], 1.5)
        self.assertEqual(summary["median"], 1.5)
        self.assertEqual(int(summary["counts"].sum()), 2)
        self.assertEqual(numeric_summary(pd.Series(["bad", None]), parser), {"count": 0})

    def test_dates_group_parseable_values_without_treating_numbers_as_dates(self):
        series = pd.Series(["2024-01-10", "2024-01-20", "03/04/2024", "bad", None, 1700000000])
        counts, valid = date_counts(series)
        self.assertEqual(valid, 3)
        self.assertEqual(counts["Month"].dt.strftime("%Y-%m").tolist(), ["2024-01", "2024-03"])
        self.assertEqual(counts["Rows"].tolist(), [2, 1])
        empty, valid = date_counts(pd.Series([None, "bad", 123]))
        self.assertTrue(empty.empty)
        self.assertEqual(valid, 0)

    def test_relationship_uses_valid_pairs_and_limits_chart_points(self):
        data = pd.DataFrame({"a": range(5_000), "b": np.arange(5_000) * 2})
        result = numeric_relationship(data, "a", "b", lambda series: pd.to_numeric(series, errors="coerce"))
        self.assertEqual(result["pairs"], 5_000)
        self.assertAlmostEqual(result["correlation"], 1.0)
        self.assertEqual(len(result["points"]), 2_000)
        self.assertTrue(result["points_sampled"])


class DataInsightsUiTests(unittest.TestCase):
    def test_sample_navigation_and_insight_sections(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
        load_test_fixture(app)
        next(item for item in app.checkbox if item.label == "I reviewed all columns for sensitive data").check().run()
        app.session_state["dashboard_tabs"] = "6 · Data insights"
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Your fields at a glance" in item.value for item in app.subheader))
        insight_key = next(key for key in app.session_state._state.filtered_state if key.startswith("insight_views_"))
        for section, heading in [
            ("Numeric", "Distribution"),
            ("Categories", "Most common values"),
            ("Dates", "Records over time"),
            ("Relationships", "How these columns move together"),
        ]:
            app.session_state[insight_key] = section
            app.run()
            self.assertFalse(app.exception, f"{section} raised an exception")
            self.assertTrue(any(heading in item.value for item in app.subheader), section)


if __name__ == "__main__":
    unittest.main()
