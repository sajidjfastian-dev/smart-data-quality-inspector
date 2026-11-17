import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

import api_settings
from localization import translate, translate_issue_type
from sample_fixtures import load_test_fixture


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
        app.button(key="language_toggle").click().run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="active_dataset").value, active_file)
        self.assertIn("درجة جودة البيانات", app.button(key="metric_card_health").label)
        self.assertIn("نظرة عامة", app.tabs[0].label)
        app.button(key="language_toggle").click().run(timeout=90)
        self.assertFalse(app.exception)
        self.assertEqual(app.selectbox(key="active_dataset").value, active_file)
        self.assertEqual(app.tabs[0].label, "1 · Overview")

    def test_arabic_settings_api_errors_and_dataset_are_preserved(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
        load_test_fixture(app)
        name = app.selectbox(key="active_dataset").value
        before = app.session_state["inspector_datasets"][name].copy(deep=True)
        app.button(key="language_toggle").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.checkbox(key="check_email").label, "تنسيقات البريد الإلكتروني غير الصالحة")
        url = "https://example.com/Rows?value=Upload"
        app.text_input(key="source_api_url").set_value(url).run()
        with patch.object(api_settings, "fetch_api_data", side_effect=api_settings.ApiConnectionError("The JSON data path does not exist in the response.")):
            app.button(key="load_external_api").click().run()
        self.assertTrue(any("مسار بيانات JSON" in error.value for error in app.error))
        self.assertEqual(app.text_input(key="source_api_url").value, url)
        assert_frame_equal(app.session_state["inspector_datasets"][name], before)
        app.button(key="language_toggle").click().run()
        self.assertEqual(app.text_input(key="source_api_url").value, url)
        assert_frame_equal(app.session_state["inspector_datasets"][name], before)

    def test_arabic_assistant_answers_common_intents(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
        load_test_fixture(app)
        app.button(key="language_toggle").click().run()
        app.session_state["dashboard_tabs"] = "5 · المساعد"
        app.run()
        for question, expected in [
            ("كم عدد الصفوف المكررة؟", "مكررة"),
            ("ما القيم المتطرفة؟", "قيمة رقمية متطرفة"),
            ("كم عدد الأعمدة؟", "عموداً"),
            ("ما التواريخ غير الصالحة؟", "تاريخ غير صالح"),
        ]:
            app.chat_input[0].set_value(question).run()
            self.assertFalse(app.exception)
            key = next(key for key in app.session_state._state.filtered_state if key.startswith("quality_assistant_history_"))
            self.assertIn(expected, app.session_state[key][-1]["content"])

    def test_custom_finding_labels_preserve_rule_values(self):
        self.assertEqual(translate_issue_type("Custom: Must contain", "العربية"), "مخصص: يجب أن يحتوي على")
        self.assertEqual(translate("Include the text: {0}", "العربية").format("Rows العربية"), "أضف النص: Rows العربية")
        self.assertEqual(translate_issue_type("Custom: Must contain", "English"), "Custom: Must contain")

    def test_switching_languages_keeps_fixed_copy_and_insights(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=90).run()
        load_test_fixture(app)
        name = app.selectbox(key="active_dataset").value
        original = app.session_state["inspector_datasets"][name].copy(deep=True)
        app.button(key="language_toggle").click().run()
        app.session_state["dashboard_tabs"] = "3 · مراجعة وإصلاح"
        app.run()
        button = next(button for button in app.button if button.label == "تطبيق الإصلاحات المحددة")
        button.click().run()
        self.assertFalse(app.exception)
        fixed = app.session_state["fixed_datasets"][name].copy(deep=True)
        assert_frame_equal(app.session_state["inspector_datasets"][name], original)
        app.session_state["dashboard_tabs"] = "6 · رؤى البيانات"
        app.run()
        self.assertTrue(any("حقولك في لمحة" in item.value for item in app.subheader))
        app.button(key="language_toggle").click().run()
        assert_frame_equal(app.session_state["fixed_datasets"][name], fixed)
        assert_frame_equal(app.session_state["inspector_datasets"][name], original)
        self.assertTrue(any("Your fields at a glance" in item.value for item in app.subheader))


if __name__ == "__main__":
    unittest.main()
