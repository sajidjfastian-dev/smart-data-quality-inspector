"""Focused OIDC protocol, ownership and session-expiry regression checks."""
import time
import unittest
from contextlib import ExitStack
from copy import deepcopy
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

import httpx
from authlib.jose import JsonWebKey, JsonWebToken
from starlette.applications import Starlette
from starlette.testclient import TestClient

import account_auth as auth
from account_identity import owns, public_example
import request_workflow as flow
from tests.test_request_workflow import payload


class OIDCProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = JsonWebKey.generate_key("RSA", 2048, is_private=True, options={"kid": "test"})

    def setUp(self):
        self.records = {}
        self.claim_updates = {}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict("os.environ", {
            "REPLIT_DEV_DOMAIN": "preview.example", "REPL_ID": "test-client",
            "REPLIT_AUTH_CLIENT_ID": "", "AUTH_PUBLIC_ORIGIN": "https://published.example",
        }))
        self.stack.enter_context(patch.object(auth, "put_record", self.put))
        self.stack.enter_context(patch.object(auth, "get_record", self.get))
        self.stack.enter_context(patch.object(auth, "revoke", lambda token: self.records.pop(token, None)))
        real_http = httpx.AsyncClient
        real_oauth = auth.AsyncOAuth2Client
        transport = httpx.MockTransport(self.provider)
        self.stack.enter_context(patch.object(auth, "AsyncClient",
                                             lambda **kw: real_http(transport=transport, **kw)))
        self.stack.enter_context(patch.object(auth, "AsyncOAuth2Client",
                                             lambda *a, **kw: real_oauth(*a, transport=transport, **kw)))
        self.client = TestClient(Starlette(routes=auth.ROUTES), base_url="https://preview.example")
        self.addCleanup(self.client.close)

    def put(self, token, kind, value, seconds):
        self.records[token] = (kind, value, time.time() + seconds)

    def get(self, token, kind, consume=False):
        entry = self.records.pop(token, None) if consume else self.records.get(token)
        return entry[1] if entry and entry[0] == kind and entry[2] > time.time() else None

    def provider(self, request):
        if request.url.path.endswith("openid-configuration"):
            return httpx.Response(200, json={
                "issuer": auth.ISSUER, "authorization_endpoint": auth.ISSUER + "/auth",
                "token_endpoint": auth.ISSUER + "/token", "jwks_uri": auth.ISSUER + "/jwks",
            })
        if request.url.path.endswith("/jwks"):
            return httpx.Response(200, json={"keys": [self.key.as_dict(is_private=False)]})
        if request.url.path.endswith("/token"):
            body = parse_qs(request.content.decode())
            self.assertEqual(body["code_verifier"], [self.verifier])
            self.assertEqual(body["redirect_uri"], ["https://preview.example/auth/callback"])
            claims = {
                "iss": auth.ISSUER, "aud": "test-client", "sub": "account-a", "username": "alice",
                "first_name": "Alice", "last_name": "Account", "nonce": self.nonce,
                "iat": int(time.time()), "exp": int(time.time()) + 300,
            }
            claims.update(self.claim_updates)
            encoded = JsonWebToken(["RS256"]).encode({"alg": "RS256", "kid": "test"}, claims, self.key)
            return httpx.Response(200, json={"id_token": encoded.decode(), "access_token": "test-access",
                                            "token_type": "Bearer"})
        raise AssertionError("Unexpected provider endpoint")

    def start(self):
        response = self.client.get("/auth/login", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        cookie = response.headers["set-cookie"]
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        params = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.nonce = params["nonce"][0]
        self.state = params["state"][0]
        record = next(item[1] for item in self.records.values() if item[0] == "login")
        self.verifier = record["verifier"]
        return response

    def finish(self, **params):
        return self.client.get("/auth/callback", params={"code": "one-use-code", "state": self.state, **params},
                               follow_redirects=False)

    def test_verified_profile_and_one_use_callback(self):
        self.start()
        response = self.finish()
        self.assertEqual(response.status_code, 303)
        cookie = self.client.cookies.get(auth.COOKIE)
        identity = auth.session_identity(cookie)
        self.assertEqual(identity, {"subject": "account-a", "username": "alice", "name": "Alice Account"})
        self.assertNotIn("test-access", repr(self.records))
        self.assertEqual(self.finish().status_code, 400)

    def test_username_fallback(self):
        self.assertEqual(auth.profile({"sub": "one", "username": "handle"})["name"], "handle")

    def test_rejects_state_nonce_issuer_audience_and_expiry(self):
        for update in ({"nonce": "forged"}, {"iss": "https://evil.example"}, {"aud": "another-client"},
                       {"exp": int(time.time()) - 300}):
            with self.subTest(update=update):
                self.start()
                self.claim_updates = update
                self.assertEqual(self.finish().status_code, 400)
        self.start()
        self.assertEqual(self.finish(state="forged").status_code, 400)

    def test_missing_cookie_unknown_host_and_provider_error(self):
        self.state = "unsolicited"
        self.assertEqual(self.finish().status_code, 400)
        self.assertEqual(self.client.get("/auth/login", headers={"host": "evil.example"}).status_code, 400)
        self.start()
        self.assertEqual(self.finish(error="access_denied").status_code, 400)

    def test_new_login_revokes_old_session(self):
        self.start()
        self.finish()
        old = self.client.cookies.get(auth.COOKIE)
        self.assertIsNotNone(auth.session_identity(old))
        self.start()
        self.assertIsNone(auth.session_identity(old))

    def test_expired_transaction(self):
        self.start()
        for key, (kind, value, _) in list(self.records.items()):
            self.records[key] = (kind, value, 0)
        self.assertEqual(self.finish().status_code, 400)


class AuthenticatedOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.identity = {"subject": "account-a", "name": "Same Name", "username": "a"}
        self.patch = patch.object(auth, "session_identity", lambda token: self.identity if token == "valid" else None)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.state = {"demo_user": "Same Name", "demo_role": "Submitter",
                      "auth_subject": "account-a", "_auth_session": "valid"}
        self.ref = flow.new_request(self.state)
        flow.save_draft(self.state, self.ref, payload())

    def test_matching_names_do_not_grant_access(self):
        record = self.state["demo_requests"][self.ref]
        other = dict(self.state, auth_subject="account-b")
        self.assertFalse(owns(other, record))
        legacy = dict(record)
        legacy.pop("owner_id")
        self.assertFalse(owns(self.state, legacy))
        with self.assertRaises(flow.WorkflowError):
            flow.open_draft(other, self.ref)
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(other, self.ref, 1)
        with self.assertRaises(flow.WorkflowError):
            flow.demo_review_action(other, self.ref, 1, "approve")

    def test_unverified_display_name_is_not_a_session(self):
        with self.assertRaises(flow.WorkflowError):
            flow.new_request({"demo_user": "Same Name", "demo_role": "Submitter"})
        self.assertFalse(owns({"demo_user": "Same Name"}, {"submitted_by": "Same Name"}))

    def test_renamed_profile_retains_subject_ownership(self):
        self.state["demo_user"] = "New Name"
        self.assertTrue(owns(self.state, self.state["demo_requests"][self.ref]))

    def test_expired_session_cannot_submit_or_download(self):
        self.identity = None
        with self.assertRaises(flow.WorkflowError):
            flow.submit(self.state, self.ref)
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(self.state, self.ref, 1)

    def test_approval_order_and_masking_remain_required(self):
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(self.state, self.ref, 1)
        flow.submit(self.state, self.ref)
        flow.demo_review_action(self.state, self.ref, 1, "approve")
        flow.demo_review_action(self.state, self.ref, 1, "ticket")
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(self.state, self.ref, 1)
        flow.demo_review_action(self.state, self.ref, 1, "cab")
        data = flow.approved_download(self.state, self.ref, 1)
        self.assertNotIn(b"Alice", data)
        flow.current(self.state, self.ref)["snapshot"]["selected"].iloc[0, 1] = 900
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(self.state, self.ref, 1)

    def test_public_examples_are_never_owned_by_name(self):
        example = {"submitted_by": "Same Name", "synthetic": True, "source_id": "quality-v1",
                   "session_id": "DEMO-HISTORY-01"}
        self.assertTrue(public_example(example))
        self.assertFalse(owns(self.state, example))
        self.state["demo_requests"]["public"] = example
        for operation in (
            lambda: flow.open_draft(self.state, "public"),
            lambda: flow.revise(self.state, "public"),
            lambda: flow.demo_review_action(self.state, "public", 1, "approve"),
            lambda: flow.approved_download(self.state, "public", 1),
        ):
            with self.assertRaises(flow.WorkflowError):
                operation()
        example["owner_id"] = "account-b"
        self.assertFalse(public_example(example))


class StreamlitAccountBoundaryTests(unittest.TestCase):
    def test_switch_expiry_and_logout_erase_private_state(self):
        import demo_session
        state = {"interface_language": "English", "demo_user": "Same Name", "auth_subject": "old",
                 "_auth_session": "old-token", "inspector_datasets": {"private": "sensitive"},
                 "private_approval_evidence": {"proof": b"private"}, "assistant_history": ["private"],
                 "business_rules": ["private"]}
        cookies = {auth.COOKIE: "new-token"}
        fake_native = SimpleNamespace(session_state=state, context=SimpleNamespace(cookies=cookies))
        identity = {"subject": "new", "name": "Same Name", "username": "new-account"}
        with patch.object(demo_session, "native", fake_native), patch.object(demo_session, "bind"), \
                patch.object(demo_session, "session_identity", return_value=identity), \
                patch.object(demo_session, "revoke") as revoke:
            demo_session.sync_account()
            self.assertEqual(state["auth_subject"], "new")
            for field in ("inspector_datasets", "private_approval_evidence", "assistant_history", "business_rules"):
                self.assertNotIn(field, state)
            self.assertEqual(state["interface_language"], "English")
            demo_session.sign_out()
            revoke.assert_called_once_with("new-token")
            self.assertNotIn("auth_subject", state)
        state.update(demo_user="Forged display name", auth_subject="old", _auth_session="expired",
                     inspector_datasets={"private": "sensitive"})
        with patch.object(demo_session, "native", fake_native), patch.object(demo_session, "bind"), \
                patch.object(demo_session, "session_identity", return_value=None):
            demo_session.sync_account()
            self.assertNotIn("inspector_datasets", state)
            self.assertFalse(demo_session.is_signed_in())

    def test_resource_routes_require_session_and_ownership(self):
        from starlette.middleware import Middleware
        from starlette.responses import Response
        from starlette.routing import Route
        async def content(request):
            return Response("private")
        application = Starlette(
            routes=[Route("/media/{filename}", content)],
            middleware=[Middleware(auth.AccountResourceGuard)],
        )
        with TestClient(application, base_url="https://preview.example") as client:
            with patch.object(auth, "session_identity", return_value=None):
                self.assertEqual(client.get("/media/private.csv").status_code, 401)
            with patch.object(auth, "session_identity", return_value={"subject": "b"}), \
                    patch("account_resources.allowed", return_value=False):
                self.assertEqual(client.get("/media/private.csv").status_code, 403)
            with patch.object(auth, "session_identity", return_value={"subject": "a"}), \
                    patch("account_resources.allowed", return_value=True):
                response = client.get("/media/private.csv")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")

    def test_resource_binding_does_not_share_between_accounts(self):
        import account_resources as resources
        import threading
        manager = SimpleNamespace(
            _lock=threading.Lock(),
            _files_by_session_and_coord={"stream-a": {"button": "file-a"}},
        )
        runtime = SimpleNamespace(media_file_mgr=manager)
        with patch.object(resources, "_bindings", {"stream-a": (resources.token_key("token-a"), time.time()+60)}), \
                patch("streamlit.runtime.get_instance", return_value=runtime):
            self.assertTrue(resources.allowed("/media/file-a.csv", "token-a"))
            self.assertFalse(resources.allowed("/media/file-a.csv", "token-b"))
            self.assertTrue(resources.allowed("/_stcore/upload_file/stream-a/file", "token-a"))
            self.assertFalse(resources.allowed("/_stcore/upload_file/stream-a/file", "token-b"))

    def test_real_streamlit_manager_authorizes_materialized_downloads(self):
        import account_resources as resources
        from streamlit.runtime.memory_media_file_storage import MemoryMediaFileStorage
        from streamlit.runtime.media_file_manager import MediaFileManager
        manager = MediaFileManager(MemoryMediaFileStorage("/media"))
        with patch("streamlit.runtime.media_file_manager._get_session_id", return_value="stream-a"):
            # This is the manager path used by eager st.download_button bytes.
            url = manager.add(b"masked,csv\n1,2\n", "text/csv", "clean-copy", "clean.csv", True)
            placeholder = manager.add_deferred(lambda: b"deferred", "text/csv", "legacy", "old.csv")
        runtime = SimpleNamespace(media_file_mgr=manager)
        with patch("streamlit.runtime.get_instance", return_value=runtime), \
                patch("streamlit.runtime.scriptrunner.get_script_run_ctx",
                      return_value=SimpleNamespace(session_id="stream-a")):
            resources.bind("token-a")
        with patch("streamlit.runtime.media_file_manager._get_session_id", return_value="stream-a"):
            deferred_url = manager.execute_deferred(placeholder)
        with patch.object(resources, "_bindings", {"stream-a": (resources.token_key("token-a"), time.time()+60)}), \
                patch("streamlit.runtime.get_instance", return_value=SimpleNamespace(media_file_mgr=manager)):
            self.assertTrue(resources.allowed(url, "token-a"))
            self.assertFalse(resources.allowed(url, "token-b"))
            self.assertTrue(resources.allowed(deferred_url, "token-a"))
            self.assertFalse(resources.allowed(deferred_url, "token-b"))
        import ast
        from pathlib import Path
        for file in ("app.py", "issue_workspace.py"):
            tree = ast.parse(Path(file).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "download_button":
                    for argument in node.keywords:
                        if argument.arg == "data":
                            self.assertNotIsInstance(argument.value, ast.Lambda)
                            self.assertFalse(isinstance(argument.value, ast.Name)
                                             and argument.value.id == "build_cleaned_csv_download")

    def test_public_and_personal_sample_details_in_both_languages(self):
        from streamlit.testing.v1 import AppTest
        from localization import translate
        from public_sample import ATTRIBUTION, NOTICE
        script = '''
import streamlit as st
import request_workflow as flow
from tests.test_request_workflow import payload
from request_details import render_request_details
from public_sample import SOURCE_ID
st.session_state["interface_language"] = LOCALE
seed = flow.sample_seed_state("Sample submitter")
reference = flow.new_request(seed)
flow.save_draft(seed, reference, payload())
flow.submit(seed, reference)
record = seed["demo_requests"][reference]
record.update(synthetic=True, source_id=SOURCE_ID, session_id="DEMO-HISTORY-TEST")
if PERSONAL:
    record.update(owner_id="different-account", sample_copy_of="public-reference")
state = {"demo_user": "Different account", "auth_subject": "different-account",
         "_auth_session": "valid", "demo_role": "Submitter", "demo_requests": {reference: record}}
render_request_details(state, reference)
'''
        for locale in ("English", "العربية"):
            for personal in (False, True):
                with self.subTest(locale=locale, personal=personal):
                    source = script.replace("LOCALE", repr(locale)).replace("PERSONAL", repr(personal))
                    with patch.object(auth, "session_identity", return_value={"subject": "different-account"}):
                        app = AppTest.from_string(source, default_timeout=30).run()
                    self.assertEqual([error.message for error in app.exception], [])
                    self.assertTrue(app.header)
                    self.assertIn(translate("Request timeline", locale), [heading.value for heading in app.subheader])
                    info = [element.value for element in app.info]
                    self.assertNotIn("Public sample example · read-only · not your request", info)
                    self.assertNotIn("مثال بيانات عامة · للقراءة فقط · ليس طلبك", info)
                    self.assertEqual(
                        translate("Personal sample copy · approval history is simulated.", locale) in info,
                        personal,
                    )
                    captions = [element.value for element in app.caption]
                    self.assertIn(ATTRIBUTION + " " + NOTICE, captions)
                    self.assertIn(translate("No real service-desk request or production change is performed.", locale),
                                  captions)
                    if not personal:
                        self.assertFalse(any(str(button.key).startswith("evidence_download")
                                             for button in app.get("download_button")))
                        self.assertFalse(any(str(button.key).startswith(("continue_", "revise_"))
                                             for button in app.button))
                        self.assertTrue(any(str(button.key).startswith("owner_yes_") for button in app.button))
                        for button in app.button:
                            if str(button.key).startswith(("owner_yes_", "owner_no_")):
                                self.assertTrue(button.disabled)


if __name__ == "__main__":
    unittest.main()
