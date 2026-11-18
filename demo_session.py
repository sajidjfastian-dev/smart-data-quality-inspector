"""Verified account bridge for Streamlit; demo roles concern approvals only."""
from localization import native
from account_auth import COOKIE, session_identity, revoke
from account_resources import bind
from demo_store import DemoStoreError

def clear_workspace():
    bind(None)
    state = native.session_state
    language = state.get("interface_language")
    state.clear()
    if language:
        state["interface_language"] = language


def sync_account():
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
    return native.session_state.get("demo_user") if native.session_state.get("auth_subject") else None


def is_signed_in():
    return bool(signed_in_user())


def sign_out():
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
    token = native.session_state.get("_auth_session")
    if token and not session_identity(token):
        clear_workspace()
        native.rerun(scope="app")
