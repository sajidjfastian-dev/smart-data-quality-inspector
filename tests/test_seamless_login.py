import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from sample_fixtures import load_test_fixture


class SeamlessLoginTests(unittest.TestCase):
    def test_one_click_login_and_approval_cancel_confirm(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45).run()
        app.button(key="sidebar_login").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["demo_role"], "Submitter")
        self.assertNotIn("Demo role", [w.label for w in app.selectbox])
        self.assertNotIn("login_continue", [w.key for w in app.button])
        app.button(key="nav_new_request").click().run()
        load_test_fixture(app)
        def button(label):
            return next(w for w in app.button if w.label == label)
        def check(label):
            next(w for w in app.checkbox if w.label == label).check().run()
        button("Apply automatic fixes").click().run()
        check("I reviewed all changes and remaining findings; this version is ready for review")
        button("Submit for review").click().run()
        ref = app.session_state["active_request_ref"]
        check("I reviewed the changes and remaining findings")
        button("Approve request").click().run()
        self.assertEqual(app.session_state["demo_requests"][ref]["revisions"][-1]["status"], "Submitted")
        button("Cancel").click().run()
        self.assertEqual(app.session_state["demo_requests"][ref]["revisions"][-1]["status"], "Submitted")
        button("Approve request").click().run()
        button("Confirm").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["demo_requests"][ref]["revisions"][-1]["status"], "Approved")
        self.assertEqual(app.session_state["demo_role"], "Submitter")
