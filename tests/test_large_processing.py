"""Regression checks for large-file quality scanning and progress."""
import ast
from io import BytesIO
from pathlib import Path
import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from quality_large import scan_large_data
from sample_fixtures import make_sample_data


ROOT = Path(__file__).resolve().parents[1]


def load_helpers():
    path = ROOT / "app.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    functions = {
        "is_missing", "display_value", "parse_date",
        "date_shape", "parse_numeric_series", "scan_data", "read_uploaded_file",
    }
    constants = {"EMAIL_PATTERN", "DATE_FORMATS", "DATE_SHAPES", "ISSUE_COLUMNS"}
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        or isinstance(node, ast.FunctionDef) and node.name in functions
        or isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in constants
            for target in node.targets
        )
    ]
    namespace = {"__file__": str(path)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


HELPERS = load_helpers()


class LargeProcessingTests(unittest.TestCase):
    def fast_scan(self, data, emails, dates, numeric, checks, rules=None, callback=None):
        return scan_large_data(
            data, emails, dates, numeric, 1.5, callback, checks, rules or [],
            HELPERS["EMAIL_PATTERN"], HELPERS["parse_date"], HELPERS["date_shape"],
            HELPERS["parse_numeric_series"], HELPERS["display_value"], HELPERS["ISSUE_COLUMNS"],
        )

    def test_chunked_checks_match_existing_results(self):
        data = make_sample_data()
        checks = {"missing", "duplicates", "email", "date", "outliers"}
        rules = [
            {"column": "name", "kind": "Must contain", "expected": "a"},
            {"column": "annual_spend", "kind": "Minimum number", "expected": "200"},
        ]
        args = (data, {"email"}, {"signup_date"}, {"annual_spend"})
        expected = HELPERS["scan_data"](*args, enabled_checks=checks, custom_rules=rules)
        actual = self.fast_scan(*args, checks, rules)
        self.assertEqual(expected[1], actual[1])
        assert_frame_equal(expected[0], actual[0], check_dtype=False)

    def test_checks_find_duplicates_and_outliers_across_chunks(self):
        rows = 100_005
        data = pd.DataFrame({
            "id": np.arange(rows),
            "email": ["person@example.com"] * rows,
            "amount": np.ones(rows),
        })
        data.loc[100_001, "email"] = "broken"
        data.loc[100_002, "amount"] = 999
        data.loc[100_004] = data.loc[1]
        progress = []
        issues, duplicates = self.fast_scan(
            data, {"email"}, set(), {"amount"},
            {"missing", "duplicates", "email", "outliers"},
            callback=lambda fraction, message: progress.append((fraction, message)),
        )
        self.assertEqual(duplicates, 1)
        self.assertEqual(set(issues["Issue Type"]), {"Duplicate Row", "Invalid Email", "Numeric Outlier"})
        self.assertEqual(set(issues["Row Number"]), {100_002, 100_003, 100_005})
        self.assertEqual(progress[-1][0], 1.0)
        self.assertEqual([p[0] for p in progress], sorted(p[0] for p in progress))

    def test_mixed_values_and_custom_rules_match_existing_checks(self):
        data = pd.DataFrame({
            "email": ["ok@example.com", "bad", "", None, " two@example.com "],
            "date": ["2024-01-03", "01/04/2024", "impossible", " ", None],
            "amount": ["$1,000", "(2)", "10", None, "not numeric"],
        })
        checks = {"missing", "duplicates", "email", "date", "outliers"}
        rules = [
            {"column": "email", "kind": "Allowed values", "expected": "ok@example.com,bad"},
            {"column": "amount", "kind": "Maximum number", "expected": "50"},
        ]
        args = (data, {"email"}, {"date"}, {"amount"})
        expected = HELPERS["scan_data"](*args, enabled_checks=checks, custom_rules=rules)
        actual = self.fast_scan(*args, checks, rules)
        self.assertEqual(expected[1], actual[1])
        assert_frame_equal(expected[0], actual[0], check_dtype=False)

    def test_upload_reports_real_csv_read_progress(self):
        uploaded = BytesIO(b"value\n" + b"1234567890\n" * 500_000)
        uploaded.name = "large.csv"
        progress = []
        result = HELPERS["read_uploaded_file"](uploaded, progress.append)
        self.assertEqual(len(result), 500_000)
        self.assertTrue(progress)
        self.assertEqual(progress[-1], 1.0)
        self.assertEqual(progress, sorted(progress))

    def test_upload_limit_is_500_mb(self):
        self.assertIn("maxUploadSize = 500", (ROOT / ".streamlit/config.toml").read_text())


if __name__ == "__main__":
    unittest.main()
