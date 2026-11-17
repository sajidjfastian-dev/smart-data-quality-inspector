"""Start AppTest sessions in the demo signed-in state that data intake requires."""

from demo_session import DEMO_USER


def signed_in(app):
    app.session_state["demo_user"] = DEMO_USER
    return app
