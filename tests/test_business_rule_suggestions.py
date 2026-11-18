import unittest
import pandas as pd
from streamlit.testing.v1 import AppTest

from business_rule_suggestions import suggest_business_rules


class BusinessRuleSuggestionsTests(unittest.TestCase):
    def test_types_and_names_ground_suggestions_without_guessing_values(self):
        frame = pd.DataFrame({"status": ["SecretA", "SecretB"], "amount": [3, -1], "notes": ["x", "y"]})
        result = suggest_business_rules(frame, [], ["amount"], set())
        self.assertEqual([(x["column"], x["kind"]) for x in result],
                         [("status", "Allowed values"), ("amount", "Minimum number")])
        self.assertNotIn("Secret", repr(result))
        self.assertNotIn("expected", repr(result))

    def test_existing_rules_and_protected_fields_are_excluded(self):
        frame = pd.DataFrame({"status": ["a"], "amount": [10], "category": ["x"]})
        configured = [{"column": "status", "kind": "Allowed values", "expected": "a,b"}]
        result = suggest_business_rules(frame, configured, ["amount"], {"category"})
        self.assertEqual([r["column"] for r in result], ["amount"])
        self.assertEqual(suggest_business_rules(frame, configured, [], {"category"}), [])

    def test_empty_and_unrelated_fields_have_no_suggestions(self):
        self.assertEqual(suggest_business_rules(pd.DataFrame(), [], [], set()), [])
        self.assertEqual(suggest_business_rules(pd.DataFrame({"story": ["status"]}), [], [], set()), [])

    def test_review_retains_disclosure_without_unresolved_section(self):
        app = AppTest.from_string("""
import pandas as pd
import streamlit as st
from review_approval import sync_context, change_index
from review_ui import render_checker_review
data = pd.DataFrame({"amount": [2]})
findings = pd.DataFrame([{"Row Number": 1, "Column Name": "amount", "Issue Type": "Example",
                          "Current Value": 2, "Suggested Fix": "Check source"}])
state = {}
sync_context(state, "example", data, data, {}, set(), True)
changes = change_index(data, data, False)
render_checker_review(state, "example", data, data, changes, findings, set(), "Fixed copy", actions=False)
""").run()
        self.assertEqual([e.message for e in app.exception], [])
        self.assertNotIn("Review unresolved issues", [e.label for e in app.expander])
        self.assertIn("Remaining findings", [m.label for m in app.metric])
        self.assertTrue(any("does not mean error-free" in w.value for w in app.warning))


if __name__ == "__main__":
    unittest.main()
