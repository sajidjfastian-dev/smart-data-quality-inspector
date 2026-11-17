"""History preparation: privacy, identity isolation, expiry and setup gating."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from streamlit.testing.v1 import AppTest
from demo_login import signed_in

from inspection_history import (
    HistoryRepository, HistoryUnavailable, InspectionSummary, build_summary,
    current_history_owner, owner_key_for_verified_identity,
)


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = InspectionSummary(100, 8, 4, 1, 99, 1, 1, 0, 1, 0, ("missing", "email"))


class SummaryTests(unittest.TestCase):
    def test_summary_excludes_names_values_and_custom_rule_contents(self):
        issues = pd.DataFrame({
            "Issue Type": ["Invalid Email", "Custom: confidential rule", "Missing Value"],
            "Column Name": ["Sensitive Person", "private_account", "secret"],
            "Current Value": ["person@example.com", "4111111111111111", "private"],
        })
        summary = build_summary(10, 3, issues, 0, 90, {"email", "missing"}, True)
        text = json.dumps(asdict(summary))
        for secret in ("Sensitive Person", "private_account", "person@example.com", "confidential", "411111"):
            self.assertNotIn(secret, text)
        self.assertEqual(summary.custom_count, 1)
        self.assertEqual(summary.enabled_checks, ("custom", "email", "missing"))

    def test_identity_is_scoped_to_provider_and_disabled_by_default(self):
        self.assertIsNone(current_history_owner())
        self.assertNotEqual(owner_key_for_verified_identity("issuer-a", "subject"),
                            owner_key_for_verified_identity("issuer-b", "subject"))
        repository = HistoryRepository(connect=lambda: self.fail("Unauthenticated database access"))
        for owner in (None, "", "someone@example.com", "' OR 1=1"):
            with self.assertRaises(PermissionError):
                repository.list(owner)
            with self.assertRaises(PermissionError):
                repository.save(owner, uuid4(), SUMMARY)
            with self.assertRaises(PermissionError):
                repository.delete(owner, uuid4())

    def test_database_failure_is_safe(self):
        with patch("inspection_history.psycopg.connect", side_effect=psycopg.OperationalError("credential and raw detail")):
            with self.assertRaises(HistoryUnavailable) as error:
                HistoryRepository().list("a" * 64)
        self.assertNotIn("credential", str(error.exception))


class DatabaseHistoryTests(unittest.TestCase):
    def setUp(self):
        if not os.environ.get("DATABASE_URL"):
            self.skipTest("Development database required")
        # Temporary table shadows the real table; all test data is rolled back.
        self.connection = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        self.addCleanup(self.connection.close)
        self.connection.execute("CREATE TEMP TABLE inspection_history (LIKE public.inspection_history INCLUDING ALL) ON COMMIT DROP")

        @contextmanager
        def borrowed():
            yield self.connection

        self.repository = HistoryRepository(borrowed)
        self.owner_a, self.owner_b = "a" * 64, "b" * 64

    def test_isolation_and_idempotent_save(self):
        run = uuid4()
        self.assertTrue(self.repository.save(self.owner_a, run, SUMMARY))
        self.assertFalse(self.repository.save(self.owner_a, run, SUMMARY))
        records = self.repository.list(self.owner_a)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["expires_at"] - records[0]["created_at"], timedelta(days=30))
        self.assertEqual(self.repository.list(self.owner_b), [])
        self.assertFalse(self.repository.delete(self.owner_b, records[0]["id"]))
        self.assertEqual(len(self.repository.list(self.owner_a)), 1)
        self.assertTrue(self.repository.delete(self.owner_a, records[0]["id"]))
        self.assertEqual(self.repository.list(self.owner_a), [])

    def test_expired_records_are_removed(self):
        self.repository.save(self.owner_a, uuid4(), SUMMARY)
        self.connection.execute("""UPDATE inspection_history
            SET created_at = created_at - interval '31 days', expires_at = expires_at - interval '31 days'""")
        self.assertEqual(self.repository.list(self.owner_a), [])
        self.assertEqual(self.connection.execute("SELECT count(*) AS count FROM inspection_history").fetchone()["count"], 0)

    def test_scheduled_cleanup_entrypoint(self):
        self.repository.save(self.owner_a, uuid4(), SUMMARY)
        self.connection.execute("""UPDATE inspection_history
            SET created_at = created_at - interval '31 days', expires_at = expires_at - interval '31 days'""")
        self.assertEqual(self.repository.purge_expired(), 1)


class HistoryUiTests(unittest.TestCase):
    def test_save_disabled_and_inspection_remains_functional(self):
        with patch("inspection_history._connect", side_effect=AssertionError("Must not persist before SSO")):
            app = signed_in(AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)).run()
            app.session_state["inspector_datasets"] = {"private.csv": pd.DataFrame({"amount": [1, None, 1]})}
            app.session_state["active_dataset"] = "private.csv"
            app.run()
            self.assertFalse(app.exception)
            self.assertTrue(app.button(key="save_history_summary").disabled)
            self.assertIn("private.csv", app.session_state["quality_scan_cache"])


if __name__ == "__main__":
    unittest.main()
