"""Regressions for masking and privacy-review boundaries."""

from io import BytesIO
from pathlib import Path
import json
import unittest
from unittest.mock import patch

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest
from demo_login import signed_in

from security_guardrails import (
    MASK, detect_sensitive_columns, mask_dataframe, mask_findings,
    mask_text_with_dataset,
)


ROOT = Path(__file__).resolve().parents[1]


class MaskingTests(unittest.TestCase):
    def test_detection_checks_complete_columns_and_arabic_headers(self):
        data = pd.DataFrame({
            "الاسم": ["ليلى", "علي"],
            "notes": ["normal", "contact@example.com"],
            "other": ["ordinary", "784-1990-1234567-1"],
            "number": [1, 4111111111111111],
            "sales": [2, 3],
        })
        self.assertEqual(detect_sensitive_columns(data, chunk_size=1), {"الاسم", "notes", "other", "number"})

    def test_masks_copies_findings_and_exact_names_in_chat(self):
        data = pd.DataFrame({"name": ["Alice Smith", None], "region": ["Dubai", "Abu Dhabi"]})
        original = data.copy(deep=True)
        protected = mask_dataframe(data, {"name"})
        self.assertEqual(protected.loc[0, "name"], MASK)
        self.assertTrue(pd.isna(protected.loc[1, "name"]))
        self.assertEqual(protected.loc[0, "region"], "Dubai")
        pd.testing.assert_frame_equal(data, original)
        issues = pd.DataFrame([{
            "Row Number": 1, "Column Name": "name", "Issue Type": "Custom: Allowed values",
            "Current Value": "Alice Smith", "Suggested Fix": "Use one of: Alice Smith",
        }])
        masked = mask_findings(issues, {"name"})
        self.assertNotIn("Alice", masked.to_string())
        self.assertEqual(mask_text_with_dataset("Review Alice Smith please", data, {"name"}), f"Review {MASK} please")


class PrivacyFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = signed_in(AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)).run()
        self.data = pd.DataFrame({
            "name": ["Alice Smith", "Bob Jones", "Alice Smith"],
            "email": ["alice@example.com", "bob@example.com", "alice@example.com"],
            "region": ["Dubai", "Abu Dhabi", "Dubai"],
        })
        self.app.session_state["inspector_datasets"] = {"test.csv": self.data}
        self.app.session_state["active_dataset"] = "test.csv"
        self.app.run()
        self.assertFalse(self.app.exception)

    def widget(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def test_review_and_manual_selection_mask_displays_and_downloads(self):
        downloads = []
        original = st.download_button

        def capture(*args, **kwargs):
            if args and args[0] == "Download a clean copy":
                downloads.append(kwargs.copy())
            return original(*args, **kwargs)

        with patch.object(st, "download_button", side_effect=capture):
            self.app.run()
            self.assertTrue(downloads[-1]["disabled"])
            self.assertTrue(any("All data values are hidden" in item.value for item in self.app.warning))
            self.widget("multiselect", "Protect additional columns").select("region").run()
            self.widget("checkbox", "I reviewed all columns for sensitive data").check().run()
            self.assertFalse(downloads[-1]["disabled"])
            cleaned = pd.read_csv(BytesIO(downloads[-1]["data"]()))
            self.assertTrue((cleaned == MASK).all().all())
            self.assertEqual(self.data.loc[0, "name"], "Alice Smith")
            self.widget("multiselect", "Protect additional columns").set_value([]).run()
            self.assertTrue(downloads[-1]["disabled"])
            self.assertFalse(self.widget("checkbox", "I reviewed all columns for sensitive data").value)

    def test_api_push_and_model_receive_masked_data(self):
        self.widget("checkbox", "I reviewed all columns for sensitive data").check().run()
        self.widget("text_input", "Destination API URL").set_value("https://example.com/data").run()
        self.widget("checkbox", "I approve sending the selected data to this destination").check().run()
        with patch("api_settings.push_api_data", return_value=200) as push:
            self.widget("button", "Push data to API").click().run()
            self.assertFalse(self.app.exception)
            sent = push.call_args.args[1]
            self.assertEqual(sent.loc[0, "name"], MASK)
            self.assertEqual(sent.loc[0, "email"], MASK)
            self.assertEqual(sent.loc[0, "region"], "Dubai")

        self.widget("text_input", "Chat Completions URL").set_value("https://example.com/v1/chat/completions")
        self.widget("text_input", "Model ID").set_value("test-model")
        self.widget("text_input", "API key").set_value("test-key")
        self.app.run()
        self.widget("checkbox", "Allow sending the active dataset to this endpoint").check().run()
        response = json.dumps({"choices": [{"message": {"content": "Ready"}}]}).encode()
        with patch("api_connections.request_public_api", return_value=(response, 200)) as request:
            self.app.chat_input[0].set_value("What about Alice Smith?").run()
            self.assertFalse(self.app.exception)
            payload = request.call_args.kwargs["body"].decode()
            self.assertNotIn("Alice Smith", payload)
            self.assertNotIn("alice@example.com", payload)
            self.assertIn(MASK, payload)
        self.widget("text_input", "Chat Completions URL").set_value("https://different.example.com/v1/chat/completions").run()
        self.assertFalse(self.widget("checkbox", "Allow sending the active dataset to this endpoint").value)


if __name__ == "__main__":
    unittest.main()
