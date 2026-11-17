"""Presentation-only enhancements; data access and safeguards remain in app.py."""

import html
from pathlib import Path

from localization import native, st, translate
from history_ui import show_history


def install_presentation_styles():
    css = (Path(__file__).parent / "assets" / "workspace_presentation.css").read_text(encoding="utf-8")
    native.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def show_login_notice():
    """A presentation-only notice: never changes identity or history state."""
    @native.dialog(translate("Login"), width="small")
    def notice():
        def text(value):
            return html.escape(translate(value))

        native.markdown(
            '<div class="login-notice">'
            f'<div class="login-kicker">{text("Organisation access")}</div>'
            f'<h3>{text("Organisation SSO setup pending")}</h3>'
            f'<p>{text("Your organisation’s approved SSO connection is not active yet. Login is not available and no credentials are collected here.")}</p>'
            '</div>', unsafe_allow_html=True,
        )
        native.caption(translate("You can continue inspecting data in this session without signing in. Saving and viewing inspection history remain disabled until organisation SSO is configured."))
        if native.button(translate("Continue without signing in"), key="login_continue", type="primary", width="stretch"):
            native.rerun()
        if native.button(translate("Close"), key="login_close", width="stretch"):
            native.rerun()

    notice()


def landing_markup():
    """Original, explicitly illustrative product preview; no dataset access."""
    def t(value):
        return html.escape(translate(value))

    stages = '<div class="journey-link" aria-hidden="true"></div>'.join(
        f'<div class="journey-stage"><div class="journey-icon" aria-hidden="true">{number}</div>'
        f'<span class="journey-stage-label">{t(label)}</span></div>'
        for number, label in (("01", "Import"), ("02", "Inspect"), ("03", "Improve"), ("04", "Export"))
    )
    steps = "".join(
        f'<div class="welcome-step"><span class="welcome-step-number">{number}</span>'
        f'<span>{t(title)}<small>{t(detail)}</small></span></div>'
        for number, title, detail in (
            ("01", "Connect your sources", "Bring CSV, Excel or API data into one inspection workspace."),
            ("02", "See what needs attention", "Check missing values, duplicates, formats and numeric outliers."),
            ("03", "Keep the final say", "Review findings and choose safe fixes. Your original stays unchanged."),
            ("04", "Take the next step", "Review sensitive columns, then export a copy or send it by API."),
        )
    )
    return f"""
    <section class="welcome-panel" aria-label="{t('Data quality introduction')}">
      <div class="welcome-copy">
        <div class="welcome-eyebrow">{t('A clearer view of your financial data')}</div>
        <h1 class="welcome-title">{t('Turn data into')} <span class="welcome-accent">{t('decisions.')}</span></h1>
        <p class="welcome-description">{t('Find the gaps before your next report. Inspect your data, understand the findings, and improve a copy — with every change in your hands.')}</p>
        <div class="welcome-start"><div>
          <strong>{t('Start in the sidebar')}</strong>
          <span class="welcome-start-copy">{t('Upload a file, explore the sample workspace, or connect an API in settings.')}</span>
        </div></div>
        <div class="welcome-meta" aria-label="{t('Supported capabilities')}">
          <span>{t('CSV & Excel')}</span><span>{t('API connections')}</span><span>{t('Configurable checks')}</span>
        </div>
      </div>
      <div class="welcome-preview" aria-label="{t('Illustrative product preview — not uploaded data')}">
        <div class="welcome-preview-top">
          <div class="welcome-preview-title">{t('Smart Data Quality Inspector')}</div>
          <div class="welcome-preview-badge">{t('Illustration · not your data')}</div>
        </div>
        <div class="inspector-demo-body">
          <div class="inspector-demo-sheet">
            <h2>{t('Small details. Better decisions.')}</h2>
            <div class="inspector-demo-caption">{t('Example only: reviewing an invoice dataset')}</div>
            <table class="inspector-demo-table">
              <thead><tr><th>{t('Invoice')}</th><th>{t('Amount')}</th><th>{t('Review findings')}</th></tr></thead>
              <tbody>
                <tr><td><bdi>INV-1042</bdi></td><td><bdi>1,284.75</bdi></td><td><span class="demo-ok">{t('No finding shown')}</span></td></tr>
                <tr><td><bdi>INV-1043</bdi></td><td class="demo-flag">{t('Missing value')}</td><td>{t('Review source')}</td></tr>
                <tr><td><bdi>INV-1043</bdi></td><td><bdi>346.80</bdi></td><td class="demo-flag">{t('Check duplicate')}</td></tr>
              </tbody>
            </table>
          </div>
          <aside class="inspector-demo-review">
            <span class="demo-review-icon" aria-hidden="true">✓</span>
            <strong>{t('You review. You decide.')}</strong>
            <p>{t('A finding is a prompt to investigate, not a confirmed business error. Choose what to change in a separate copy.')}</p>
            <div class="demo-review-status">{t('Original data stays unchanged')}</div>
          </aside>
        </div>
        <div class="journey-visual" aria-label="{t('Import, inspect, improve, and export data')}">{stages}</div>
      </div>
      <p class="landing-privacy-note">{t('Review sensitive columns before sharing or exporting. Automatic detection can miss sensitive data.')}</p>
      <div class="welcome-steps" aria-label="{t('How it works')}">{steps}</div>
    </section>
    """


def select_workspace(destination):
    native.session_state["workspace_page"] = "inspection"
    native.session_state["dashboard_tabs"] = translate(destination)


def select_settings(destination):
    native.session_state["settings_navigation"] = translate(destination)
    native.session_state["settings_button"] = True
    native.session_state["reveal_settings_panel"] = True


def render_workspace_menu():
    ready = bool(native.session_state.get("inspector_datasets", {}))
    groups = (
        ("Inspect & review", "fact_check", (
            ("Overview", "1 · Overview", "dashboard"),
            ("Issue log", "2 · Issue log", "list_alt"),
            ("Review & fix", "3 · Review & fix", "tune"),
        )),
        ("Explore & export", "query_stats", (
            ("Preview & export", "4 · Preview & export", "ios_share"),
            ("Assistant", "5 · Assistant", "chat_bubble_outline"),
            ("Data insights", "6 · Data insights", "monitoring"),
        )),
    )
    with st.container(key="workspace_menu"):
        native.button(
            translate("Inspection history"), key="nav_history", width="stretch",
            icon=":material/history:", on_click=show_history,
        )
        for label, icon, destinations in groups:
            with st.expander(translate(label), icon=f":material/{icon}:", expanded=False):
                if not ready:
                    st.caption(translate("Load a file, sample workspace, or API source to unlock these views."))
                for title, destination, item_icon in destinations:
                    native.button(
                        translate(title), key=f"nav_{destination[0]}", width="stretch",
                        icon=f":material/{item_icon}:", disabled=not ready,
                        help=translate("Open this view for the active dataset.") if ready else translate("Load data to enable workspace navigation."),
                        on_click=select_workspace, args=(destination,),
                    )
        with st.expander(translate("Settings"), icon=":material/settings:", expanded=False):
            for index, (label, icon) in enumerate((
                ("LLM assistant", "smart_toy"), ("Data APIs", "api"),
                ("Inspection checks", "checklist"), ("Data privacy", "shield"),
            )):
                native.button(
                    translate(label), key=f"nav_settings_{index}", icon=f":material/{icon}:",
                    width="stretch", on_click=select_settings, args=(label,),
                )
            st.caption(translate("Settings open in the panel below. Review privacy before sharing."))


def render_motion_control():
    paused = native.session_state.get("landing_animation_paused", False)
    with native.container(key="landing_motion"):
        with native.container(key="landing_motion_paused" if paused else "landing_motion_running"):
            native.button(
                translate("Resume workflow animation") if paused else translate("Pause workflow animation"),
                icon=":material/play_arrow:" if paused else ":material/pause:",
                on_click=_toggle_motion, key="toggle_workflow_animation",
            )


def _toggle_motion():
    native.session_state["landing_animation_paused"] = not native.session_state.get("landing_animation_paused", False)


def render_viewport_footer():
    """Project the footer across the viewport without changing its scroll position.

    Its source remains in normal flow and reserves the measured height. A
    viewport-level copy avoids clipping by Streamlit's independently scrolling
    main/sidebar panes. The sidebar shrinks only as the footer enters view.
    """
    if native.session_state.pop("reveal_settings_panel", False):
        native.html("""
        <script>
        requestAnimationFrame(() => {
          const anchor = document.querySelector(".st-key-settings_anchor");
          if (anchor) anchor.scrollIntoView({block: "center", behavior: "instant"});
        });
        </script>
        """, unsafe_allow_javascript=True)
    labels = [html.escape(translate(text)) for text in (
        "Smart Data Quality Inspector", "Session-based processing",
        "Accessibility review pending", "UAE accessibility guidance",
    )]
    native.markdown(
        f'<footer class="app-footer" id="inspector-footer-source">'
        f'<div><strong>{labels[0]}</strong><span>{labels[1]}</span></div>'
        f'<div class="app-footer-links"><span>{labels[2]}</span>'
        f'<a href="https://designsystem.gov.ae/guidelines/accessibility">{labels[3]}</a>'
        '</div></footer>', unsafe_allow_html=True,
    )
    native.html("""
    <script>
    (() => {
      if (window.__inspectorFooterCleanup) window.__inspectorFooterCleanup();
      const source = document.getElementById("inspector-footer-source");
      if (!source) return;
      const footer = source.cloneNode(true);
      footer.id = "inspector-viewport-footer";
      document.body.appendChild(footer);
      source.setAttribute("aria-hidden", "true");
      source.style.visibility = "hidden";
      source.querySelectorAll("a").forEach(a => a.tabIndex = -1);
      let frame = 0;
      const sidebar = document.querySelector('[data-testid="stSidebar"]');
      const oldHeight = sidebar?.style.getPropertyValue("height") || "";
      const oldPriority = sidebar?.style.getPropertyPriority("height") || "";
      function update() {
        frame = 0;
        if (!source.isConnected) { cleanup(); return; }
        source.style.minHeight = footer.offsetHeight + "px";
        const top = source.getBoundingClientRect().top;
        const visible = top < innerHeight && top + footer.offsetHeight > 68;
        footer.style.visibility = visible ? "visible" : "hidden";
        footer.style.top = top + "px";
        if (sidebar) {
          const sidebarTop = sidebar.getBoundingClientRect().top;
          sidebar.style.setProperty("height",
            Math.max(0, Math.min(innerHeight, top) - sidebarTop) + "px", "important");
        }
      }
      function schedule() { if (!frame) frame = requestAnimationFrame(update); }
      const observer = new ResizeObserver(schedule);
      observer.observe(footer);
      observer.observe(document.querySelector('[data-testid="stMainBlockContainer"]') || source.parentElement);
      document.addEventListener("scroll", schedule, true);
      window.addEventListener("resize", schedule);
      function cleanup() {
        observer.disconnect();
        document.removeEventListener("scroll", schedule, true);
        window.removeEventListener("resize", schedule);
        cancelAnimationFrame(frame);
        footer.remove();
        if (sidebar) {
          if (oldHeight) sidebar.style.setProperty("height", oldHeight, oldPriority);
          else sidebar.style.removeProperty("height");
        }
        source.style.visibility = "";
        source.removeAttribute("aria-hidden");
        source.querySelectorAll("a").forEach(a => a.removeAttribute("tabindex"));
      }
      window.__inspectorFooterCleanup = cleanup;
      update();
    })();
    </script>
    """, unsafe_allow_javascript=True)
