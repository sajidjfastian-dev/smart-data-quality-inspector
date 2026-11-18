"""Verified-identity fixture for non-authentication AppTest unit checks.

These UI unit checks cannot perform a browser OIDC redirect. Authentication
itself is exercised by test_account_auth, not this fixture.
"""
from unittest.mock import patch
from copy import deepcopy

DEMO_USER = "Sajid"
TEST_SUBJECT = "apptest-account"
TEST_SESSION = "apptest-session"


def signed_in(app):
    app.session_state["auth_subject"] = TEST_SUBJECT
    app.session_state["_auth_session"] = TEST_SESSION
    app.session_state["demo_user"] = DEMO_USER
    app.session_state["demo_role"] = "Submitter"
    app.session_state["workspace_page"] = "inspection"
    # Existing inspection tests exercise isolated private sessions. Dedicated
    # persistence tests cover real sign-in and PostgreSQL-backed examples.
    app.session_state["_persistent_demo_ready"] = True
    app.session_state["_business_rules_version"] = 0
    if not getattr(app, "_account_fixture_installed", False):
        original_run = app._run
        identity = {"subject": TEST_SUBJECT, "name": DEMO_USER, "username": "apptest"}
        saved = {"rules": [], "version": 0}
        def save_rules(token, subject, rules, version):
            from demo_store import DemoConflict
            if version != saved["version"]:
                raise DemoConflict("conflict")
            saved["rules"] = deepcopy(rules)
            saved["version"] += 1
            return deepcopy(saved["rules"]), saved["version"]
        def load_rules(state):
            state["business_rules"] = deepcopy(saved["rules"])
            state["_business_rules_version"] = saved["version"]
        def verified_run(*args, **kwargs):
            with patch("demo_session.sync_account"), \
                    patch("demo_session.revoke"), \
                    patch("demo_session.session_identity", return_value=identity), \
                    patch("account_auth.session_identity", return_value=identity), \
                    patch("business_rule_store.save", side_effect=save_rules), \
                    patch("business_rule_store.load_into_state", side_effect=load_rules):
                return original_run(*args, **kwargs)
        app._run = verified_run
        app._account_fixture_installed = True
    return app
