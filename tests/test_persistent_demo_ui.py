"""Focused UI coverage for the shared examples and private upload boundary."""
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
import demo_store
import request_workflow as flow
from persistent_demo import register_source

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class PersistentDemoUITests(unittest.TestCase):
    def clean(self, app):
        self.assertEqual([e.message for e in app.exception], [])

    def test_all_seeded_view_paths_and_session_filter(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        app.button(key="sidebar_login").click().run()
        self.clean(app)
        seeded = {k:v for k,v in app.session_state["demo_requests"].items()
                  if v["session_id"].startswith("DEMO-HISTORY-")}
        self.assertEqual(len(seeded), 20)
        app.selectbox(key="rd_session").set_value("DEMO-HISTORY-01").run()
        self.clean(app)
        views = [b for b in app.button if str(b.key).startswith("rd_view_")]
        self.assertEqual(len(views), 4)
        for ref in seeded:
            app.session_state["request_view"] = ref
            app.run()
            self.clean(app)
            self.assertIn(ref, [h.value for h in app.header])
            self.assertNotIn("The submitted snapshot changed", " ".join(e.value for e in app.error))

    def test_sample_import_fix_submit_relogin_and_private_rule_fork(self):
        app = AppTest.from_file(APP, default_timeout=45).run()
        app.button(key="sidebar_login").click().run()
        session = app.session_state["demo_session_id"]
        try:
            app.button(key="nav_new_request").click().run()
            # UI tests need a database, not a live HTTP server. Endpoint behavior
            # is tested independently, and the browser smoke check uses real HTTP.
            frame = deepcopy(demo_store.load_catalog()["variants"]["original"]["original"])
            with patch("sample_client.fetch_sample", return_value=frame):
                app.button(key="sample_external_api").click().run()
            self.clean(app)
            ref = app.session_state["active_request_ref"]
            self.assertIn(ref, demo_store.list_requests())
            self.assertEqual(len(app.session_state["inspector_datasets"]["Synthetic quality sample"]), 520)
            apply_button = next(b for b in app.button if b.label == "Apply selected fixes")
            apply_button.click().run()
            self.clean(app)
            next(c for c in app.checkbox if c.label == "Ready to submit this version to the demo approver").check().run()
            app.button(key="submit_"+ref).click().run()
            self.clean(app)
            self.assertEqual(demo_store.list_requests()[ref]["revisions"][-1]["status"], "Submitted")
            app.button(key="sidebar_logout").click().run()
            self.assertEqual(len(app.get("file_uploader")), 0)
            app.button(key="sidebar_login").click().run()
            self.clean(app)
            self.assertNotEqual(app.session_state["demo_session_id"], session)
            self.assertIn(ref, app.session_state["demo_requests"])
        finally:
            with demo_store.connection() as conn:
                conn.execute("DELETE FROM dq_demo_requests WHERE session_id=%s", (session,))
                conn.execute("DELETE FROM dq_demo_sessions WHERE id=%s", (session,))


if __name__ == "__main__":
    unittest.main()
