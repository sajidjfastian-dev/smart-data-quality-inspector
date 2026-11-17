"""Presentation-only enhancements; data access and safeguards remain in app.py."""

import html
from pathlib import Path

from localization import native, st, translate


def install_presentation_styles():
    css = (Path(__file__).parent / "assets" / "workspace_presentation.css").read_text(encoding="utf-8")
    native.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def select_workspace(destination):
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
