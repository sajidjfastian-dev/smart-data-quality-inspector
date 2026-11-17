"""Tests for API parsing, network safeguards, and explicit sending."""

import json
import socket
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from security_guardrails import mask_dataframe
from streamlit.testing.v1 import AppTest
from demo_login import signed_in

import api_connections as api
import api_settings
from sample_fixtures import load_test_fixture


class ApiConnectionTests(unittest.TestCase):
    def test_json_csv_excel_and_nested_path(self):
        json_rows = api.parse_api_data(
            b'{"payload":{"rows":[{"id":1,"profile":{"city":"Dubai"},"tags":["a","b"]}]}}',
            "JSON", "payload.rows",
        )
        self.assertEqual(json_rows.loc[0, "profile.city"], "Dubai")
        self.assertEqual(json_rows.loc[0, "tags"], '["a","b"]')
        csv_rows = api.parse_api_data(b"id,name\n1,Ada\n", "CSV")
        self.assertEqual(csv_rows.loc[0, "name"], "Ada")
        excel = BytesIO()
        pd.DataFrame({"id": [1], "name": ["Ada"]}).to_excel(excel, index=False)
        self.assertEqual(api.parse_api_data(excel.getvalue(), "Excel").loc[0, "name"], "Ada")
        with self.assertRaisesRegex(api.ApiConnectionError, "data path"):
            api.parse_api_data(b'{"items":[]}', "JSON", "unknown")
        with self.assertRaisesRegex(api.ApiConnectionError, "array of objects"):
            api.parse_api_data(b'{"id":1}', "JSON")
        with self.assertRaises(api.ApiConnectionError):
            api.parse_api_data(b"not a spreadsheet", "Excel")

    def test_url_checks_reject_local_private_and_mixed_dns(self):
        for address in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1"):
            with self.subTest(address=address):
                dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]
                with patch.object(api.socket, "getaddrinfo", return_value=dns):
                    with self.assertRaisesRegex(api.ApiConnectionError, "private and local"):
                        api._resolve_target("https://example.com/data")
        mixed = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
                 for ip in ("8.8.8.8", "127.0.0.1")]
        with patch.object(api.socket, "getaddrinfo", return_value=mixed):
            with self.assertRaises(api.ApiConnectionError):
                api._resolve_target("https://example.com/data")
        for url in ("http://example.com", "https://user:pass@example.com",
                    "https://example.com:8443", "https://example.com/path#fragment"):
            with self.subTest(url=url), self.assertRaises(api.ApiConnectionError):
                api._resolve_target(url)

    def test_request_pins_verified_ip_and_never_follows_redirects(self):
        class Response:
            status = 302
            def close(self): pass
        class Connection:
            def __init__(self, host, address, port):
                self.target = (host, address, port)
                calls.append(self.target)
            def request(self, method, path, body, headers):
                calls.append((method, path, body, headers))
            def getresponse(self): return Response()
            def close(self): pass
        calls = []
        with patch.object(api, "_resolve_target", return_value=("api.example.com", 443, ["8.8.8.8"], "/items")), \
             patch.object(api, "_PinnedHTTPSConnection", Connection):
            with self.assertRaisesRegex(api.ApiConnectionError, "redirect"):
                api.request_public_api("https://api.example.com/items", "POST", "Bearer token", "secret", body=b"[]")
        self.assertEqual(calls[0], ("api.example.com", "8.8.8.8", 443))
        self.assertEqual(calls[1][3]["Authorization"], "Bearer secret")
        self.assertEqual(len(calls), 2)

    def test_payload_formats_and_size_limit(self):
        data = pd.DataFrame({"id": [1, 2], "name": ["A", None]})
        with patch.object(api, "request_public_api", return_value=(b"", 202)) as request:
            self.assertEqual(api.push_api_data("https://example.com", data), 202)
            self.assertEqual(json.loads(request.call_args.args[5]), [
                {"id": 1, "name": "A"}, {"id": 2, "name": None}
            ])
            self.assertEqual(request.call_args.args[6], "application/json")
            api.push_api_data("https://example.com", data, "PUT", "CSV")
            self.assertTrue(request.call_args.args[5].startswith(b"id,name"))
        with self.assertRaisesRegex(api.ApiConnectionError, "10 MB"):
            api.request_public_api("https://example.com", "POST", body=b"x" * (api.MAX_API_BYTES + 1))
        with self.assertRaises(api.ApiConnectionError):
            api._auth_headers("API key header", "key", "Host")


class ApiUiTests(unittest.TestCase):
    def setUp(self):
        self.app = signed_in(AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=45)).run()
        self.assertFalse(self.app.exception)

    def find(self, kind, label):
        return next(widget for widget in getattr(self.app, kind) if widget.label == label)

    def test_sample_load_with_live_push_disabled(self):
        frame = pd.DataFrame({"id": [1, 2], "name": ["Ada", "Sam"]})
        with patch.object(api_settings, "fetch_api_data", return_value=frame) as fetch, \
             patch.object(api_settings, "push_api_data", return_value=202) as push:
            self.find("button", "Try sample API").click().run()
            self.assertFalse(self.app.exception)
            self.assertEqual(fetch.call_count, 1)
            self.assertEqual(len(self.app.session_state["inspector_datasets"]["API sample"]), 2)
            self.assertTrue(self.find("button", "Push data to API").disabled)
            self.find("checkbox", "I reviewed all columns for sensitive data").check().run()
            self.assertTrue(self.find("button", "Push data to API").disabled)
            self.find("checkbox", "Ready to submit this version to the demo data owner").check().run()
            self.find("button", "Submit for review").click().run()
            self.assertFalse(self.app.exception)
            self.assertTrue(self.find("button", "Push data to API").disabled)
            push.assert_not_called()

    def test_source_error_does_not_replace_existing_data(self):
        load_test_fixture(self.app)
        self.find("text_input", "Source API URL").set_value("https://example.com/data").run()
        with patch.object(api_settings, "fetch_api_data", side_effect=api.ApiConnectionError("Source failed")):
            self.find("button", "Load data from API").click().run()
        self.assertFalse(self.app.exception)
        self.assertIn("Sample messy dataset", self.app.session_state["inspector_datasets"])
        self.assertTrue(any("Source failed" in item.value for item in self.app.error))

    def test_fixed_copy_keeps_live_push_disabled(self):
        load_test_fixture(self.app)
        self.find("checkbox", "I reviewed all columns for sensitive data").check().run()
        self.find("button", "Apply selected fixes").click().run()
        self.assertTrue(self.find("button", "Push data to API").disabled)
        with patch.object(api_settings, "push_api_data", return_value=200) as push:
            self.app.run()
            self.assertFalse(self.app.exception)
            push.assert_not_called()
            self.assertEqual(len(self.app.session_state["fixed_datasets"]["Sample messy dataset"]), 49)


if __name__ == "__main__":
    unittest.main()
