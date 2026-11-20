"""Local demo login stays session-only and does not require the account database."""
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class LocalDemoLoginTests(unittest.TestCase):
    def test_explicit_demo_login_and_logout_without_replit_or_database(self):
        with patch.dict(os.environ, {"SMART_DQ_DEMO_LOGIN_ENABLED": "true"}):
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key="demo_login"))
            app.button(key="demo_login").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state["demo_user"], "Demo User")
            self.assertEqual(app.session_state["auth_subject"], "local-demo")
            self.assertNotIn("demo_session_id", app.session_state)
            self.assertNotIn("_persistent_demo_ready", app.session_state)

            app.button(key="sidebar_logout").click().run()
            self.assertFalse(app.exception)
            self.assertNotIn("auth_subject", app.session_state)
            self.assertNotIn("demo_user", app.session_state)
            self.assertTrue(app.button(key="demo_login"))


if __name__ == "__main__":
    unittest.main()
