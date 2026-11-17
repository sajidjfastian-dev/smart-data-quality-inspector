"""Presentation-only enhancements; data access and safeguards remain in app.py."""

import html
from pathlib import Path

from demo_session import sign_in, sign_out, signed_in_user
from localization import native, st, translate


def install_presentation_styles():
    css = (Path(__file__).parent / "assets" / "workspace_presentation.css").read_text(encoding="utf-8")
    native.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def show_login_notice():
    """Demo sign-in: no credentials are collected and history stays disabled."""
    @native.dialog(translate("Login"), width="small")
    def notice():
        def text(value):
            return html.escape(translate(value))

        native.markdown(
            '<div class="login-notice">'
            f'<div class="login-kicker">{text("Organisation access")}</div>'
            f'<h3>{text("Organisation SSO setup pending")}</h3>'
            f'<p>{text("Organisation sign-in is not connected yet, so no credentials are collected here. Continue to start a demo session as Sajid.")}</p>'
            '</div>', unsafe_allow_html=True,
        )
        native.caption(translate("Inspection history stays disabled in demo sessions until organisation SSO is configured."))
        if native.button(translate("Continue without signing in"), key="login_continue", type="primary", width="stretch"):
            sign_in()
            native.rerun()
        if native.button(translate("Close"), key="login_close", width="stretch"):
            native.rerun()

    notice()


def render_account_panel():
    """Bottom-of-sidebar account and settings controls; returns the settings anchor."""
    with native.container(key="account_panel"):
        user = signed_in_user()
        if user:
            name = html.escape(translate(user))
            native.markdown(
                '<div class="account-card">'
                f'<span class="account-avatar" aria-hidden="true">{name[:1]}</span>'
                f'<span class="account-text"><strong>{name}</strong>'
                f'<small>{html.escape(translate("Logged in · demo session"))}</small></span>'
                '</div>', unsafe_allow_html=True,
            )
        else:
            native.markdown(
                f'<div class="account-hint">{html.escape(translate("Log in to upload and inspect data."))}</div>',
                unsafe_allow_html=True,
            )
        with native.container(key="account_actions", horizontal=True, gap="small", vertical_alignment="center"):
            settings_anchor = native.container(key="settings_anchor", width="content")
            if user:
                native.button(
                    translate("Log out"), key="sidebar_logout", icon=":material/logout:",
                    width="stretch", on_click=sign_out,
                )
            elif native.button(translate("Login"), key="sidebar_login", icon=":material/login:", type="primary", width="stretch"):
                show_login_notice()
    # Toasts render after the panel so they never shift the panel's position between reruns.
    notice = native.session_state.pop("account_notice", None)
    if notice == "signed_in":
        native.toast(translate("Signed in as {0}.").format(translate(signed_in_user())), icon=":material/check_circle:")
    elif notice == "signed_out":
        native.toast(translate("You have logged out. Your session data was cleared."), icon=":material/logout:")
    return settings_anchor


def remove_legacy_footer():
    """Remove a footer projected by an earlier version in an already-open tab."""
    native.html("""<script>
    if (window.__inspectorFooterCleanup) window.__inspectorFooterCleanup();
    document.getElementById("inspector-viewport-footer")?.remove();
    </script>""", unsafe_allow_javascript=True)
