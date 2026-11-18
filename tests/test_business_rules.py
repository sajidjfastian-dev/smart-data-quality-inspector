"""Focused business-rule coverage; no full-suite or production dependencies."""
import unittest
from copy import deepcopy
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from business_rules import validate, apply_rules, findings, applicability
from demo_login import signed_in


def rule(kind="Value mapping", expected='{"pending":"Approved"}', **kwargs):
    return validate(dict(column="status", kind=kind, expected=expected, business=True,
                         enabled=True, mode="Correct automatically", id="one", **kwargs))


class RuleEngineTests(unittest.TestCase):
    def test_mapping_and_original_and_reasons(self):
        original = pd.DataFrame({"status": ["pending", "unknown", None]})
        before = original.copy(deep=True)
        fixed, reasons = apply_rules(original, [rule()])
        self.assertEqual(fixed.status.iloc[:2].tolist(), ["Approved", "unknown"])
        self.assertTrue(pd.isna(fixed.status.iloc[2]))
        self.assertEqual(len(findings(original, [rule()])), 1)
        self.assertEqual(findings(fixed, [rule()]), [])
        self.assertEqual(reasons, {(0, 0): "Business rule: Value mapping"})
        assert_frame_equal(original, before)
        assert_frame_equal(apply_rules(fixed, [rule()])[0], fixed)

    def test_check_only_and_disabled(self):
        data = pd.DataFrame({"status": ["pending"]})
        r = rule()
        r["mode"] = "Check only"
        assert_frame_equal(apply_rules(data, [r])[0], data)
        self.assertEqual(len(findings(data, [r])), 1)
        r["enabled"] = False
        self.assertEqual(findings(data, [r]), [])

    def test_no_guessing_chains_collisions_or_clamping(self):
        for expected in ['{"a":"b","a":"c"}', '{"a":"b","b":"a"}', '{"a":2}']:
            with self.assertRaises(ValueError):
                rule(expected=expected)
        with self.assertRaises(ValueError):
            rule(kind="Minimum number", expected="20")
        data = pd.DataFrame({"status": ["pending"]})
        rules = [rule(), rule(expected='{"pending":"Other"}')]
        assert_frame_equal(apply_rules(data, rules)[0], data)
        self.assertTrue(applicability(data, rules))

    def test_validation_constraint_blocks_correction(self):
        rules = [rule(), dict(rule(kind="Allowed values", expected="Other"), mode="Check only")]
        data = pd.DataFrame({"status": ["pending"]})
        assert_frame_equal(apply_rules(data, rules)[0], data)

    def test_missing_columns_types_and_formatting(self):
        r = rule(kind="Trim whitespace", expected="")
        self.assertTrue(applicability(pd.DataFrame({"other": ["x"]}), [r]))
        data = pd.DataFrame({"status": [12, " a "]})
        self.assertTrue(applicability(data, [r]))
        self.assertEqual(apply_rules(data, [r])[0].status.tolist(), [12, "a"])

    def test_large_scan_agrees(self):
        from quality_large import scan_large_data
        from numeric_quality import parse_numbers
        import re
        data = pd.DataFrame({"status": ["pending", "other"] * 50001})
        columns = ["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"]
        result, _ = scan_large_data(data, set(), set(), set(), 1.5, None, set(), [rule()],
                                    re.compile(".*"), lambda v: None, lambda v: "", parse_numbers,
                                    str, columns)
        self.assertEqual(len(result), 50001)
        self.assertEqual(result["Row Number"].tolist(), list(range(1, len(data)+1, 2)))

    def test_protected_mapping_parameters_are_redacted(self):
        from business_rules import visible_rules
        r = rule()
        self.assertEqual(visible_rules([r], {"status"})[0]["expected"], "••••")
        self.assertEqual(visible_rules([r], set())[0]["expected"], r["expected"])

    def test_custom_rules_cannot_enter_shared_catalog(self):
        from persistent_demo import canonical_payload, make_private, eligible, register_source
        import request_workflow as flow
        frame = pd.DataFrame({"status": ["pending"]})
        state = {"demo_user": "Sajid", "demo_role": "Submitter", "_persistent_demo_ready": True}
        ref = flow.new_request(state)
        payload = {"file": "source.csv", "original": frame, "selected": frame, "choice": "Original data",
                   "rules": {"custom": [], "email": [], "date": [], "numeric": [], "enabled": [], "iqr": 1.5},
                   "protected": set(), "privacy_reviewed": True}
        state["demo_catalog"] = {"variants": {"original": deepcopy(payload)}}
        register_source(state, frame)
        payload["rules"]["custom"] = [rule()]
        self.assertTrue(eligible(state, state["demo_requests"][ref], payload))
        with self.assertRaises(flow.WorkflowError):
            canonical_payload(state, payload)
        make_private(state, ref, payload)
        private = state["demo_requests"][state["active_request_ref"]]
        self.assertNotEqual(private["reference"], ref)
        self.assertTrue(private["_private"])
        self.assertFalse(eligible(state, private, payload))
        self.assertEqual(frame.status.iloc[0], "pending")


class RuleUiTests(unittest.TestCase):
    def setUp(self):
        self.app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"),
                                               default_timeout=60)).run()

    def widget(self, kind, label):
        return next(w for w in getattr(self.app, kind) if w.label == label)

    def clean(self):
        self.assertEqual([e.message for e in self.app.exception], [])

    def add(self):
        self.widget("text_input", "Target column name").set_value("status")
        self.widget("selectbox", "Business rule type").set_value("Value mapping")
        self.widget("text_input", "Business rule value").set_value('{"pending":"Approved"}')
        self.widget("selectbox", "Rule behavior").set_value("Correct automatically")
        self.widget("button", "Add business rule").click().run()
        self.clean()

    def test_no_file_lifecycle_multiple_files_and_fix(self):
        self.add()
        self.assertNotIn("inspector_datasets", self.app.session_state)
        data = pd.DataFrame({"status": ["pending", "other"]})
        self.app.session_state["inspector_datasets"] = {"one.csv": data, "two.csv": data.copy()}
        self.app.session_state["active_dataset"] = "one.csv"
        self.app.run()
        self.clean()
        self.assertIn("Custom: Value mapping", self.app.session_state["quality_scan_cache"]["one.csv"]["issues"]["Issue Type"].tolist())
        self.widget("button", "Apply automatic fixes").click().run()
        self.clean()
        self.assertEqual(self.app.session_state["fixed_datasets"]["one.csv"].status.tolist(), ["Approved", "other"])
        self.assertEqual(self.app.session_state["inspector_datasets"]["one.csv"].status.tolist(), ["pending", "other"])
        self.widget("selectbox", "Active file").select("two.csv").run()
        self.assertIn("Custom: Value mapping", self.app.session_state["quality_scan_cache"]["two.csv"]["issues"]["Issue Type"].tolist())
        self.widget("selectbox", "Business rule to edit").set_value(1).run()
        self.widget("checkbox", "Enable business rule").uncheck()
        self.widget("button", "Save business rule").click().run()
        self.clean()
        self.assertNotIn("Custom: Value mapping", self.app.session_state["quality_scan_cache"]["two.csv"]["issues"]["Issue Type"].tolist())
        self.widget("selectbox", "Business rule to edit").set_value(1).run()
        self.widget("button", "Delete business rule").click().run()
        self.clean()
        self.assertEqual(self.app.session_state["business_rules"], [])

    def test_invalid_rule_is_not_saved(self):
        self.widget("text_input", "Target column name").set_value("amount")
        self.widget("selectbox", "Business rule type").set_value("Minimum number")
        self.widget("text_input", "Business rule value").set_value("nan")
        self.widget("button", "Add business rule").click().run()
        self.clean()
        self.assertEqual(self.app.session_state["business_rules"], [])
        self.assertTrue(self.app.error)

    def test_rule_edit_preserves_row_rejection_choices(self):
        self.add()
        self.app.session_state["inspector_datasets"] = {"rows.csv": pd.DataFrame({"status": ["pending", "pending"], "id": [1, 2]})}
        self.app.session_state["active_dataset"] = "rows.csv"
        self.app.run()
        self.widget("button", "Apply automatic fixes").click().run()
        self.widget("button", "Reject fix").click().run()
        self.clean()
        self.widget("selectbox", "Business rule to edit").set_value(1).run()
        self.widget("text_input", "Business rule value").set_value('{"pending":"Complete"}')
        self.widget("button", "Save business rule").click().run()
        self.widget("button", "Apply automatic fixes").click().run()
        self.clean()
        self.assertEqual(self.app.session_state["fixed_datasets"]["rows.csv"].status.tolist(), ["pending", "Complete"])

    def test_edit_invalidates_review_and_approved_export_is_exact(self):
        self.add()
        self.app.session_state["inspector_datasets"] = {"private.csv": pd.DataFrame({"status": ["pending", "other"]})}
        self.app.session_state["active_dataset"] = "private.csv"
        self.app.run()
        self.widget("button", "Apply automatic fixes").click().run()
        old_version = self.app.session_state["review_contexts"]["private.csv"]["version"]
        self.widget("selectbox", "Business rule to edit").set_value(1).run()
        self.widget("text_input", "Business rule value").set_value('{"pending":"Complete"}')
        self.widget("button", "Save business rule").click().run()
        self.clean()
        self.assertNotEqual(old_version, self.app.session_state["review_contexts"]["private.csv"]["version"])
        self.assertNotIn("private.csv", self.app.session_state["fixed_datasets"])
        self.assertNotIn("Submit for review", [w.label for w in self.app.button])
        self.widget("button", "Apply automatic fixes").click().run()
        self.widget("checkbox", "I reviewed all changes and remaining findings; this version is ready for review").check().run()
        self.widget("button", "Submit for review").click().run()
        self.widget("checkbox", "I reviewed the changes and remaining findings").check().run()
        self.widget("button", "Approve request").click().run()
        self.widget("button", "Confirm").click().run()
        self.widget("button", "Approve ticket").click().run()
        self.widget("button", "Confirm").click().run()
        self.widget("button", "Approve CAB step").click().run()
        self.widget("button", "Confirm").click().run()
        self.clean()
        from request_workflow import approved_download
        state = dict(self.app.session_state._state.filtered_state)
        payload = approved_download(state, state["active_request_ref"], 1)
        self.assertIn(b"Complete", payload)
        self.assertNotIn(b"pending", payload)
        self.assertNotIn(b"Approved", payload)
