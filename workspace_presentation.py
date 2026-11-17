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


def render_signed_out_sidebar():
    """A decorative, translated guide for the otherwise empty signed-out sidebar."""
    if signed_in_user():
        return

    def text(value):
        return html.escape(translate(value))

    steps = (
        ("Controlled changes", "Review and approval steps keep proposed changes separate from your original data."),
        ("Privacy protection", "Detected and selected sensitive columns are masked in previews and exports."),
        ("Configurable quality checks", "The application checks your data against the quality rules you select."),
    )
    guide = "".join(
        '<li><span class="signed-out-guide__marker" aria-hidden="true"></span>'
        f'<div><strong>{text(title)}</strong><p>{text(description)}</p></div></li>'
        for title, description in steps
    )
    native.markdown(
        '<div class="signed-out-guide">'
        '<svg class="signed-out-guide__motif" viewBox="0 0 224 106" '
        'xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">'
        '<ellipse cx="112" cy="94" rx="75" ry="5" fill="#e3eee7"/>'
        '<g fill="#eef5ef" stroke="#cedfd5" stroke-width="1.2">'
        '<rect x="51" y="12" width="99" height="75" rx="8" transform="rotate(-8 100 50)"/>'
        '<rect x="70" y="9" width="99" height="81" rx="8"/>'
        '</g>'
        '<g fill="none" stroke="#abc7b9" stroke-width="2" stroke-linecap="round">'
        '<path d="M84 26h38M84 40h14m9 0h15M84 54h38M84 68h14m9 0h15"/>'
        '</g>'
        '<rect x="133" y="34" width="23" height="23" rx="6" fill="#f5eccf" stroke="#d9c487"/>'
        '<path d="m139 45 4 4 7-8" fill="none" stroke="#8c763a" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="40" cy="65" r="3" fill="#d6e6dc"/>'
        '<path d="M183 19v8m-4-4h8" stroke="#cbb56f" stroke-width="1.3" stroke-linecap="round"/>'
        '</svg>'
        f'<h3>{text("Built-in safeguards for your data")}</h3>'
        f'<ol>{guide}</ol></div>',
        unsafe_allow_html=True,
    )


def render_signed_in_sidebar(state):
    """Non-interactive workflow and privacy guide beneath the native navigation."""
    if not signed_in_user():
        return

    def text(value):
        return html.escape(translate(value))

    page = state.get(
        "workspace_page",
        "inspection" if state.get("inspector_datasets") else "requests",
    )
    # Restrict the attribute to known values; the marker only styles real buttons.
    selected = page if page in ("requests", "inspection") else ""
    steps = (
        ("Prepare a dataset", "Choose a synthetic example or upload a private file in the workspace."),
        ("Inspect findings", "Check quality issues and compare proposed changes."),
        ("Review before sharing", "Check the result and mask sensitive columns before sharing."),
    )
    workflow = "".join(
        '<li><span class="signed-in-guide__number" aria-hidden="true">'
        f'{number:02d}</span><div><strong>{text(title)}</strong>'
        f'<p>{text(description)}</p></div></li>'
        for number, (title, description) in enumerate(steps, start=1)
    )
    native.markdown(
        f'<div class="signed-in-guide" data-nav="{selected}">'
        f'<h3>{text("Request workflow")}</h3><ol>{workflow}</ol>'
        '<div class="signed-in-guide__privacy">'
        f'<h4>{text("What stays where")}</h4>'
        f'<p>{text("Shared synthetic examples are saved. Private uploads stay in this session.")}</p>'
        '</div></div>',
        unsafe_allow_html=True,
    )


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
            else:
                native.button(translate("Continue with SSO"), key="sidebar_login",
                              icon=":material/login:", type="primary", width="stretch", on_click=sign_in)
        if not user:
            native.caption(translate("Demo sign-in · no credentials required"))
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
