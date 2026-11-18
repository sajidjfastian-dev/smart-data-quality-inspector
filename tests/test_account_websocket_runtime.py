"""Run in a fresh Python process: real Streamlit WebSockets and widget callbacks."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import streamlit as st
from starlette.middleware import Middleware
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg

from account_auth import AccountResourceGuard, COOKIE


class RuntimeReconnectTests(unittest.TestCase):
    def test_cross_account_anonymous_and_revoked_reconnects_never_run_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "app.py"
            output = Path(directory) / "approval.txt"
            script.write_text(f'''
import streamlit as st
from demo_session import sync_account
from request_workflow import require_role
sync_account()
def approve():
    require_role(st.session_state, "Submitter")
    with open({str(output)!r}, "w") as target:
        target.write("approved")
st.button("Pending approval", key="pending_approval", on_click=approve)
''')
            identities = {"a"*64: {"subject": "account-a", "name": "Same Name", "username": "a"},
                          "b"*64: {"subject": "account-b", "name": "Same Name", "username": "b"}}
            def identity(token):
                return identities.get(token)
            application = st.App(str(script), middleware=[Middleware(AccountResourceGuard)])
            with patch("account_auth.session_identity", side_effect=identity), \
                    patch("demo_session.session_identity", side_effect=identity), \
                    TestClient(application, base_url="https://testserver") as client:
                def connect(token=None, session=None):
                    protocols = ["streamlit", "xsrf-placeholder"]
                    if session:
                        protocols.append(session)
                    headers = {"cookie": f"{COOKIE}={token}"} if token else {}
                    # A forged runtime identity must be stripped, too.
                    headers["x-dq-account-session"] = "forged"
                    return client.websocket_connect("/_stcore/stream", subprotocols=protocols, headers=headers)
                with connect("a"*64) as owner:
                    rerun = BackMsg()
                    rerun.rerun_script.query_string = ""
                    owner.send_bytes(rerun.SerializeToString())
                    session_id, button_id = None, None
                    for _ in range(100):
                        message = ForwardMsg.FromString(owner.receive_bytes())
                        kind = message.WhichOneof("type")
                        if kind == "new_session":
                            session_id = message.new_session.initialize.session_id
                        if kind == "delta" and message.delta.new_element.HasField("button"):
                            button_id = message.delta.new_element.button.id
                        if kind == "script_finished":
                            break
                    self.assertTrue(session_id)
                    self.assertTrue(button_id)
                    from account_resources import can_resume
                    self.assertTrue(can_resume(session_id, "a"*64))
                    self.assertFalse(can_resume(session_id, "b"*64))
                    callback = BackMsg()
                    widget = callback.rerun_script.widget_states.widgets.add()
                    widget.id = button_id
                    widget.trigger_value = True
                    # Neither another account nor a guest can connect to A's
                    # active session, let alone deliver a preserved callback.
                    for attacker in ("b"*64, None):
                        with self.assertRaises(WebSocketDisconnect) as refused:
                            with connect(attacker, session_id) as connection:
                                connection.send_bytes(callback.SerializeToString())
                        self.assertEqual(refused.exception.code, 4403)
                    self.assertFalse(output.exists())
                    # Unknown guest reconnect IDs are discarded, not resumed;
                    # even a supplied old callback cannot inherit A's state.
                    with connect(None, "unknown-guest-session") as guest:
                        guest.send_bytes(callback.SerializeToString())
                        for _ in range(100):
                            message = ForwardMsg.FromString(guest.receive_bytes())
                            if message.WhichOneof("type") == "new_session":
                                self.assertNotEqual(message.new_session.initialize.session_id, session_id)
                            if message.WhichOneof("type") == "script_finished":
                                break
                    self.assertFalse(output.exists())
                    # Revocation is enforced on an already-connected socket,
                    # before the preserved widget callback can execute.
                    identities.pop("a"*64)
                    owner.send_bytes(callback.SerializeToString())
                    with self.assertRaises(WebSocketDisconnect) as refused:
                        # Initialization/status messages may still be queued
                        # ahead of the close frame.
                        for _ in range(100):
                            owner.receive_bytes()
                    self.assertEqual(refused.exception.code, 4401)
                    self.assertFalse(output.exists())
                with self.assertRaises(WebSocketDisconnect):
                    with connect("a"*64, session_id):
                        pass


if __name__ == "__main__":
    unittest.main()
