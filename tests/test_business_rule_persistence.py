"""Account isolation, durable rule lifecycle, and concurrency regressions."""
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from psycopg import sql
from psycopg.types.json import Jsonb
from streamlit.testing.v1 import AppTest

import account_auth
import business_rule_store as store
import demo_store
from demo_store import DemoConflict, DemoStoreError


def rule(**kwargs):
    result = dict(id="rule1", column="status", kind="Value mapping",
                  expected='{"old":"new"}', mode="Correct automatically",
                  enabled=True, business=True)
    result.update(kwargs)
    return result


class DatabasePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.schema = "dq_rules_test_" + uuid4().hex
        self.original_connection = demo_store.connection
        with self.original_connection() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(self.schema)))

        @contextmanager
        def isolated():
            with self.original_connection() as conn:
                conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(self.schema)))
                yield conn
        self.connection = isolated
        with isolated() as conn:
            conn.execute((Path(__file__).resolve().parents[1] / "scripts/demo_schema.sql").read_text())
        self.patcher = patch.object(store, "connection", isolated)
        self.patcher.start()
        self.a, self.b = uuid4().hex + uuid4().hex, uuid4().hex + uuid4().hex
        self.add_session(self.a, "account-a")
        self.add_session(self.b, "account-b")

    def tearDown(self):
        self.patcher.stop()
        with self.original_connection() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(self.schema)))

    def add_session(self, token, subject, expired=False):
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO dq_auth_records(token_hash,kind,payload,expires_at)
                   VALUES (%s,'session',%s,now() + (%s * interval '1 hour'))""",
                (account_auth.digest(token), Jsonb({"subject": subject}), -1 if expired else 1),
            )

    def test_lifecycle_is_private_and_only_rule_fields_are_stored(self):
        self.assertEqual(store.load(self.a, "account-a"), ([], 0))
        submitted = rule(extra_uploaded_data="must not be persisted")
        saved, version = store.save(self.a, "account-a", [submitted], 0)
        self.assertNotIn("extra_uploaded_data", saved[0])
        self.assertEqual(store.load(self.a, "account-a"), (saved, version))
        self.assertEqual(store.load(self.b, "account-b"), ([], 0))
        with self.assertRaises(DemoStoreError):
            store.load(self.b, "account-a")
        second_token = uuid4().hex + uuid4().hex
        self.add_session(second_token, "account-a")
        self.assertEqual(store.load(second_token, "account-a"), (saved, version))
        edited = rule(expected='{"old":"updated"}')
        _, version = store.save(second_token, "account-a", [edited], version)
        self.assertEqual(store.load(self.a, "account-a")[0], [edited])
        _, version = store.save(self.a, "account-a", [], version)
        self.assertEqual(store.load(second_token, "account-a"), ([], version))
        with self.connection() as conn:
            row = conn.execute("SELECT rules FROM dq_account_business_rules WHERE owner_id=%s", ("account-a",)).fetchone()
            self.assertEqual(row["rules"], [])

    def test_revoked_and_expired_sessions_cannot_load_or_save(self):
        expired = uuid4().hex + uuid4().hex
        self.add_session(expired, "account-a", expired=True)
        for token in (expired, "invalid", self.b):
            with self.assertRaises(DemoStoreError):
                store.load(token, "account-a")
            with self.assertRaises(DemoStoreError):
                store.save(token, "account-a", [rule()], 0)
        with self.connection() as conn:
            conn.execute("DELETE FROM dq_auth_records WHERE token_hash=%s", (account_auth.digest(self.a),))
        with self.assertRaises(DemoStoreError):
            store.save(self.a, "account-a", [rule()], 0)

    def test_concurrent_edits_and_delete_do_not_overwrite(self):
        _, version = store.save(self.a, "account-a", [rule()], 0)
        second = uuid4().hex + uuid4().hex
        self.add_session(second, "account-a")
        self.assertEqual(store.load(second, "account-a")[1], version)
        edited = [rule(expected='{"old":"other"}')]
        _, new_version = store.save(self.a, "account-a", edited, version)
        with self.assertRaises(DemoConflict):
            store.save(second, "account-a", [], version)
        self.assertEqual(store.load(second, "account-a"), (edited, new_version))
        with self.assertRaises(DemoConflict):
            store.save(second, "account-a", [rule()], 0)

    def test_invalid_definitions_are_rejected_without_overwriting(self):
        _, version = store.save(self.a, "account-a", [rule()], 0)
        for invalid in ([rule(expected="bad json")], [rule(), rule()], [rule(column="")]):
            with self.assertRaises(ValueError):
                store.save(self.a, "account-a", invalid, version)
        self.assertEqual(store.load(self.a, "account-a"), ([rule()], version))

    def test_new_signed_in_workspace_loads_rules_without_uploaded_data(self):
        saved, _ = store.save(self.a, "account-a", [rule()], 0)
        token = uuid4().hex + uuid4().hex
        self.add_session(token, "account-a")
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=60)
        app.session_state["auth_subject"] = "account-a"
        app.session_state["_auth_session"] = token
        app.session_state["demo_user"] = "Account A"
        app.session_state["demo_role"] = "Submitter"
        app.session_state["workspace_page"] = "inspection"
        app.session_state["_persistent_demo_ready"] = True
        with patch("demo_session.sync_account"), patch("demo_session.watch_account"), \
                patch("account_auth.session_identity", return_value={"subject": "account-a"}):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["business_rules"], saved)
        self.assertNotIn("inspector_datasets", app.session_state)
        self.assertIn("Business rule", [widget.label for widget in app.text_input])
        self.assertIn("Edit", [widget.label for widget in app.button])

    def test_text_editor_saves_edits_and_deletes_in_database(self):
        script = """
import streamlit as st
from business_rule_store import load_into_state
from business_rules import render_editor
if '_business_rules_version' not in st.session_state:
    load_into_state(st.session_state)
render_editor(st, st.session_state)
"""
        editor = AppTest.from_string(script)
        editor.session_state["auth_subject"] = "account-a"
        editor.session_state["_auth_session"] = self.a
        editor.run()
        next(w for w in editor.text_input if w.label == "Business rule").set_value("status must contain ready")
        next(w for w in editor.button if w.label == "Add business rule").click().run()
        self.assertFalse(editor.exception)
        self.assertEqual(store.load(self.a, "account-a")[0][0]["expected"], "ready")
        next(w for w in editor.button if w.label == "Edit").click().run()
        next(w for w in editor.text_input if w.label == "Business rule").set_value("status must contain complete")
        next(w for w in editor.button if w.label == "Save business rule").click().run()
        self.assertFalse(editor.exception)
        self.assertEqual(store.load(self.a, "account-a")[0][0]["expected"], "complete")
        next(w for w in editor.button if w.label == "Delete").click().run()
        self.assertFalse(editor.exception)
        self.assertEqual(store.load(self.a, "account-a")[0], [])


class FailureUiTests(unittest.TestCase):
    def test_failed_save_keeps_current_rules_and_existing_preview(self):
        script = """
import streamlit as st
from business_rules import render_editor
st.session_state.setdefault('auth_subject', 'account')
st.session_state.setdefault('_auth_session', 'token')
st.session_state.setdefault('_business_rules_version', 0)
render_editor(st, st.session_state)
"""
        editor = AppTest.from_string(script).run()
        editor.session_state["fixed_datasets"] = {"private.csv": "unchanged"}
        next(w for w in editor.text_input if w.label == "Business rule").set_value("status must contain ready")
        with patch("business_rule_store.save", side_effect=DemoStoreError("unavailable")):
            next(w for w in editor.button if w.label == "Add business rule").click().run()
        self.assertFalse(editor.exception)
        self.assertEqual(editor.session_state["business_rules"], [])
        self.assertEqual(editor.session_state["fixed_datasets"], {"private.csv": "unchanged"})
        self.assertTrue(any("could not be saved" in e.value for e in editor.error))

    def test_conflict_reload_invalidates_previous_corrected_copy(self):
        script = """
import streamlit as st
from business_rules import render_editor
st.session_state.setdefault('auth_subject', 'account')
st.session_state.setdefault('_auth_session', 'token')
st.session_state.setdefault('_business_rules_version', 1)
render_editor(st, st.session_state)
"""
        editor = AppTest.from_string(script).run()
        editor.session_state["fixed_datasets"] = {"private.csv": "old"}
        next(w for w in editor.text_input if w.label == "Business rule").set_value("status must contain ready")
        with patch("business_rule_store.save", side_effect=DemoConflict("conflict")):
            next(w for w in editor.button if w.label == "Add business rule").click().run()
        self.assertFalse(editor.exception)
        self.assertTrue(editor.warning)
        self.assertEqual(editor.session_state["fixed_datasets"], {"private.csv": "old"})
        def reload(state):
            state["business_rules"] = [rule()]
            state["_business_rules_version"] = 2
        with patch("business_rule_store.load_into_state", side_effect=reload):
            next(w for w in editor.button if w.label == "Reload saved rules").click().run()
        self.assertFalse(editor.exception)
        self.assertEqual(editor.session_state["business_rules"], [rule()])
        self.assertEqual(editor.session_state["fixed_datasets"], {})
        self.assertNotIn("_business_rules_conflict", editor.session_state)

    def test_conflict_reload_preserves_manual_corrections(self):
        import pandas as pd
        script = """
import streamlit as st
from business_rules import render_editor
st.session_state.setdefault('auth_subject', 'account')
st.session_state.setdefault('_auth_session', 'token')
st.session_state.setdefault('_business_rules_version', 1)
render_editor(st, st.session_state)
"""
        editor = AppTest.from_string(script).run()
        editor.session_state["_business_rules_conflict"] = True
        editor.session_state["fixed_datasets"] = {"private.csv": "manual"}
        editor.session_state["fix_change_indexes"] = {"private.csv": {
            "changes": pd.DataFrame({"Change reason": ["Manual correction"]})}}
        editor.run()
        with patch("business_rule_store.load_into_state") as load:
            next(w for w in editor.button if w.label == "Reload saved rules").click().run()
        load.assert_not_called()
        self.assertEqual(editor.session_state["fixed_datasets"], {"private.csv": "manual"})
        self.assertTrue(any("manual corrections are preserved" in e.value for e in editor.error))


if __name__ == "__main__":
    unittest.main()
