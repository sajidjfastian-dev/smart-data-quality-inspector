import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from localization import translate


class LocalizationTests(unittest.TestCase):
    def test_placeholders_preserve_user_supplied_values(self):
        name = "Customer بيانات.csv"
        message = translate("Applied fixes to a copy of {0}. The original workspace data is unchanged.", "العربية")
        self.assertIn(name, message.format(name))
        self.assertEqual(translate(name, "العربية"), name)
        self.assertEqual(translate("Active file", "English"), "Active file")

    def test_language_switch_keeps_loaded_dataset(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
        self.assertFalse(app.exception)
        app.button(key="sidebar_sample").click().run(timeout=90)
        active_file = app.selectbox(key="active_dataset").value
        app.selectbox(key="interface_language").select("العربية").run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="active_dataset").value, active_file)
        self.assertIn("درجة جودة البيانات", app.button(key="metric_card_health").label)
        self.assertIn("نظرة عامة", app.tabs[0].label)
        app.selectbox(key="interface_language").select("English").run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="active_dataset").value, active_file)
        self.assertEqual(app.tabs[0].label, "1 · Overview")


if __name__ == "__main__":
    unittest.main()
