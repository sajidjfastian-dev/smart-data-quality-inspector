"""Focused approval, lineage and mocked delivery regressions."""
import unittest
from unittest.mock import Mock
import pandas as pd
from review_approval import (
    ApprovalRequired, approve, change_index, guarded_push, invalidate,
    is_approved, return_for_revision, sync_context,
)
from correction_workbench import build_changes


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.original = pd.DataFrame({"name": [" Alice ", "Bob", " Alice "], "amount": [1., None, 1.]})
        self.fixed = pd.DataFrame({"name": ["Alice", "Bob"], "amount": [1., 1.]})
        self.sync()

    def sync(self, rules=("missing",), protected=("name",), reviewed=True):
        return sync_context(self.state, "a", self.original, self.fixed, rules, protected, reviewed)

    def accept(self, choice="Fixed copy"):
        return approve(self.state, "a", self.fixed if choice == "Fixed copy" else self.original, choice, 1)

    def test_lineage_and_all_change_reasons(self):
        result = change_index(self.original, self.fixed, True)
        self.assertEqual(result["Original row"].tolist(), [1, 2, 3])
        self.assertEqual(result["Change reason"].tolist(),
                         ["Trimmed whitespace", "Filled missing value", "Removed duplicate row"])
        self.assertEqual(result["Corrected row"].dropna().tolist(), [1, 2])

    def test_followup_changes_preserve_normalized_duplicate_reason(self):
        previous = change_index(self.original, self.fixed, True)
        previous.loc[previous["Column position"].isna(), "Change reason"] = "Removed duplicate after normalization"
        rebuilt = build_changes(self.original, self.fixed, [0, 1], previous)
        self.assertEqual(rebuilt.loc[rebuilt["Column position"].isna(), "Change reason"].item(),
                         "Removed duplicate after normalization")

    def test_no_duplicate_removal_retains_positions(self):
        result = change_index(self.original, self.original.copy(), False)
        self.assertTrue(result.empty)

    def test_invalid_lineage_fails_explicitly(self):
        with self.assertRaises(ValueError):
            change_index(self.original, self.fixed, False)

    def test_nulls_and_index_labels_do_not_create_false_changes(self):
        a = pd.DataFrame({"x": [pd.NA, "A", "A"]}, index=[4, 4, 1])
        result = change_index(a, a.iloc[:2].reset_index(drop=True), True)
        self.assertEqual(result["Original row"].tolist(), [3])

    def test_date_reason(self):
        a = pd.DataFrame({"date": ["2024/01/20"]})
        b = pd.DataFrame({"date": ["2024-01-20"]})
        self.assertEqual(change_index(a, b, False)["Change reason"].tolist(), ["Standardized date"])

    def test_whitespace_only_is_trim_not_imputation(self):
        a = pd.DataFrame({"x": ["   "]})
        b = pd.DataFrame({"x": [""]})
        self.assertEqual(change_index(a, b, False)["Change reason"].tolist(), ["Trimmed whitespace"])

    def test_rerun_preserves_approval(self):
        self.accept()
        self.sync()
        self.assertTrue(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_original_is_not_a_bypass(self):
        self.accept()
        self.assertFalse(is_approved(self.state, "a", self.original, "Original data"))
        self.accept("Original data")
        self.assertTrue(is_approved(self.state, "a", self.original, "Original data"))
        self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_changed_rules_and_revert_cannot_restore_approval(self):
        self.accept()
        self.sync(rules=("email",))
        self.sync()
        self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_changed_masking_or_review_invalidates(self):
        for kwargs in ({"protected": ("name", "amount")}, {"reviewed": False}):
            self.sync()
            self.accept()
            self.sync(**kwargs)
            self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_reapply_identical_data_invalidates(self):
        self.accept()
        invalidate(self.state, "a")
        self.sync()
        self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_data_and_file_isolation(self):
        self.accept()
        sync_context(self.state, "b", self.original, self.fixed, (), ("name",), True)
        self.assertFalse(is_approved(self.state, "b", self.fixed, "Fixed copy"))
        self.fixed.loc[0, "amount"] = 5
        self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_return_for_revision(self):
        self.accept()
        return_for_revision(self.state, "a")
        self.assertFalse(is_approved(self.state, "a", self.fixed, "Fixed copy"))

    def test_execution_gate_blocks_and_masks(self):
        sender = Mock(return_value=201)
        def send(consent=True):
            return guarded_push(self.state, "a", self.original, self.fixed, "Fixed copy",
                                ("name",), True, consent, sender, url="https://example.com")
        with self.assertRaises(ApprovalRequired):
            send()
        sender.assert_not_called()
        self.accept()
        with self.assertRaises(ApprovalRequired):
            send(False)
        with self.assertRaises(ApprovalRequired):
            send()
        self.original.loc[0, "amount"] = 9
        with self.assertRaises(ApprovalRequired):
            send()
        self.assertEqual(sender.call_count, 0)


if __name__ == "__main__":
    unittest.main()
