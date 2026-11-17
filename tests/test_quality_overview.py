"""Focused exact-aggregation and value-free chart tests; no app/database setup."""
import json
import unittest

import pandas as pd
from streamlit.testing.v1 import AppTest

from quality_overview import (
    aggregate_quality, build_column_findings, build_control_findings,
    build_multiplicity, build_row_coverage, build_row_ranges, build_type_heatmap,
    plot_label,
)


FIELDS = ["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"]


def findings(*records):
    return pd.DataFrame([(*r, "PRIVATE-CELL", "PRIVATE-SUGGESTION") for r in records], columns=FIELDS)


class QualityOverviewTests(unittest.TestCase):
    def setUp(self):
        self.data = pd.DataFrame({"Entire row": range(7), "email": ["x"] * 7, "amount": range(7)})

    def test_unique_rows_not_issue_count_or_cells(self):
        issues = findings((1, "email", "Invalid Email"), (1, "amount", "Numeric Outlier"),
                          (2, "Entire row", "Duplicate Row"))
        result = aggregate_quality(self.data, issues, {"email", "outliers", "duplicates"},
                                   email_columns=["email"], numeric_columns=["amount"])
        self.assertEqual((result["findings"], result["affected"], result["unflagged"]), (3, 2, 5))
        self.assertEqual(sum(x["rows"] for x in result["multiplicity"]), 2)
        self.assertEqual(result["multiplicity"][:2], [{"findings": 1, "rows": 1}, {"findings": 2, "rows": 1}])

    def test_mixed_controls_and_same_kind_rules_are_aggregated(self):
        rules = [{"column": "email", "kind": "Must contain", "expected": "PRIVATE-EXPECTED"},
                 {"column": "Entire row", "kind": "Must contain", "expected": "OTHER-SECRET"},
                 {"column": "amount", "kind": "Maximum number", "expected": "99"}]
        issues = findings((1, "email", "Custom: Must contain"), (3, "Entire row", "Custom: Must contain"),
                          (4, "email", "Invalid Email"), (5, "Entire row", "Missing Value"))
        result = aggregate_quality(self.data, issues, {"email", "missing", "outliers"}, rules,
                                   email_columns=["email"], numeric_columns=["amount"])
        controls = {c["key"]: c for c in result["controls"]}
        self.assertEqual(controls["custom:Must contain"]["count"], 2)
        self.assertEqual(controls["custom:Must contain"]["rules"], 2)
        self.assertEqual(controls["custom:Must contain"]["columns"], 2)
        self.assertTrue(controls["custom:Maximum number"]["assessed"])
        self.assertEqual(controls["custom:Maximum number"]["count"], 0)
        self.assertFalse(controls["duplicates"]["assessed"])
        self.assertTrue(controls["outliers"]["assessed"])
        self.assertEqual(controls["outliers"]["count"], 0)
        self.assertEqual(sum(c["count"] for c in result["controls"]), len(issues))
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("OTHER-SECRET", json.dumps(result))

    def test_duplicate_scope_does_not_merge_literal_entire_row_column(self):
        result = aggregate_quality(self.data, findings(
            (1, "Entire row", "Missing Value"), (2, "Entire row", "Duplicate Row")
        ), {"missing", "duplicates"})
        fields = {c["id"]: c for c in result["columns"]}
        self.assertEqual(fields["column:0"]["count"], 1)
        self.assertEqual(fields["whole-row"]["count"], 1)
        self.assertEqual(sum(map(sum, result["heat"])), 2)

    def test_all_controls_off_and_custom_only(self):
        off = aggregate_quality(self.data, findings(), set())
        self.assertFalse(off["assessed"])
        self.assertEqual(off["affected"], 0)
        self.assertTrue(all(c["status"] == "Disabled · not assessed" for c in off["controls"]))
        custom = aggregate_quality(self.data, findings(), set(),
                                   [{"column": "amount", "kind": "Minimum number", "expected": "0"}])
        self.assertTrue(custom["assessed"])
        self.assertTrue(custom["controls"][-1]["assessed"])
        self.assertEqual(custom["controls"][-1]["count"], 0)

    def test_no_selected_columns_and_empty_data_are_not_passed(self):
        empty_scope = aggregate_quality(self.data, findings(), {"email"})
        self.assertFalse(empty_scope["assessed"])
        self.assertEqual(empty_scope["controls"][2]["status"], "No selected columns · not assessed")
        empty = aggregate_quality(self.data.head(0), findings(), {"missing", "duplicates"})
        self.assertFalse(empty["assessed"])
        self.assertEqual(empty["rows"], 0)
        self.assertEqual(empty["ranges"], [])
        self.assertEqual(len(build_row_coverage(empty).data), 0)

    def test_bounded_row_ranges_preserve_findings_and_cover_last_row(self):
        data = pd.DataFrame({"x": range(103)})
        issues = findings(*[(i, "x", "Missing Value") for i in range(1, 104)],
                          (1, "x", "Invalid Email"), (103, "Entire row", "Duplicate Row"))
        result = aggregate_quality(data, issues, {"missing", "email", "duplicates"},
                                   email_columns=["x"], max_ranges=11)
        self.assertEqual(len(result["ranges"]), 11)
        self.assertEqual(result["ranges"][0]["start"], 1)
        self.assertEqual(result["ranges"][-1]["end"], 103)
        self.assertEqual(sum(r["count"] for r in result["ranges"]), len(issues))
        for previous, current in zip(result["ranges"], result["ranges"][1:]):
            self.assertEqual(previous["end"] + 1, current["start"])

    def test_unpositioned_findings_stay_in_totals_not_affected_rows(self):
        result = aggregate_quality(self.data, findings(
            (1, "email", "Invalid Email"), (0, "email", "Invalid Email"),
            (8, "email", "Invalid Email"), (1.5, "email", "Invalid Email")
        ), {"email"}, email_columns=["email"])
        self.assertEqual(result["affected"], 1)
        self.assertEqual(result["unpositioned"], 3)
        self.assertEqual(sum(r["count"] for r in result["ranges"]) + result["unpositioned"], 4)

    def test_all_columns_retained_and_chart_labels_literal_no_private_values(self):
        name = '<b>Findings</b> %{x} & "name"'
        data = pd.DataFrame({name: [1], **{f"field{i}": [1] for i in range(27)}})
        result = aggregate_quality(data, findings((1, name, "Missing Value")), {"missing"})
        self.assertEqual(len(result["columns"]), 28)
        indices = list(range(len(result["columns"])))
        figures = [build_row_coverage(result), build_control_findings(result),
                   build_column_findings(result, indices), build_type_heatmap(result, indices),
                   build_multiplicity(result), build_row_ranges(result)]
        for figure in figures:
            encoded = figure.to_json()
            self.assertNotIn("PRIVATE-CELL", encoded)
            self.assertNotIn("PRIVATE-SUGGESTION", encoded)
        self.assertIn("&lt;b&gt;", plot_label(name))
        self.assertIn("&#37;{x}", plot_label(name))
        self.assertEqual(result["columns"][0]["label"], name)

    def test_many_column_window_is_navigable_and_contains_only_charts(self):
        app = AppTest.from_string("""
import pandas as pd
from quality_overview import render_quality_overview
data = pd.DataFrame({f"field{i}": [1, 2] for i in range(27)})
issues = pd.DataFrame(columns=["Row Number", "Column Name", "Issue Type"])
render_quality_overview(data, issues, {"missing"}, [], [], [], [], 1.5, "window-test")
""").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get("plotly_chart")), 6)
        self.assertEqual(app.selectbox[0].options, ["Columns 1–10 of 27", "Columns 11–20 of 27", "Columns 21–27 of 27"])
        app.selectbox[0].select_index(2).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.dataframe)
        charts = app.get("plotly_chart")
        column_chart = json.loads(charts[2].proto.spec)
        self.assertEqual(column_chart["data"][0]["y"], [f"column:{i}" for i in range(20, 27)])


if __name__ == "__main__":
    unittest.main()
