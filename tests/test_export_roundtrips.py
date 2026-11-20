"""Round-trip contracts for the real app functions, without running its UI.

Run with: python -m unittest discover -s tests -v

CSV/Excel do not preserve pandas dtypes or distinguish empty strings from null
cells. Comparisons normalize only those documented storage differences; numeric
values, column/row order, and nonempty text must survive unchanged.
"""

import ast
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from pandas.testing import assert_frame_equal


ROOT = Path(__file__).resolve().parents[1]


def load_export_functions():
    """Compile actual function bodies and initial constants, not UI statements."""
    path = ROOT / "app.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = {
        "is_missing", "parse_date", "parse_numeric_series", "infer_column_rules",
        "clean_data", "standardize_date_value", "serialize_data_file",
        "read_data_file", "read_uploaded_file", "connected_sample_archive",
        "build_cleaned_batch_archive",
    }
    nodes = []
    before_functions = True
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            before_functions = False
            if node.name in names:
                nodes.append(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            nodes.append(node)
        elif before_functions and isinstance(node, ast.Assign):
            nodes.append(node)
    namespace = {"__file__": str(path)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    assert names <= namespace.keys(), "An export helper was removed or renamed"
    return SimpleNamespace(**namespace)


APP = load_export_functions()
FORMATS = (".csv", ".xlsx")


def storage_values(frame):
    # Empty text and null cells both reload as missing in the current readers.
    return frame.reset_index(drop=True).map(
        lambda value: np.nan
        if (isinstance(value, str) and value == "") or pd.isna(value)
        else value
    )


class ExportRoundTripTests(unittest.TestCase):
    def assertStoredEqual(self, actual, expected):
        assert_frame_equal(
            storage_values(actual), storage_values(expected),
            check_dtype=False, check_exact=False, rtol=1e-14, atol=1e-14,
        )
        self.assertEqual(list(actual.columns), list(expected.columns))
        self.assertEqual(actual.shape, expected.shape)

    def fixture(self):
        data = pd.DataFrame({
            "id": [101, 102, 103, 104, 101],
            "name": ['  Zoë, "QA"  ', "   ", None, "東京\nsecond line",
                     '  Zoë, "QA"  '],
            "amount": [1.25, np.nan, -4.5, 1000.125, 1.25],
            "unfilled": [np.nan] * 5,
            "date": ["2024/01/20", "not-a-date", None, "03/04/2024", "2024/01/20"],
            "active": [True, False, True, False, True],
        }, index=[9, 12, 30, 44, 90])
        return data

    def test_cleaned_exports_have_explicit_expected_values(self):
        original = self.fixture()
        snapshot = original.copy(deep=True)
        cleaned = APP.clean_data(original, numeric_columns={"amount", "unfilled"})
        expected = pd.DataFrame({
            "id": [101, 102, 103, 104],
            "name": ['Zoë, "QA"', "", None, "東京\nsecond line"],
            "amount": [1.25, 1.25, -4.5, 1000.125],
            "unfilled": [np.nan] * 4,
            "date": ["2024/01/20", "not-a-date", None, "03/04/2024"],
            "active": [True, False, True, False],
        })
        self.assertStoredEqual(cleaned, expected)
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("input" + suffix, cleaned)
                self.assertStoredEqual(APP.read_data_file("output" + suffix, content), expected)
        assert_frame_equal(original, snapshot)

    def test_raw_loads_preserve_whitespace_duplicates_and_missing_cells(self):
        original = self.fixture()
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("raw" + suffix, original)
                loaded = APP.read_data_file("raw" + suffix.upper(), content)
                self.assertStoredEqual(loaded, original)
                self.assertEqual(loaded.loc[0, "name"], '  Zoë, "QA"  ')
                self.assertEqual(loaded.duplicated().sum(), 1)
                self.assertTrue(pd.isna(loaded.loc[1, "amount"]))

    def test_disabled_fixes_survive_export(self):
        original = self.fixture()
        cleaned = APP.clean_data(
            original, drop_duplicates=False, trim_whitespace=False,
            fill_numeric_missing=False, standardize_dates=False,
        )
        assert_frame_equal(cleaned, original)
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("unchanged" + suffix, cleaned)
                self.assertStoredEqual(APP.read_data_file("out" + suffix, content), original)

    def test_export_format_metadata_and_no_index_column(self):
        frame = pd.DataFrame({"label": ["café"], "value": [2]}, index=[45])
        csv, mime, suffix = APP.serialize_data_file("REPORT.CSV", frame)
        self.assertEqual((mime, suffix), ("text/csv", ".csv"))
        self.assertTrue(csv.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(csv.decode("utf-8-sig"), "label,value\ncafé,2\n")
        xlsx, mime, suffix = APP.serialize_data_file("REPORT.XLSX", frame)
        self.assertEqual((mime, suffix), (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx",
        ))
        self.assertTrue(xlsx.startswith(b"PK"))
        book = load_workbook(BytesIO(xlsx), read_only=True)
        try:
            self.assertEqual(book.sheetnames, ["Fixed data"])
            self.assertEqual(list(book.active.values), [("label", "value"), ("café", 2)])
        finally:
            book.close()

    def test_sample_label_defaults_to_csv(self):
        content, mime, suffix = APP.serialize_data_file("Sample messy dataset", self.fixture())
        self.assertEqual((mime, suffix), ("text/csv", ".csv"))
        self.assertStoredEqual(APP.read_data_file("sample.csv", content), self.fixture())

    def test_uploaded_file_uses_complete_bytes_not_current_cursor(self):
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("file" + suffix, self.fixture())
                uploaded = BytesIO(content)
                uploaded.name = "file" + suffix
                uploaded.seek(0, 2)
                self.assertStoredEqual(APP.read_uploaded_file(uploaded), self.fixture())

    def test_header_only_files_round_trip(self):
        frame = pd.DataFrame(columns=["name", "amount"])
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("empty" + suffix, frame)
                self.assertStoredEqual(APP.read_data_file("empty" + suffix, content), frame)

    def test_numeric_values_are_not_rounded_or_changed_to_missing(self):
        frame = pd.DataFrame({
            "integer": [0, -12345, 2147483647, 999999999999999],
            "decimal": [0.0, -0.125, 123456.7890123, 1.25e-9],
            "formatted": ["$1,234.50", "(25.00)", "€7.50", "bad-number"],
        })
        for suffix in FORMATS:
            with self.subTest(format=suffix):
                content, _, _ = APP.serialize_data_file("numbers" + suffix, frame)
                loaded = APP.read_data_file("numbers" + suffix, content)
                self.assertStoredEqual(loaded, frame)
                self.assertFalse(loaded.isna().any().any())
                self.assertEqual(loaded["integer"].tolist(), frame["integer"].tolist())

    def test_invalid_inputs_raise_clear_errors(self):
        cases = [
            ("empty.csv", b"", pd.errors.EmptyDataError, "No columns"),
            ("bad.csv", b"a,b\n1,2\n3,4,5\n", pd.errors.ParserError, "Expected"),
            ("quote.csv", b'a,b\n"unfinished,2', pd.errors.ParserError, "EOF"),
            ("encoding.csv", b"a\n\xff", UnicodeDecodeError, "decode"),
            ("broken.xlsx", b"not a workbook", BadZipFile, "zip"),
            ("empty.xlsx", b"", BadZipFile, "zip"),
            ("wrong.xlsx", b"a,b\n1,2\n", BadZipFile, "zip"),
        ]
        for filename, content, error, message in cases:
            with self.subTest(filename=filename):
                with self.assertRaisesRegex(error, message):
                    APP.read_data_file(filename, content)
        content, _, _ = APP.serialize_data_file("valid.xlsx", self.fixture())
        with self.assertRaisesRegex(BadZipFile, "zip"):
            APP.read_data_file("truncated.xlsx", content[:40])


class SampleAndBatchExportTests(unittest.TestCase):
    assertStoredEqual = ExportRoundTripTests.assertStoredEqual

    @classmethod
    def setUpClass(cls):
        cls.samples = {
            name: APP.read_data_file(name, (ROOT / "sample_data" / name).read_bytes())
            for name in APP.CONNECTED_SAMPLE_FILES
        }

    def test_every_sample_loads_and_cleaned_export_round_trips(self):
        for name, original in self.samples.items():
            with self.subTest(sample=name):
                self.assertGreater(len(original), 0)
                snapshot = original.copy(deep=True)
                cleaned = APP.clean_data(original)
                self.assertEqual(len(cleaned), len(original.drop_duplicates()))
                # Exercise both export formats, not just each sample's source format.
                for suffix in FORMATS:
                    with self.subTest(export=suffix):
                        content, _, actual_suffix = APP.serialize_data_file("cleaned" + suffix, cleaned)
                        self.assertEqual(actual_suffix, suffix)
                        loaded = APP.read_data_file("cleaned" + suffix, content)
                        self.assertStoredEqual(loaded, cleaned)
                assert_frame_equal(original, snapshot)

    def test_sample_pack_contains_exact_original_files(self):
        with ZipFile(BytesIO(APP.connected_sample_archive())) as archive:
            self.assertIsNone(archive.testzip())
            expected_files = [*APP.CONNECTED_SAMPLE_FILES, "ecb_fx_manifest.json"]
            self.assertEqual(archive.namelist(), expected_files)
            for name in APP.CONNECTED_SAMPLE_FILES:
                self.assertEqual(archive.read(name), (ROOT / "sample_data" / name).read_bytes())
            self.assertEqual(
                archive.read("ecb_fx_manifest.json"),
                (ROOT / "sample_data" / "ecb_fx_manifest.json").read_bytes(),
            )

    def test_batch_contains_exact_supplied_file_versions(self):
        progress = []
        snapshots = {name: frame.copy(deep=True) for name, frame in self.samples.items()}
        payload = APP.build_cleaned_batch_archive(
            self.samples, lambda fraction, text: progress.append((fraction, text)),
        )
        expected_names = [
            (name[:-4] if name.lower().endswith(".csv") else name) + "_preview.csv"
            for name in self.samples
        ]
        with ZipFile(BytesIO(payload)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.namelist(), expected_names)
            for (name, original), entry in zip(self.samples.items(), expected_names):
                self.assertStoredEqual(
                    APP.read_data_file(entry, archive.read(entry)),
                    original,
                )
                assert_frame_equal(original, snapshots[name])
        self.assertEqual(len(progress), len(self.samples))
        for index, ((fraction, text), name) in enumerate(zip(progress, self.samples), 1):
            self.assertEqual(fraction, index / len(self.samples))
            self.assertEqual(text, f"Prepared {name} ({index} of {len(self.samples)})")

    def test_small_batch_has_explicit_values_and_safe_entry_names(self):
        frame = pd.DataFrame({"name": [" A ", " A ", " B "], "amount": [2.5, 2.5, np.nan]})
        snapshot = frame.copy(deep=True)
        expected = frame.copy(deep=True)
        payload = APP.build_cleaned_batch_archive({"folder/report 1.xlsx": frame})
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(archive.namelist(), ["folder_report 1.xlsx_preview.csv"])
            entry = archive.namelist()[0]
            self.assertStoredEqual(APP.read_data_file(entry, archive.read(entry)), expected)
        assert_frame_equal(frame, snapshot)

    def test_batch_preserves_unicode_and_avoids_name_collisions(self):
        frame = pd.DataFrame({"Rows": ["Upload", "العربية"]})
        payload = APP.build_cleaned_batch_archive({"بيانات.csv": frame, "بيانات.CSV": frame})
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(archive.namelist(), ["بيانات_preview.csv", "بيانات_preview (2).csv"])
            for name in archive.namelist():
                assert_frame_equal(pd.read_csv(BytesIO(archive.read(name))), frame)

    def test_empty_batch_is_valid_empty_zip_without_progress(self):
        progress = []
        payload = APP.build_cleaned_batch_archive({}, lambda *args: progress.append(args))
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(archive.namelist(), [])
            self.assertIsNone(archive.testzip())
        self.assertEqual(progress, [])

    def test_batch_failure_does_not_return_partial_archive_or_mutate_input(self):
        frame = pd.DataFrame({"name": [" A "]})
        snapshot = frame.copy(deep=True)
        with self.assertRaises(AttributeError):
            APP.build_cleaned_batch_archive({"valid.csv": frame, "invalid.csv": None})
        assert_frame_equal(frame, snapshot)


if __name__ == "__main__":
    unittest.main()
