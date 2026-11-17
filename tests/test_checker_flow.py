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
        self.widget("checkbox", "Ready to submit this version to the demo approver").check().run()
        self.widget("button", "Submit for review").click().run()
        self.widget("selectbox", "Demo role").select("Approver").run()
        self.widget("checkbox", "I reviewed the changes and remaining findings").check().run()
        self.widget("button", "Approve request").click().run()
        self.assert_clean()

    def test_fixed_review_approval_send_and_reapply(self):
        self.assertTrue(self.widget("button", "Push data to API").disabled)
        self.fix()
        markup = "\n".join(m.value for m in self.app.markdown)
        self.assertIn("checker-comparison", markup)
        self.assertIn("••••", markup)
        self.assertIn("Removed duplicate row", markup)
        self.approve()
        self.assertEqual(self.widget("selectbox", "Demo role").options, ["Submitter", "Approver"])
        self.widget("button", "Approve demo ticket").click().run()
        self.assertTrue(self.widget("button", "Simulate production application").disabled)
        self.widget("button", "Approve CAB step").click().run()
        with patch("api_settings.push_api_data") as push:
            self.widget("button", "Simulate production application").click().run()
        self.assert_clean()
        push.assert_not_called()
        ref = self.app.session_state["active_request_ref"]
        self.assertEqual(self.app.session_state["demo_requests"][ref]["revisions"][-1]["status"], "Simulated")
        self.widget("selectbox", "Demo role").select("Submitter").run()
        self.widget("button", "Create new draft revision").click().run()
        self.assert_clean()
        self.fix()
        self.assertEqual(self.app.session_state["demo_requests"][ref]["revisions"][-1]["status"], "Draft")
        self.assertTrue(self.widget("button", "Push data to API").disabled)

    def test_original_review_return_and_rule_invalidation(self):
        self.widget("checkbox", "Ready to submit this version to the demo approver").check().run()
        self.widget("button", "Submit for review").click().run()
        self.widget("selectbox", "Demo role").select("Approver").run()
        self.widget("button", "Reject request").click().run()
        self.assertIn("Enter a rejection reason.", [e.value for e in self.app.error])
        self.widget("text_area", "Rejection reason").input("Check the source").run()
        self.widget("button", "Reject request").click().run()
        self.widget("selectbox", "Demo role").select("Submitter").run()
        self.widget("button", "Create new draft revision").click().run()
        self.widget("checkbox", "Missing values").uncheck().run()
        self.widget("button", "Apply all built-in checks").click().run()
        self.assert_clean()
        self.assertTrue(self.widget("checkbox", "Missing values").value)
        ref = self.app.session_state["active_request_ref"]
        self.assertEqual(self.app.session_state["demo_requests"][ref]["revisions"][0]["status"], "Rejected")

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
        self.assertIn("تقديم للمراجعة", [b.label for b in self.app.button])
        self.assertIn("مراجعة التغييرات", [s.value for s in self.app.subheader])
        self.widget("button", "تسجيل الخروج").click().run()
        self.assert_clean()
        self.assertNotIn("review_contexts", self.app.session_state)

    def test_ticket_flow_bilingual_stale_and_logout(self):
        self.fix()
        self.approve()
        with patch("api_settings.push_api_data") as push:
            ref = self.app.session_state["active_request_ref"]
            ticket = self.app.session_state["demo_requests"][ref]["revisions"][-1]["ticket"]
            self.app.run()
            self.assertEqual(ticket, self.app.session_state["demo_requests"][ref]["revisions"][-1]["ticket"])
            push.assert_not_called()
        self.assertTrue(self.widget("button", "Push data to API").disabled)
        self.assertIn(ticket["version"], "\n".join(x.value for x in self.app.text))
        self.app.segmented_control(key="language_choice").set_value("AR").run()
        self.assertIn(ticket["reference"], "\n".join(x.value for x in self.app.text))
        self.assertTrue(any("تذكرة" in s.value for s in self.app.subheader))
        self.widget("button", "تسجيل الخروج").click().run()
        self.assert_clean()
        self.assertNotIn("demo_requests", self.app.session_state)


if __name__ == "__main__":
    unittest.main()
