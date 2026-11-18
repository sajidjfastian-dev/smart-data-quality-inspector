import unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from request_workflow import new_request, sample_seed_state
from demo_login import signed_in, TEST_SUBJECT

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class DashboardTests(unittest.TestCase):
    def app(self):
        app = signed_in(AppTest.from_file(APP, default_timeout=45))
        app.session_state["workspace_page"] = "requests"
        app.session_state["_persistent_demo_ready"] = True
        return app.run()

    def clean(self, app):
        self.assertEqual([e.message for e in app.exception], [])

    def test_login_and_request_upload_visibility(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        self.clean(app)
        self.assertNotIn("nav_requests", [w.key for w in app.button])
        self.assertEqual(len(app.get("file_uploader")), 0)
        signed_in(app)
        app.session_state["workspace_page"] = "requests"
        app.run()
        self.assertEqual(len(app.get("file_uploader")), 0)
        app.button(key="nav_new_request").click().run()
        self.clean(app)
        self.assertEqual(len(app.get("file_uploader")), 1)
        self.assertEqual(len(app.sidebar.get("file_uploader")), 0)
        app.button(key="nav_requests").click().run()
        self.assertEqual(len(app.get("file_uploader")), 0)

    def test_empty_new_and_view_draft(self):
        app = self.app()
        self.clean(app)
        self.assertIn("No requests yet", "\n".join(m.value for m in app.markdown))
        self.assertNotIn("rd_new", [button.key for button in app.button])
        app.button(key="nav_new_request").click().run()
        self.clean(app)
        ref = app.session_state["active_request_ref"]
        app.button(key="nav_requests").click().run()
        self.clean(app)
        self.assertEqual(len(app.session_state["demo_requests"]), 1)
        app.button(key=f"rd_view_{ref}").click().run()
        self.clean(app)
        self.assertIn(ref, [h.value for h in app.header])
        app.button(key="continue_"+ref).click().run()
        self.clean(app)
        self.assertEqual(app.session_state["workspace_page"], "inspection")

    def test_identical_reupload_in_new_request(self):
        app = self.app()
        app.button(key="nav_new_request").click().run()
        uploaded = BytesIO(b"name,amount\nAda,1\nBob,2\n")
        uploaded.name = "repeat.csv"
        uploaded.size = len(uploaded.getvalue())
        with patch("streamlit.file_uploader", return_value=[uploaded]):
            app.run()
            self.clean(app)
            first = app.session_state["active_request_ref"]
            next(w for w in app.checkbox if w.label == "I reviewed all changes and remaining findings; this version is ready for review").check().run()
            app.button(key="submit_"+first).click().run()
            self.clean(app)
            self.assertEqual(app.session_state["demo_requests"][first]["revisions"][0]["status"], "Submitted")
        with patch("streamlit.file_uploader", return_value=[]):
            app.button(key="nav_new_request").click().run()
            self.clean(app)
            second = app.session_state["active_request_ref"]
            self.assertNotEqual(first, second)
            self.assertNotIn("inspector_upload_signature", app.session_state)
        with patch("streamlit.file_uploader", return_value=[uploaded]):
            app.run()
            self.clean(app)
            self.assertEqual(app.session_state["active_request_ref"], second)
            self.assertIn("repeat.csv", app.session_state["inspector_datasets"])
            revision = app.session_state["demo_requests"][second]["revisions"][0]
            self.assertIn("working", revision)
            self.assertEqual(len(revision["working"]["original"]), 2)
            next(w for w in app.checkbox if w.label == "I reviewed all changes and remaining findings; this version is ready for review").check().run()
            app.button(key="submit_"+second).click().run()
            self.clean(app)
            self.assertEqual(app.session_state["demo_requests"][second]["revisions"][0]["status"], "Submitted")
            self.assertEqual(app.session_state["demo_requests"][first]["revisions"][0]["status"], "Submitted")

    def test_counts_filter_dates_pagination_and_language(self):
        app = self.app()
        state = sample_seed_state("Sajid")
        refs = [new_request(state) for _ in range(12)]
        for i, ref in enumerate(refs):
            state["demo_requests"][ref]["owner_id"] = TEST_SUBJECT
            revision = state["demo_requests"][ref]["revisions"][-1]
            if i > 3:
                revision["status"] = "Submitted" if i < 8 else "Approved"
                revision["submitted_at"] = "2026-11-17T12:00:00+04:00"
        app.session_state["demo_requests"] = state["demo_requests"]
        app.run()
        self.clean(app)
        self.assertEqual([m.value for m in app.metric], ["4", "4", "4", "0"])
        self.assertEqual(len([b for b in app.button if str(b.key).startswith("rd_view_")]), 10)
        app.button(key="rd_next").click().run()
        self.assertEqual(len([b for b in app.button if str(b.key).startswith("rd_view_")]), 2)
        app.checkbox(key="rd_status_option_0").check().run()
        self.assertNotIn("rd_scope", [radio.key for radio in app.radio])
        self.assertNotIn("refresh_shared_requests", [button.key for button in app.button])
        self.assertEqual([m.value for m in app.metric], ["4", "0", "0", "0"])
        app.checkbox(key="rd_use_dates").check().run()
        self.clean(app)
        self.assertEqual(len([b for b in app.button if str(b.key).startswith("rd_view_")]), 0)
        app.button(key="rd_clear").click().run()
        app.text_input(key="rd_reference").input(refs[0]).run()
        self.assertEqual(len([b for b in app.button if str(b.key).startswith("rd_view_")]), 1)
        app.segmented_control(key="language_choice").set_value("AR").run()
        self.clean(app)
        app.button(key="sidebar_logout").click().run()
        self.clean(app)
        self.assertNotIn("demo_requests", app.session_state)

    def test_clickable_status_cards(self):
        app = self.app()
        state = sample_seed_state("Sajid")
        for status in ("Draft", "Submitted", "Approved", "Ticket approved", "CAB approved", "Simulated", "Rejected"):
            ref = new_request(state)
            state["demo_requests"][ref]["revisions"][-1]["status"] = status
            state["demo_requests"][ref]["owner_id"] = TEST_SUBJECT
        app.session_state["demo_requests"] = state["demo_requests"]
        app.run()
        for slug, expected in (("draft", ["Draft"]), ("submitted", ["Submitted"]),
                               ("approved", ["Approved", "Ticket approved", "CAB approved", "Simulated"]),
                               ("rejected", ["Rejected"])):
            app.button(key=f"rd_status_click_{slug}").click().run()
            self.clean(app)
            self.assertEqual(set(app.session_state["rd_statuses"]), set(expected))
            self.assertEqual(len([b for b in app.button if str(b.key).startswith("rd_view_")]), len(expected))
        app.button(key="rd_status_click_rejected").click().run()
        self.assertEqual(app.session_state["rd_statuses"], [])


if __name__ == "__main__":
    unittest.main()
