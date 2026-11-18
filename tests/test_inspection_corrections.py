"""Numeric controls and correction lineage through the actual application."""
from pathlib import Path
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest
from demo_login import signed_in


class InspectionCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"),
                                               default_timeout=60)).run()
        self.original = pd.DataFrame({
            "region": [" north ", "North", "South", "South", "West", "West", "East"],
            "amount": ["10", "10", None, "10", "1,23", "1,23", "20"],
            "email": ["x@example.com", "x@example.com", "bad", "bad",
                      "z@example.com", "z@example.com", "e@example.com"],
        })
        self.app.session_state["inspector_datasets"] = {"test.csv": self.original.copy(deep=True)}
        self.app.session_state["active_dataset"] = "test.csv"
        self.app.run()
        self.assertFalse(self.app.exception)

    def widget(self, kind, label):
        return next(w for w in getattr(self.app, kind) if w.label == label)

    def test_rules_fixes_recheck_and_lineage(self):
        numeric = self.widget("multiselect", "Treat columns as Numeric")
        numeric.set_value(["amount"]).run()
        findings = self.app.session_state["quality_scan_cache"]["test.csv"]["issues"]
        self.assertEqual(findings.query("`Issue Type` == 'Invalid Number'")["Row Number"].tolist(), [5, 6])
        self.widget("checkbox", "Invalid numeric values").uncheck().run()
        self.assertNotIn("Invalid Number", set(self.app.session_state["quality_scan_cache"]["test.csv"]["issues"]["Issue Type"]))
        self.widget("checkbox", "Invalid numeric values").check().run()

        self.widget("selectbox", "Rule column").select("region")
        self.widget("selectbox", "Rule type").select("Allowed values")
        self.widget("text_input", "Expected value").set_value("North,South,West,East")
        self.widget("button", "Add rule").click().run()
        self.assertTrue(self.widget("checkbox", "Normalize case and spacing to allowed values").value)
        self.widget("button", "Apply automatic fixes").click().run()
        self.assertFalse(self.app.exception)
        fixed = self.app.session_state["fixed_datasets"]["test.csv"]
        assert_frame_equal(self.app.session_state["inspector_datasets"]["test.csv"], self.original)
        self.assertEqual(len(fixed), 5)
        self.assertEqual(fixed["region"].tolist(), ["North", "South", "South", "West", "East"])
        self.assertEqual(fixed["amount"].tolist(), ["10", "10.0", "10", "1,23", "20"])
        changes = self.app.session_state["fix_change_indexes"]["test.csv"]["changes"]
        self.assertEqual(set(changes.loc[changes["Column position"].isna(), "Original row"]), {2, 6})
        self.assertIn("Removed duplicate after normalization", set(changes["Change reason"]))
        self.assertIn("Normalized to allowed value", set(changes["Change reason"]))
        remaining = self.app.session_state["review_scan_cache"]["test.csv"]["issues"]
        self.assertEqual(set(remaining["Issue Type"]) & {"Invalid Number", "Invalid Email"},
                         {"Invalid Number", "Invalid Email"})
        self.assertEqual(remaining.query("`Issue Type` == 'Invalid Number'")["Row Number"].tolist(), [4])
        self.assertIn("••••", "\n".join(item.value for item in self.app.markdown))
        saved = fixed.copy(deep=True)
        self.widget("button", "Apply automatic fixes").click().run()
        assert_frame_equal(self.app.session_state["fixed_datasets"]["test.csv"], saved)
        assert_frame_equal(self.app.session_state["inspector_datasets"]["test.csv"], self.original)


if __name__ == "__main__":
    unittest.main()
