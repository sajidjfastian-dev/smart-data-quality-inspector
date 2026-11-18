"""Focused coverage of rule visibility, applicability and protected parameters."""
import unittest
from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest
from business_rules import apply_rules
from business_rule_review import rule_results


def rule(**updates):
    return dict(dict(id="r", column="status", kind="Value mapping",
                     expected='{"pending":"Approved"}', business=True,
                     mode="Correct automatically", enabled=True), **updates)


class RuleReviewTests(unittest.TestCase):
    def test_every_rule_and_current_copy(self):
        data = pd.DataFrame({"status": ["pending", "other"]})
        rules = [rule(), rule(enabled=False), rule(column="absent")]
        results = rule_results(data, rules)
        self.assertEqual(len(results), 3)
        self.assertEqual([r["count"] for r in results], [1, None, None])
        self.assertEqual(results[2]["applicability"], "Not applicable")
        fixed, _ = apply_rules(data, rules)
        self.assertEqual(rule_results(fixed, rules)[0]["count"], 0)
        self.assertEqual(rule_results(data, [rule(expected='{"other":"Approved"}')])[0]["count"], 1)
        self.assertEqual(rule_results(data, [rule(column="missing")])[0]["applicability"], "Not applicable")

    def test_incompatible_mixed_and_empty_not_passed(self):
        for kind, expected in [("Trim whitespace", ""), ("Minimum number", "5")]:
            r = rule(kind=kind, expected=expected, mode="Check only")
            values = [1, 2] if kind == "Trim whitespace" else ["bad", "wrong"]
            result = rule_results(pd.DataFrame({"status": values}), [r])[0]
            self.assertEqual(result["applicability"], "Not applicable")
            self.assertIsNone(result["count"])
        result = rule_results(pd.DataFrame({"status": [1, " a "]}),
                              [rule(kind="Trim whitespace", expected="")])[0]
        self.assertEqual(result["applicability"], "Partially applicable")
        self.assertEqual(result["count"], 2)  # Same flags as the inspection engine.
        result = rule_results(pd.DataFrame({"status": [None, " "]}), [rule()])[0]
        self.assertTrue(result["empty"])
        self.assertIsNone(result["count"])

    def test_render_empty_masked_disabled_and_recomputed(self):
        script = """
import pandas as pd
import streamlit as st
from business_rule_review import render_business_rule_review
render_business_rule_review(
    st.session_state.get("data", pd.DataFrame({"status": ["pending"]})),
    st.session_state.get("rules", []), {"status"},
    st.session_state.get("corrected", False))
"""
        app = AppTest.from_string(script).run()
        self.assertFalse(app.exception)
        self.assertIn("No business rules configured", app.info[0].value)
        app.session_state["rules"] = [rule(), rule(enabled=False), rule(column="absent", expected='{"x":"y"}')]
        app.run()
        self.assertFalse(app.exception)
        markup = "\n".join(item.value for item in app.markdown)
        self.assertNotIn("pending", markup)
        self.assertNotIn("Approved", markup)
        self.assertIn("••••", markup)
        captions = "\n".join(item.value for item in app.caption)
        self.assertIn("Disabled", captions)
        self.assertIn("Not applicable", captions)
        self.assertIn("Inspection flags: 1", captions)
        app.session_state["data"] = pd.DataFrame({"status": ["Approved"]})
        app.session_state["corrected"] = True
        app.run()
        self.assertIn("Inspection flags: 0", "\n".join(i.value for i in app.caption))
        app.session_state["rules"] = []
        app.run()
        self.assertIn("No business rules configured", app.info[0].value)

    def test_settings_edits_and_active_file_in_full_application(self):
        from demo_login import signed_in
        app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60))
        app.session_state["business_rules"] = [rule()]
        app.session_state["inspector_datasets"] = {
            "one.csv": pd.DataFrame({"status": ["pending", "other"]}),
            "two.csv": pd.DataFrame({"different": ["value"]}),
        }
        app.session_state["active_dataset"] = "one.csv"
        app.run()
        def widget(kind, label):
            return next(w for w in getattr(app, kind) if w.label == label)
        def captions():
            self.assertFalse(app.exception)
            return "\n".join(w.value for w in app.caption)
        self.assertIn("Inspection flags: 1", captions())
        widget("button", "Apply automatic fixes").click().run()
        self.assertIn("Results use the current corrected copy.", captions())
        self.assertIn("Inspection flags: 0", captions())
        widget("selectbox", "Business rule to edit").set_value(1).run()
        widget("checkbox", "Enable business rule").uncheck()
        widget("button", "Save business rule").click().run()
        self.assertIn("Not evaluated — rule is disabled.", captions())
        self.assertIn("Results use the original file.", captions())
        widget("selectbox", "Active file").set_value("two.csv").run()
        self.assertIn("Not applicable", captions())

    def test_standard_rules_are_the_same_in_settings_and_review(self):
        from demo_login import signed_in
        from business_rule_review import STANDARD_RULES
        app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60))
        app.session_state["inspector_datasets"] = {
            "one.csv": pd.DataFrame({"status": [" a ", " a "], "amount": [1, 1]}),
        }
        app.session_state["active_dataset"] = "one.csv"
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("Business rules", [tab.label for tab in app.tabs])
        self.assertNotIn("Inspection checks", [tab.label for tab in app.tabs])
        self.assertIn("Configured business rules · 7", [exp.label for exp in app.expander])
        self.assertTrue(all(any(box.label == label for box in app.checkbox) for _, label, *_ in STANDARD_RULES))
        captions = "\n".join(i.value for i in app.caption)
        self.assertIn("Inspection flags: 1", captions)
        next(w for w in app.button if w.label == "Apply automatic fixes").click().run()
        self.assertIn("one.csv", app.session_state["fixed_datasets"])
        next(w for w in app.checkbox if w.label == "Duplicate rows").uncheck().run()
        self.assertNotIn("one.csv", app.session_state["fixed_datasets"])
        self.assertIn("Not evaluated — rule is disabled.", "\n".join(i.value for i in app.caption))
        self.assertFalse(app.exception)
        next(w for w in app.checkbox if w.label == "Duplicate rows").check().run()
        next(w for w in app.checkbox if w.label == "Remove exact duplicate rows").uncheck().run()
        self.assertIn("Automatic correction off or not applicable", "\n".join(i.value for i in app.caption))
        next(w for w in app.button if w.label == "Apply automatic fixes").click().run()
        self.assertEqual(len(app.session_state["fixed_datasets"]["one.csv"]), 2)
        next(w for w in app.checkbox if w.label == "Remove exact duplicate rows").check().run()
        self.assertNotIn("one.csv", app.session_state["fixed_datasets"])
        next(w for w in app.button if w.label == "Apply automatic fixes").click().run()
        self.assertEqual(len(app.session_state["fixed_datasets"]["one.csv"]), 1)
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
