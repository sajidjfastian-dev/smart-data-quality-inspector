"""Focused real-script checks; no live outbound requests."""
import unittest
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from demo_login import signed_in
from sample_fixtures import load_test_fixture


class CheckerFlowTests(unittest.TestCase):
    def setUp(self):
        self.app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45)).run()
        load_test_fixture(self.app)
        self.assert_clean()

    def widget(self, kind, label):
        return next(item for item in getattr(self.app, kind) if item.label == label)

    def assert_clean(self):
        self.assertEqual([e.message for e in self.app.exception], [])

    def fix(self):
        self.widget("button", "Apply selected fixes").click().run()
        self.assert_clean()

    def approve(self):
        self.widget("checkbox", "I reviewed the changes and remaining findings").check().run()
        self.widget("button", "Approve reviewed version").click().run()
        self.assert_clean()

    def test_fixed_review_approval_send_and_reapply(self):
        self.assertTrue(self.widget("button", "Push data to API").disabled)
        self.fix()
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertIn("checker-comparison", markup)
        self.assertIn("••••", markup)
        self.assertIn("Removed duplicate row", markup)
        self.approve()
        self.widget("selectbox", "Data to send").select("Fixed copy").run()
        self.widget("text_input", "Destination API URL").input("https://example.com/records").run()
        self.widget("checkbox", "I approve sending the selected data to this destination").check().run()
        self.assertFalse(self.widget("button", "Push data to API").disabled)
        with patch("api_settings.push_api_data", return_value=201) as push:
            self.widget("button", "Push data to API").click().run()
        self.assert_clean()
        push.assert_called_once()
        protected = push.call_args.kwargs["data"]["name"].dropna()
        self.assertTrue(protected.map(lambda value: value == "••••" or not str(value).strip()).all())
        self.fix()
        self.assertFalse(self.app.session_state["final_approvals"])
        self.assertTrue(self.widget("button", "Push data to API").disabled)

    def test_original_review_return_and_rule_invalidation(self):
        self.approve()
        self.assertTrue(self.app.session_state["final_approvals"])
        self.widget("button", "Return for revision").click().run()
        self.assertFalse(self.app.session_state["final_approvals"])
        self.approve()
        self.widget("checkbox", "Missing values").uncheck().run()
        self.assert_clean()
        self.assertFalse(self.app.session_state["final_approvals"])

    def test_rule_crud_and_validation(self):
        self.widget("selectbox", "Rule type").select("Minimum number")
        self.widget("text_input", "Expected value").input("nan")
        self.widget("button", "Add rule").click().run()
        self.assertIn("Enter a finite number for the limit.", [e.value for e in self.app.error])
        self.widget("selectbox", "Rule column").select("age")
        self.widget("text_input", "Expected value").input("30")
        self.widget("button", "Add rule").click().run()
        self.assert_clean()
        self.widget("selectbox", "Rule to edit").select(1).run()
        self.widget("text_input", "Expected value").input("40")
        self.widget("button", "Save changes").click().run()
        self.assert_clean()
        self.widget("button", "Delete selected rule").click().run()
        self.assert_clean()
        self.assertEqual(len(self.widget("selectbox", "Rule to edit").options), 1)

    def test_arabic_and_logout(self):
        self.fix()
        self.app.segmented_control(key="language_choice").set_value("AR").run()
        self.assert_clean()
        self.assertIn("اعتماد النسخة المراجعة", [b.label for b in self.app.button])
        self.assertIn("مراجعة المدقق والاعتماد النهائي", [s.value for s in self.app.subheader])
        self.widget("button", "تسجيل الخروج").click().run()
        self.assert_clean()
        self.assertNotIn("review_contexts", self.app.session_state)

    def test_ticket_flow_bilingual_stale_and_logout(self):
        self.assertTrue(self.widget("button", "Generate demo ticket").disabled)
        self.fix()
        self.approve()
        with patch("api_settings.push_api_data") as push:
            self.widget("button", "Generate demo ticket").click().run()
            ticket = next(iter(self.app.session_state["demo_change_tickets"].values())).copy()
            self.widget("button", "Generate demo ticket").click().run()
            self.assertEqual(ticket, next(iter(self.app.session_state["demo_change_tickets"].values())))
            push.assert_not_called()
        self.assertTrue(self.widget("button", "Push data to API").disabled)
        self.assertIn(ticket["version"], "\n".join(x.value for x in self.app.text))
        self.app.segmented_control(key="language_choice").set_value("AR").run()
        self.assertIn("إنشاء تذكرة تجريبية", [b.label for b in self.app.button])
        self.assertIn("معاينة التذكرة التجريبية — لم تُرسل", [s.value for s in self.app.success])
        self.widget("button", "إعادة للمراجعة").click().run()
        self.assertTrue(self.widget("button", "إنشاء تذكرة تجريبية").disabled)
        self.assertTrue(any("تذكرة تجريبية قديمة" in x.value for x in self.app.warning))
        self.widget("button", "تسجيل الخروج").click().run()
        self.assert_clean()
        self.assertNotIn("demo_change_tickets", self.app.session_state)


if __name__ == "__main__":
    unittest.main()
