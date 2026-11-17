"""Demonstration sign-in state for presentations.

This is not authentication: no credentials are collected or verified, and it
never grants access to stored inspection history. It only gates data intake in
the current browser session so the demo can show a signed-in flow.
"""

from localization import native

DEMO_USER = "Sajid"
_PRESERVED_ON_SIGN_OUT = ("interface_language",)


def signed_in_user():
    return native.session_state.get("demo_user")


def is_signed_in():
    return bool(signed_in_user())


def sign_in():
    native.session_state["demo_user"] = DEMO_USER
    native.session_state["account_notice"] = "signed_in"
    native.session_state["workspace_page"] = "requests"
    native.session_state["demo_role"] = "Submitter"


def sign_out():
    """Clear the whole session (data, fixes, settings) except interface language."""
    state = native.session_state
    kept = {key: state[key] for key in _PRESERVED_ON_SIGN_OUT if key in state}
    for key in list(state.keys()):
        del state[key]
    state.update(kept)
    state["account_notice"] = "signed_out"
