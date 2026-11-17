"""Start AppTest sessions in the demo signed-in state that data intake requires."""

from demo_session import DEMO_USER


def signed_in(app):
    app.session_state["demo_user"] = DEMO_USER
    # Existing inspection tests exercise isolated private sessions. Dedicated
    # persistence tests cover real sign-in and PostgreSQL-backed examples.
    app.session_state["_persistent_demo_ready"] = True
    return app
