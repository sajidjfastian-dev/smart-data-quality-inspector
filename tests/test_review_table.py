"""The compact change table keeps row rejection and privacy safeguards."""
import unittest
from streamlit.testing.v1 import AppTest


SCRIPT = """
import pandas as pd
import streamlit as st
from review_ui import render_checker_review
from review_approval import sync_context

st.session_state["interface_language"] = LOCALE
original = pd.DataFrame({"date": ["2023/01/02", "2023/01/16", "removed"],
                         "private": ["secret one", "secret two", "secret three"]})
corrected = pd.DataFrame({"date": ["2023-01-02", "2023-01-16"],
                          "private": ["changed one", "secret two"]})
changes = pd.DataFrame([[1, 1, 0, "Standardized date"], [1, 1, 1, "Trimmed whitespace"],
                        [2, 2, 0, "Standardized date"], [3, None, None, "Removed duplicate row"]],
                       columns=["Original row", "Corrected row", "Column position", "Change reason"])
sync_context(st.session_state, "sample", original, corrected, {}, {"private"}, True)
render_checker_review(st.session_state, "sample", original, corrected, changes, pd.DataFrame(),
                      {"private"}, "Fixed copy", actions=False,
                      on_reject=lambda row: st.session_state.update(rejected=row))
"""


class ReviewTableTests(unittest.TestCase):
    def test_table_rejects_retained_rows_and_masks_values_in_both_languages(self):
        for locale, label, heading in (
            ("English", "Reject fix", "Original row"),
            ("العربية", "رفض التصحيح", "الصف الأصلي"),
        ):
            with self.subTest(locale=locale):
                app = AppTest.from_string(SCRIPT.replace("LOCALE", repr(locale))).run()
                self.assertEqual([error.message for error in app.exception], [])
                markup = "\n".join(element.value for element in app.markdown)
                self.assertEqual(markup.count(f"<bdi>{heading}</bdi>"), 1)
                self.assertIn("••••", markup)
                self.assertNotIn("secret one", markup)
                self.assertNotIn("changed one", markup)
                buttons = [button for button in app.button if button.label == label]
                self.assertEqual(len(buttons), 3)
                self.assertTrue(str(buttons[0].key).endswith("_reject_1_0"))
                self.assertTrue(str(buttons[1].key).endswith("_reject_1_1"))
                self.assertTrue(str(buttons[2].key).endswith("_reject_2_2"))
                buttons[2].click().run()
                self.assertEqual(app.session_state["rejected"], 2)
                self.assertEqual([error.message for error in app.exception], [])
