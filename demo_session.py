"""Verified account bridge for Streamlit; demo roles concern approvals only."""
import os

from localization import native
from account_auth import COOKIE, session_identity, revoke
from account_resources import bind
from demo_store import DemoStoreError
from account_identity import _LOCAL_DEMO_CAPABILITY, is_local_demo


def local_demo_login_enabled():
    return os.environ.get("SMART_DQ_DEMO_LOGIN_ENABLED", "").lower() in ("1", "true", "yes")


def clear_workspace():
    bind(None)
    state = native.session_state
    language = state.get("interface_language")
    state.clear()
    if language:
        state["interface_language"] = language


def sync_account():
    if local_demo_login_enabled():
        if is_local_demo(native.session_state):
            return
        if native.session_state.get("demo_user") or native.session_state.get("_auth_session"):
            clear_workspace()
        return
    pending = native.session_state.get("_logout_pending")
    if pending:
        try:
            revoke(pending)
            native.session_state.pop("_logout_pending", None)
        except DemoStoreError:
            return
    token = native.context.cookies.get(COOKIE, "")
    identity = session_identity(token) if token else None
    prior = native.session_state.get("_auth_session")
    if not identity:
        if native.session_state.get("demo_user") or prior:
            clear_workspace()
        return
    if prior != token or native.session_state.get("auth_subject") != identity["subject"]:
        clear_workspace()
        native.session_state.update(
            auth_subject=identity["subject"], _auth_session=token, demo_user=identity["name"],
            account_username=identity["username"], demo_role="Submitter", workspace_page="requests",
        )
    else:
        native.session_state["demo_user"] = identity["name"]
    bind(token)


def signed_in_user():
    state = native.session_state
    if is_local_demo(state):
        return state.get("demo_user") if local_demo_login_enabled() else None
    return state.get("demo_user") if state.get("auth_subject") else None


def is_signed_in():
    return bool(signed_in_user())


def is_local_demo_session():
    return local_demo_login_enabled() and is_local_demo(native.session_state)


def sign_in_as_demo():
    if not local_demo_login_enabled():
        raise RuntimeError("Local demo login is disabled.")
    clear_workspace()
    native.session_state.update(
        auth_subject="local-demo",
        demo_user="Demo User",
        demo_role="Submitter",
        workspace_page="inspection",
        _local_demo_capability=_LOCAL_DEMO_CAPABILITY,
        _business_rules_version=0,
        business_rules=[],
        account_notice="signed_in",
    )


def sign_out():
    if is_local_demo_session():
        clear_workspace()
        native.session_state["account_notice"] = "signed_out"
        return
    token = native.session_state.get("_auth_session")
    try:
        revoke(token)
    except DemoStoreError:
        clear_workspace()
        native.session_state["_logout_pending"] = token
        native.session_state["account_notice"] = "sign_out_pending"
    else:
        clear_workspace()
        native.session_state["account_notice"] = "signed_out"


@native.fragment(run_every=30)
def watch_account():
    if is_local_demo_session():
        return
    token = native.session_state.get("_auth_session")
    if token and not session_identity(token):
        clear_workspace()
        native.rerun(scope="app")
