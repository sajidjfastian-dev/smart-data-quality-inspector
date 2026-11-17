"""Browser-level tests of the actual Streamlit download buttons.

These tests start an isolated Streamlit server and download into temporary
browser storage; they do not import or call the app's export helpers.
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
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile

import pandas as pd
from pandas.testing import assert_frame_equal
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CSV_INPUT = b"id,name,amount,signup_date\n1, Alice ,10,2024/01/20\n2, Bob ,,2024/02/21\n1, Alice ,10,2024/01/20\n"
EXCEL_INPUT = pd.DataFrame({
    "id": [7, 8, 7],
    "name": ["  Zoe  ", "  Kai ", "  Zoe  "],
    "amount": [20.0, None, 20.0],
    "signup_date": ["2024/03/18", "2024/04/19", "2024/03/18"],
})


def excel_bytes():
    buffer = BytesIO()
    EXCEL_INPUT.to_excel(buffer, index=False, engine="openpyxl")
    return buffer.getvalue()


class DownloadInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Bind a free port for this test server, independent of the preview.
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base_url = f"http://127.0.0.1:{port}"
        cls.server = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py"),
                "--server.address=127.0.0.1", f"--server.port={port}",
                "--server.headless=true", "--browser.gatherUsageStats=false",
            ],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        cls.addClassCleanup(cls.stop_server)
        deadline = time.monotonic() + 45
        while True:
            if cls.server.poll() is not None:
                raise RuntimeError("The Streamlit test server exited before starting")
            try:
                with urlopen(f"{cls.base_url}/_stcore/health", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("The Streamlit test server did not become ready")
            time.sleep(0.2)

        # Replit's bundled Playwright driver may lack system libraries; its
        # installed Node and Chromium can be used instead. Other environments
        # use Playwright's normal bundled browser unless explicitly configured.
        replit_chromium = "/repl/tools/bin/chromium"
        if (
            Path(replit_chromium).exists() and shutil.which("node")
            and "PLAYWRIGHT_NODEJS_PATH" not in os.environ
        ):
            os.environ["PLAYWRIGHT_NODEJS_PATH"] = shutil.which("node")
            cls.addClassCleanup(os.environ.pop, "PLAYWRIGHT_NODEJS_PATH", None)
        cls.playwright = sync_playwright().start()
        cls.addClassCleanup(cls.playwright.stop)
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        if not executable and Path(replit_chromium).exists():
            executable = replit_chromium
        cls.browser = cls.playwright.chromium.launch(
            headless=True, executable_path=executable, args=["--no-sandbox"],
        )
        cls.addClassCleanup(cls.browser.close)

    @classmethod
    def stop_server(cls):
        cls.server.terminate()
        try:
            cls.server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            cls.server.kill()
            cls.server.wait()

    def setUp(self):
        self.context = self.browser.new_context(accept_downloads=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(30000)
        self.page.goto(self.base_url)
        self.page.get_by_role("button", name="Explore sample workspace").wait_for()

    def upload(self, files):
        self.page.locator('input[type="file"]').set_input_files(files)
        self.page.get_by_role("tab", name="3 · Review & fix").wait_for()

    def click_tab(self, name):
        self.page.get_by_role("tab", name=name).click()

    def test_watch_demo_loads_and_plays_local_video(self):
        self.page.get_by_role("button", name="Watch demo").click()
        dialog = self.page.get_by_role("dialog", name="A quick tour of the inspector")
        video = dialog.locator("video")
        video.wait_for()
        video.evaluate("""async video => {
            video.muted = true;
            await video.play();
        }""")
        self.page.wait_for_function(
            """() => {
                const video = document.querySelector('[role="dialog"] video');
                return video && video.readyState >= 2 && video.currentTime > 0;
            }""",
            timeout=30000,
        )
        self.assertGreater(video.evaluate("video => video.duration"), 0)
        self.assertIsNone(video.evaluate("video => video.error"))

    def download(self, label):
        with self.page.expect_download(timeout=30000) as pending:
            self.page.get_by_role("button", name=label, exact=True).click()
        result = pending.value
        self.assertIsNone(result.failure())
        return result.suggested_filename, Path(result.path()).read_bytes()

    def assert_data(self, actual, rows):
        expected = pd.DataFrame(rows, columns=["id", "name", "amount", "signup_date"])
        assert_frame_equal(actual, expected, check_dtype=False)

    def test_mobile_landing_upload_preserves_csv_and_excel_in_workspace(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.reload()
        uploader = self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader")
        uploader.wait_for(state="visible")
        self.assertIn("500MB", uploader.inner_text().replace(" ", ""))
        with self.page.expect_file_chooser() as chooser:
            uploader.get_by_role("button", name="Upload", exact=True).click()
        chooser.value.set_files([
            {"name": "customers.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
            {
                "name": "orders.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "buffer": excel_bytes(),
            },
        ])
        self.page.get_by_role("tab", name="3 · Review & fix").wait_for()
        self.page.get_by_text("Workspace · 2 file(s)", exact=False).wait_for()
        self.assertEqual(self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader").count(), 0)
        self.page.get_by_role("tab", name="2 · Issue log").click()
        self.page.get_by_text("Workspace · 2 file(s)", exact=False).wait_for()

        # The same widget has moved to the sidebar without losing its files.
        self.page.get_by_role("button", name="Expand sidebar").click()
        sidebar_uploader = self.page.get_by_test_id("stSidebar").get_by_test_id("stFileUploader")
        sidebar_uploader.wait_for(state="visible")
        self.assertIn("customers.csv", sidebar_uploader.inner_text())
        self.assertIn("orders.xlsx", sidebar_uploader.inner_text())

    def test_landing_upload_keeps_valid_file_and_reports_invalid_excel(self):
        uploader = self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader")
        uploader.locator('input[type="file"]').set_input_files([
            {"name": "valid.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
            {
                "name": "invalid.xlsx",
                "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "buffer": b"not an excel workbook",
            },
        ])
        self.page.get_by_role("tab", name="3 · Review & fix").wait_for()
        self.page.get_by_text("Workspace · 1 file(s)", exact=False).wait_for()
        self.page.get_by_text("invalid.xlsx:", exact=False).wait_for()

    def test_landing_rejects_empty_csv_and_can_retry(self):
        uploader = self.page.get_by_test_id("stMain").get_by_test_id("stFileUploader")
        uploader.locator('input[type="file"]').set_input_files([
            {"name": "empty.csv", "mimeType": "text/csv", "buffer": b""},
        ])
        self.page.get_by_text("No files could be analyzed", exact=False).wait_for()
        uploader.locator('input[type="file"]').set_input_files([
            {"name": "valid.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
        ])
        self.page.get_by_role("tab", name="3 · Review & fix").wait_for()
        self.page.get_by_text("Workspace · 1 file(s)", exact=False).wait_for()

    def test_fixed_csv_download_reflects_applied_fixes(self):
        self.upload([{"name": "customer records.csv", "mimeType": "text/csv", "buffer": CSV_INPUT}])
        self.click_tab("3 · Review & fix")
        fixed = self.page.get_by_role("button", name="Download fixed file (CSV)", exact=True)
        self.assertEqual(fixed.count(), 0)
        self.page.get_by_role("button", name="Apply selected fixes").click()
        self.page.get_by_text("Applied fixes to a copy of customer records.csv").wait_for(state="attached")
        self.click_tab("3 · Review & fix")
        fixed.wait_for()
        filename, content = self.download("Download fixed file (CSV)")
        self.assertEqual(filename, "customer records_fixed.csv")
        self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
        self.assert_data(pd.read_csv(BytesIO(content)), [
            [1, "Alice", 10.0, "2024-01-20"],
            [2, "Bob", 10.0, "2024-02-21"],
        ])

    def test_fixed_excel_download_honors_selected_fixes(self):
        self.upload([{
            "name": "sales.xlsx",
            "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "buffer": excel_bytes(),
        }])
        self.click_tab("3 · Review & fix")
        self.page.get_by_text("Remove exact duplicate rows", exact=True).click()
        self.page.get_by_role("button", name="Apply selected fixes").click()
        self.page.get_by_text("Applied fixes to a copy of sales.xlsx").wait_for(state="attached")
        self.click_tab("3 · Review & fix")
        self.page.get_by_role("button", name="Download fixed file (XLSX)").wait_for()
        filename, content = self.download("Download fixed file (XLSX)")
        self.assertEqual(filename, "sales_fixed.xlsx")
        self.assert_data(pd.read_excel(BytesIO(content), sheet_name="Fixed data"), [
            [7, "Zoe", 20.0, "2024-03-18"],
            [8, "Kai", 20.0, "2024-04-19"],
            [7, "Zoe", 20.0, "2024-03-18"],
        ])

    def test_prepared_batch_download_contains_each_cleaned_file(self):
        self.upload([
            {"name": "customer records.csv", "mimeType": "text/csv", "buffer": CSV_INPUT},
            {"name": "sales.xlsx", "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "buffer": excel_bytes()},
        ])
        self.click_tab("4 · Preview & export")
        self.assertEqual(self.page.get_by_role("button", name="Download all cleaned files").count(), 0)
        self.page.get_by_role("button", name="Prepare cleaned batch ZIP").click()
        self.page.get_by_text("Cleaned batch export is ready").wait_for(state="attached")
        self.click_tab("4 · Preview & export")
        self.page.get_by_role("button", name="Download all cleaned files").wait_for()
        filename, content = self.download("Download all cleaned files")
        self.assertEqual(filename, "cleaned_data_batch.zip")
        with ZipFile(BytesIO(content)) as archive:
            self.assertEqual(set(archive.namelist()), {
                "customer_records_cleaned.csv", "sales.xlsx_cleaned.csv",
            })
            self.assertEqual(len(archive.namelist()), 2)
            self.assertIsNone(archive.testzip())
            self.assert_data(pd.read_csv(BytesIO(archive.read("customer_records_cleaned.csv"))), [
                [1, "Alice", 10.0, "2024/01/20"],
                [2, "Bob", 10.0, "2024/02/21"],
            ])
            self.assert_data(pd.read_csv(BytesIO(archive.read("sales.xlsx_cleaned.csv"))), [
                [7, "Zoe", 20.0, "2024/03/18"],
                [8, "Kai", 20.0, "2024/04/19"],
            ])


if __name__ == "__main__":
    unittest.main()
