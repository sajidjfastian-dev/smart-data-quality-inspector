"""Current browser contract: seamless sign-in, main-page intake and reviewed exports.

Replaces the retired sidebar uploader/login-dialog/video-button contract.
Uses an isolated server and synthetic uploads; never publishes or writes production.
"""
from io import BytesIO
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen
from zipfile import ZipFile
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CSV_INPUT = b"id,name,amount,signup_date\n1, Alice ,10,2024/01/20\n2, Bob ,,2024/02/21\n1, Alice ,10,2024/01/20\n"


def excel_bytes():
    buf = BytesIO()
    pd.DataFrame({"id": [7, 8, 7], "name": [" Zoe ", " Kai ", " Zoe "],
                  "amount": [20, None, 20], "signup_date": ["2024/03/18", "2024/04/19", "2024/03/18"]}).to_excel(buf, index=False)
    return buf.getvalue()


class DownloadInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(ROOT/"app.py"),
             "--server.address=127.0.0.1", f"--server.port={port}", "--server.headless=true"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.server.terminate)
        for _ in range(120):
            try:
                with urlopen(cls.base_url+"/_stcore/health", timeout=1):
                    break
            except OSError:
                time.sleep(.25)
        else:
            raise RuntimeError("Isolated test server did not become ready")
        os.environ.setdefault("PLAYWRIGHT_NODEJS_PATH", shutil.which("node") or "")
        cls.pw = sync_playwright().start()
        cls.addClassCleanup(cls.pw.stop)
        cls.browser = cls.pw.chromium.launch(executable_path="/repl/tools/bin/chromium", args=["--no-sandbox"])
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.goto(self.base_url)
        self.page.get_by_role("button", name="Continue with SSO", exact=True).wait_for()
        self.settle()

    def settle(self):
        self.page.wait_for_timeout(500)
        self.page.get_by_role("button", name="Stop", exact=True).wait_for(state="hidden")
        exceptions = self.page.get_by_test_id("stException")
        self.assertEqual(exceptions.count(), 0, exceptions.all_inner_texts())

    def click(self, name):
        self.page.get_by_role("button", name=name, exact=True).click()
        self.settle()

    def login(self):
        self.click("Continue with SSO")
        self.page.locator(".st-key-nav_new_request button").click()
        self.settle()

    def upload(self, files=None):
        self.login()
        self.page.locator('input[type=file]').set_input_files(files or [
            {"name": "customer.csv", "mimeType": "text/csv", "buffer": CSV_INPUT}])
        self.settle()
        self.page.get_by_role("tab", name="1 · Overview", exact=True).wait_for()

    def tab(self, label):
        self.page.get_by_role("tab", name=label, exact=True).click()
        self.settle()

    def download(self, label):
        with self.page.expect_download() as event:
            self.page.get_by_role("button", name=label, exact=True).click()
        result = event.value
        self.assertIsNone(result.failure())
        return result.suggested_filename, Path(result.path()).read_bytes()

    def test_guest_gate_seamless_login_and_logout(self):
        self.assertEqual(self.page.locator('input[type=file]').count(), 0)
        self.upload()
        self.assertEqual(self.page.get_by_test_id("stSidebar").get_by_test_id("stFileUploader").count(), 0)
        self.assertEqual(self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader").count(), 1)
        self.click("Log out")
        self.assertEqual(self.page.locator('input[type=file]').count(), 0)
        self.page.get_by_role("button", name="Continue with SSO", exact=True).wait_for()
        self.page.get_by_role("heading", name="Turn data into decisions.", exact=True).wait_for()

    def test_retired_demo_button_stays_hidden_and_header_is_single(self):
        self.assertEqual(self.page.get_by_role("button", name="Watch demo").count(), 0)
        self.assertEqual(self.page.locator(".brand-header").count(), 1)
        self.assertEqual(self.page.locator("footer:visible").count(), 0)
        self.assertEqual(self.page.locator(".journey-stage").count(), 4)

    def test_mobile_landing_and_main_upload(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.reload()
        self.settle()
        self.assertFalse(self.page.get_by_test_id("stSidebar").is_visible())
        self.page.get_by_role("button", name="Expand sidebar", exact=True).click()
        self.upload()
        self.assertEqual(self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader").count(), 1)
        self.assertTrue(self.page.evaluate("document.documentElement.scrollWidth <= innerWidth"))

    def test_arabic_language_preserves_uploaded_file(self):
        self.upload()
        self.page.get_by_role("radio", name="AR", exact=True).click()
        self.settle()
        self.assertEqual(self.page.locator("html").get_attribute("dir"), "rtl")
        self.assertIn("customer.csv", self.page.get_by_test_id("stFileUploader").inner_text())
        self.page.get_by_role("radio", name="EN", exact=True).click()
        self.settle()
        self.assertIn("customer.csv", self.page.get_by_test_id("stFileUploader").inner_text())

    def test_invalid_file_does_not_discard_valid_file(self):
        self.upload([{"name": "valid.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
                     {"name": "invalid.xlsx", "mimeType": "application/octet-stream", "buffer": b"invalid"}])
        self.assertIn("invalid.xlsx:", self.page.get_by_test_id("stMain").inner_text())
        self.page.get_by_role("combobox", name="Active file", exact=True).wait_for()

    def test_empty_file_can_be_replaced(self):
        self.login()
        self.page.locator('input[type=file]').set_input_files({"name": "empty.csv", "mimeType": "text/csv", "buffer": b""})
        self.settle()
        self.assertIn("No files could be analyzed", self.page.get_by_test_id("stMain").inner_text())
        self.page.locator('input[type=file]').set_input_files({"name": "valid.csv", "mimeType": "text/csv", "buffer": CSV_INPUT})
        self.settle()
        self.page.get_by_role("tab", name="1 · Overview", exact=True).wait_for()

    def test_csv_export_matches_highlighted_corrected_copy(self):
        self.upload()
        self.tab("2 · Review & fix")
        self.click("Apply automatic fixes")
        self.tab("3 · Preview & export")
        self.assertGreater(self.page.locator(".fixed-preview-cell:visible").count(), 0)
        name, payload = self.download("Download a clean copy")
        frame = pd.read_csv(BytesIO(payload))
        self.assertEqual(name, "customer_cleaned.csv")
        self.assertEqual(len(frame), 2)
        self.assertEqual(frame.amount.tolist(), [10., 10.])
        self.assertEqual(frame.signup_date.tolist(), ["2024-01-20", "2024-02-21"])
        self.assertTrue(frame["name"].eq("••••").all())
        self.assertTrue(frame["id"].eq("••••").all())
        self.assertNotIn(b"Alice", payload)

    def test_excel_input_export_honors_duplicate_option(self):
        self.upload([{"name": "sales.xlsx", "mimeType": "application/octet-stream", "buffer": excel_bytes()}])
        self.tab("2 · Review & fix")
        self.page.get_by_text("Optional fix settings", exact=True).click()
        self.page.get_by_text("Remove exact duplicate rows", exact=True).click()
        self.settle()
        self.click("Apply automatic fixes")
        self.tab("3 · Preview & export")
        _, payload = self.download("Download a clean copy")
        frame = pd.read_csv(BytesIO(payload))
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame.amount.tolist(), [20., 20., 20.])
        self.assertTrue(frame["name"].eq("••••").all())
        self.assertEqual(frame.signup_date.tolist(), ["2024-03-18", "2024-04-19", "2024-03-18"])

    def test_csv_numeric_findings_and_approved_version(self):
        data = pd.DataFrame({
            "region": [" north ", "north", "south", "east", "west", "central", "other"],
            "amount": ["10", "10", "20", "30", "40", "50", "1,23"],
            "email": ["a@example.com", "a@example.com", "b@example.com", "c@example.com",
                      "d@example.com", "e@example.com", "invalid"],
        })
        self.upload([{"name": "inspection.csv", "mimeType": "text/csv",
                      "buffer": data.to_csv(index=False).encode()}])
        self.tab("2 · Review & fix")
        self.click("Apply automatic fixes")
        panel = self.page.locator('[role="tabpanel"]:visible')
        panel.get_by_role("heading", name="Review changes", exact=True).wait_for()
        self.assertIn("Removed duplicate after normalization", panel.inner_text())
        self.assertIn("2", panel.get_by_test_id("stMetric").filter(has_text="Remaining findings").inner_text())
        self.assertEqual(panel.get_by_text("Review unresolved issues", exact=True).count(), 0)
        self.assertNotIn("a@example.com", panel.inner_text())
        self.page.get_by_text("I reviewed all changes and remaining findings; this version is ready for review", exact=True).click()
        self.settle()
        self.click("Submit for review")
        self.page.get_by_text("I reviewed the changes and remaining findings", exact=True).click()
        self.settle()
        self.click("Approve request")
        self.click("Confirm")
        self.click("Approve ticket")
        self.click("Confirm")
        self.assertTrue(self.page.get_by_role("button", name="Download approved file", exact=True).is_disabled())
        self.click("Approve CAB step")
        self.click("Confirm")
        _, payload = self.download("Download approved file")
        frame = pd.read_csv(BytesIO(payload))
        self.assertEqual(len(frame), 6)
        self.assertIn("1,23", frame["amount"].tolist())
        self.assertTrue(frame["email"].eq("••••").all())
        self.assertNotIn(b"a@example.com", payload)

    def test_excel_numeric_findings_survive_correction(self):
        data = pd.DataFrame({"region": [" A ", "A", "B", "C", "D", "E", "F"],
                             "amount": ["10", "10", "20", "30", "40", "50", "1,23"]})
        buffer = BytesIO()
        data.to_excel(buffer, index=False)
        self.upload([{"name": "inspection.xlsx", "mimeType": "application/octet-stream",
                      "buffer": buffer.getvalue()}])
        self.tab("2 · Review & fix")
        self.click("Apply automatic fixes")
        panel = self.page.locator('[role="tabpanel"]:visible')
        panel.get_by_role("heading", name="Review changes", exact=True).wait_for()
        self.assertIn("Removed duplicate after normalization", panel.inner_text())
        self.assertIn("1", panel.get_by_test_id("stMetric").filter(has_text="Remaining findings").inner_text())
        self.assertEqual(panel.get_by_text("Review unresolved issues", exact=True).count(), 0)
        self.tab("3 · Preview & export")
        _, payload = self.download("Download a clean copy")
        frame = pd.read_csv(BytesIO(payload))
        self.assertEqual(len(frame), 6)
        self.assertIn("1,23", frame["amount"].tolist())

    def test_privacy_blocks_exports_until_reviewed(self):
        self.upload()
        self.page.get_by_role("button", name="Settings", exact=True).first.click()
        self.page.get_by_role("tab", name="Data privacy", exact=True).click()
        self.page.get_by_text("I reviewed all columns for sensitive data", exact=True).click()
        self.settle()
        self.page.keyboard.press("Escape")
        self.tab("3 · Preview & export")
        self.assertTrue(self.page.get_by_role("button", name="Download a clean copy", exact=True).is_disabled())

    def test_batch_archive_contains_both_masked_files(self):
        self.upload([{"name": "customer.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
                     {"name": "sales.xlsx", "mimeType": "application/octet-stream", "buffer": excel_bytes()}])
        control = self.page.get_by_role("combobox", name="Active file", exact=True)
        control.focus()
        control.press("ArrowDown")
        control.press("End")
        control.press("Enter")
        self.settle()
        self.tab("3 · Preview & export")
        self.click("Prepare cleaned batch ZIP")
        name, payload = self.download("Download all cleaned files")
        self.assertEqual(name, "cleaned_data_batch.zip")
        with ZipFile(BytesIO(payload)) as archive:
            self.assertEqual(set(archive.namelist()), {"customer_cleaned.csv", "sales.xlsx_cleaned.csv"})
            self.assertIsNone(archive.testzip())
            for member in archive.namelist():
                frame = pd.read_csv(BytesIO(archive.read(member)))
                self.assertEqual(len(frame), 2)
                self.assertTrue(frame["name"].eq("••••").all())
