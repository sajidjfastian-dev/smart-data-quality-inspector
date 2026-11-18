"""Focused checks for insight accuracy, consent, and masking."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest
from demo_login import signed_in
from insight_summary import dataset_facts, masked_sample, quality_suggestions

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class SummaryLogicTests(unittest.TestCase):
    def test_facts_and_sample_are_grounded_and_protected(self):
        data = pd.DataFrame({"email": [f"person{i}@example.com" for i in range(40)],
                             "amount": range(40), "date": [None] * 40})
        profile = pd.DataFrame({"Column": list(data.columns), "Missing": [0, 0, 40]})
        facts = dataset_facts(data, profile, ["amount"], ["date"], {"email"})
        self.assertEqual((facts["rows"], facts["columns"], facts["missing_cells"]), (40, 3, 40))
        self.assertEqual(facts["visible_fields"], ["amount", "date"])
        sample = masked_sample(data, {"email"})
        self.assertEqual(len(sample), 25)
        self.assertEqual((sample.amount.iloc[0], sample.amount.iloc[-1]), (0, 39))
        self.assertTrue(sample.email.eq("••••").all())

    def test_suggest_only_applicable_disabled_controls(self):
        data = pd.DataFrame({"email": ["a"], "amount": [1], "date": ["2024-01-01"]})
        suggestions = quality_suggestions(data, {"missing", "duplicates"}, ["email"], ["date"], ["amount"])
        self.assertEqual(len(suggestions), 4)
        self.assertTrue(any("source verification" in text for text in suggestions))
        self.assertTrue(any("not automatic" in text for text in suggestions))
        self.assertEqual(quality_suggestions(data, {"missing", "duplicates", "email", "date", "outliers", "numeric"},
                                             ["email"], ["date"], ["amount"]), [])


class SummaryUiTests(unittest.TestCase):
    def test_connected_summary_requires_consent_and_masks_data(self):
        calls = []
        response = {"choices": [{"message": {"content": "A sample containing financial amounts."}}]}

        def fake_request(*args, **kwargs):
            calls.append(json.loads(kwargs["body"]))
            return json.dumps(response).encode(), 200

        with patch("api_connections.request_public_api", side_effect=fake_request):
            app = signed_in(AppTest.from_file(APP, default_timeout=60)).run()
            data = pd.DataFrame({"email": ["alice@example.com", "bob@example.com"], "amount": [10, None]})
            app.session_state["inspector_datasets"] = {"private.csv": data}
            app.session_state["active_dataset"] = "private.csv"
            app.session_state["dashboard_tabs"] = "5 · Data insights"
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(any("2 rows and 2 fields" in x.value for x in app.markdown))
            self.assertNotIn("Generate AI summary", [b.label for b in app.button])
            self.assertEqual(calls, [])

            app.session_state["assistant_api_url"] = "https://example.com/v1/chat/completions"
            app.session_state["assistant_model_id"] = "model"
            app.session_state["assistant_api_key"] = "not-a-real-key"
            app.run()
            next(c for c in app.checkbox if c.label == "Allow sending the active dataset to this endpoint").check().run()
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == "Generate AI summary").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(calls), 1)
            prompt = json.dumps(calls[0]["messages"])
            self.assertNotIn("alice@example.com", prompt)
            self.assertNotIn("bob@example.com", prompt)
            self.assertIn("evenly spaced rows", prompt)
            self.assertTrue(any("financial amounts" in item.value for item in app.markdown))
            next(c for c in app.checkbox if c.label == "I reviewed all columns for sensitive data").uncheck().run()
            self.assertFalse(app.exception)
            self.assertNotIn("Generate AI summary", [b.label for b in app.button])
            self.assertFalse(any("financial amounts" in item.value for item in app.markdown))
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
