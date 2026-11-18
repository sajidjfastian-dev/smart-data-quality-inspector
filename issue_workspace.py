"""Read-only, masked evidence explorer shared by active files and request detail."""
import math
from html import escape
from pathlib import Path

import pandas as pd

from issue_workspace_translations import ISSUE_WORKSPACE_ARABIC
from localization import native as st, translate, translate_issue_type, display_findings, language
from review_approval import frame_digest
from security_guardrails import mask_dataframe, mask_findings


SCOPES = ("All findings", "Column findings", "Whole-row duplicates")
GUIDANCE = {
    "Missing Value": (
        "A blank or whitespace-only value was found.",
        "Missing data can prevent complete matching or calculations.",
        "Check the source; fill only when an appropriate value is known.",
    ),
    "Duplicate Row": (
        "This occurrence matches an earlier row across every column.",
        "Repeated rows may double-count a record.",
        "Confirm whether the repeat is intentional before removing it.",
    ),
    "Invalid Email": (
        "A selected email value does not match the email-format check.",
        "The value may be unsuitable for email-based matching or contact.",
        "Verify the source address before correcting it; format checks do not verify delivery.",
    ),
    "Invalid Date": (
        "A selected date value could not be parsed.",
        "Date-based sorting and calculations may exclude the value.",
        "Confirm the intended date and correct the source format.",
    ),
    "Inconsistent Date Format": (
        "Parseable dates use different patterns within the selected column.",
        "Mixed formats can make dates ambiguous to readers.",
        "Review ambiguous dates, then standardize valid dates in Review & fix.",
    ),
    "Numeric Outlier": (
        "A numeric value falls outside the configured IQR limits.",
        "An outlier is a review candidate, not a confirmed error.",
        "Check units, context and source evidence before changing the value.",
    ),
    "Invalid Number": (
        "A value in a selected numeric column is malformed or non-finite.",
        "Numeric calculations and outlier checks exclude this value.",
        "Verify the intended number in the source; it is not automatically replaced.",
    ),
    "Custom": (
        "A value does not meet a configured column rule.",
        "Custom rules represent the expectations selected for this file.",
        "Review the configured rule and source; no automatic correction is assumed.",
    ),
    "Other": (
        "A selected quality control recorded this finding.",
        "A finding needs context before it is treated as an error.",
        "Inspect the row and source evidence before choosing a correction.",
    ),
}


def t(value, locale=None):
    """Translate application copy only; dataset names never pass through here."""
    selected = language() if locale is None else locale
    if selected == "العربية" and value in ISSUE_WORKSPACE_ARABIC:
        return ISSUE_WORKSPACE_ARABIC[value]
    return translate(value, selected)


def _styles():
    css = (Path(__file__).parent / "assets" / "issue_workspace.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def filter_safe_findings(safe, selected_types=(), selected_columns=(), scope="All findings",
                         search="", display_search=None):
    """Filter an already-masked frame. Literal column names never mean row scope."""
    selected = pd.Series(True, index=safe.index)
    duplicate = safe["Issue Type"].eq("Duplicate Row")
    if selected_types:
        selected &= safe["Issue Type"].isin(selected_types)
    if scope == "Column findings":
        selected &= ~duplicate
    elif scope == "Whole-row duplicates":
        selected &= duplicate
    if selected_columns:
        # A real column called "Entire row" is not the whole-row duplicate scope.
        selected &= ~duplicate & safe["Column Name"].isin(selected_columns)
    term = search.strip()
    if term:
        def matches(frame):
            return frame.astype(str).apply(
                lambda col: col.str.contains(term, case=False, regex=False, na=False)
            ).any(axis=1)
        matched = matches(safe)
        if display_search is not None:
            matched |= matches(display_search)
        selected &= matched
    return safe.loc[selected]


def affected_rows(findings, row_count):
    positions = pd.to_numeric(findings["Row Number"], errors="coerce")
    valid = positions.between(1, row_count) & positions.eq(positions.round())
    return int(positions[valid].nunique())


def workspace_coverage(datasets, active, current_issues, cache):
    """Counts describe actual completed scans, not assumed workspace cleanliness."""
    rows = []
    for name, frame in datasets.items():
        scan = cache.get(name)
        if name == active:
            count, coverage = f"{len(current_issues):,}", "Current file · current controls"
        elif not scan or scan.get("issues") is None:
            count, coverage = "Not inspected", "Open file to inspect"
        else:
            count = f"{len(scan['issues']):,}"
            digest = scan.get("digest")
            coverage = ("Previous scan · open to refresh" if digest is None else
                        "Last completed scan" if digest == frame_digest(frame) else
                        "Data changed · open to rescan")
        rows.append({"File": name, "Rows": len(frame), "Findings": count, "Coverage": coverage})
    return rows


def _clear_filters(key):
    for suffix, value in (("_types", []), ("_columns", []), ("_search", ""),
                          ("_page", 1)):
        st.session_state[key + suffix] = value
    scope_key = _localized_choice_key(key + "_scope", SCOPES)
    st.session_state[scope_key] = "All findings"
    st.session_state[key + "_scope_choice"] = "All findings"


def _localized_choice_key(base_key, options):
    """Remount native option labels on locale change, retaining the real choice.

    Streamlit's native controls can retain an English display value or lose the
    checked radio indicator when only format_func labels change. EN keeps its
    established widget key; a separate AR presentation key avoids that stale UI.
    """
    locale = language()
    ui_key = base_key + ("_ar" if locale == "العربية" else "")
    saved = st.session_state.get(base_key + "_choice", st.session_state.get(base_key, options[0]))
    if saved not in options:
        saved = options[0]
    if (st.session_state.get(base_key + "_locale") != locale
            or st.session_state.get(ui_key) not in options):
        st.session_state[ui_key] = saved
    st.session_state[base_key + "_locale"] = locale
    return ui_key


def _remember_choice(base_key, ui_key):
    st.session_state[base_key + "_choice"] = st.session_state[ui_key]


def _scope_changed(key, ui_key):
    _remember_choice(key + "_scope", ui_key)
    if st.session_state.get(ui_key) == "Whole-row duplicates":
        st.session_state[key + "_columns"] = []
    st.session_state[key + "_page"] = 1


def _table(frame, values=False):
    config = None if values else {
        t("Suggested Fix"): st.column_config.TextColumn(t("Suggested Fix"), width="large"),
        t("Current Value"): st.column_config.TextColumn(t("Current Value"), width="medium"),
    }
    st.dataframe(frame, hide_index=True, width="stretch", row_height=40,
                 height=min(440, max(100, 42 + len(frame) * 40)), column_config=config)


def _guidance(issues, key):
    if issues.empty:
        return
    with st.expander(t("Understand a finding"), expanded=False):
        counts = issues["Issue Type"].value_counts()
        selected = st.selectbox(
            t("Issue type to explain"), list(counts.index), key=key + "_explain",
            format_func=lambda value, locale=language(): f"{translate_issue_type(value, locale)} · {counts[value]:,}",
        )
        kind = "Custom" if selected.startswith("Custom:") else selected
        texts = GUIDANCE.get(kind, GUIDANCE["Other"])
        blocks = "".join(
            "<div><strong>" + escape(t(label)) + "</strong><p>" + escape(t(text)) + "</p></div>"
            for label, text in zip(("What", "Why it matters", "Next action"), texts)
        )
        st.markdown('<div class="issue-guidance">' + blocks + "</div>", unsafe_allow_html=True)


def render_findings(issues, protected, key, data, downloads=True, filename="issue_report.csv"):
    """All matching findings export lazily; row detail ignores every list filter."""
    _styles()
    safe = mask_findings(issues, protected)
    with st.container(key="issue_findings_" + key):
        st.markdown('<h3 class="issue-section-heading">' + escape(t("Findings explorer")) + "</h3>",
                    unsafe_allow_html=True)
        _guidance(safe, key)
        types = list(issues["Issue Type"].unique())
        columns = list(issues.loc[issues["Issue Type"] != "Duplicate Row", "Column Name"].unique())
        scope_key = _localized_choice_key(key + "_scope", SCOPES)
        a, b, c = st.columns([1.3, 1.3, 1], gap="small")
        selected_types = a.multiselect(
            t("Issue types"), types, format_func=lambda value, locale=language(): translate_issue_type(value, locale),
            key=key + "_types",
        )
        selected_columns = b.multiselect(
            t("Columns"), columns, key=key + "_columns",
            help=t("Selecting columns excludes whole-row duplicate findings."),
            disabled=st.session_state.get(scope_key) == "Whole-row duplicates",
        )
        scope = c.selectbox(
            t("Finding scope"), SCOPES,
            format_func=lambda value, locale=language(): t(value, locale),
            key=scope_key, on_change=_scope_changed, args=(key, scope_key),
        )
        st.session_state[key + "_scope_choice"] = scope
        search = st.text_input(
            t("Search findings"), key=key + "_search",
            help=t("Searches the masked findings only. Text is matched literally, not as a pattern."),
        )
        filtered = filter_safe_findings(safe, selected_types, selected_columns, scope, search,
                                        display_findings(safe))
        signature = (tuple(selected_types), tuple(selected_columns), scope, search.strip())
        if st.session_state.get(key + "_filter_signature") != signature:
            st.session_state[key + "_page"] = 1
            st.session_state[key + "_filter_signature"] = signature
        st.markdown(
            '<div class="issue-results"><strong>'
            + escape(t("{0} matching / {1} current-version findings").format(f"{len(filtered):,}", f"{len(safe):,}"))
            + '</strong><span>'
            + escape(t("{0} affected rows in these results").format(f"{affected_rows(filtered, len(data)):,}"))
            + '</span></div>', unsafe_allow_html=True,
        )
        actions = st.columns([1.1, 1, 1.3] if downloads else [1, 1.3], gap="small")
        if downloads:
            with actions[0]:
                st.download_button(
                    t("Download issue report"),
                    data=filtered.to_csv(index=False).encode("utf-8-sig"),
                    file_name=filename, mime="text/csv", key=key + "_download", disabled=filtered.empty,
                )
        with actions[1 if downloads else 0]:
            st.button(t("Clear filters"), key=key + "_clear", on_click=_clear_filters, args=(key,))
        if filtered.empty:
            if safe.empty:
                st.markdown(
                    '<div class="issue-empty"><strong>' + escape(t("No findings in this version"))
                    + '</strong><p>' + escape(t(
                        "This scan recorded no findings. This is not a guarantee that the data is error-free."
                    )) + '</p></div>', unsafe_allow_html=True,
                )
            else:
                st.info(t("No findings match these search and filter choices."))
                st.caption(t("Change the filters or clear them. Row detail below still shows every finding for the chosen row."))
        else:
            pages = max(1, math.ceil(len(filtered) / 100))
            page_key = key + "_page"
            if not 1 <= st.session_state.get(page_key, 1) <= pages:
                st.session_state[page_key] = 1
            page = 1
            if pages > 1:
                with actions[-1]:
                    page = st.number_input(t("Findings page"), 1, pages, key=page_key)
                st.caption(t("Page {0} of {1}; all matching findings are accessible.").format(page, pages))
            _table(display_findings(filtered.iloc[(page - 1) * 100:page * 100]))

        # Deliberately outside the filtered-empty branch: a search cannot hide
        # row context or remove findings from the exact row detail.
        with st.expander(t("Row-level issue detail"), expanded=False):
            st.caption(t("All findings for this row, regardless of the filters above."))
            if data.empty:
                st.info(t("This copy has no rows to inspect."))
            else:
                row_key = key + "_row"
                if not 1 <= st.session_state.get(row_key, 1) <= len(data):
                    st.session_state[row_key] = 1
                row = st.number_input(t("Row number to inspect"), 1, len(data), key=row_key)
                related = safe[safe["Row Number"] == row]
                st.caption(t("Read-only row values"))
                _table(mask_dataframe(data.iloc[row - 1:row], protected), values=True)
                if related.empty:
                    st.info(t("No findings for this row in the selected version."))
                else:
                    st.caption(t("All findings on this row"))
                    _table(display_findings(related))


def _select_file(name):
    st.session_state["active_dataset"] = name


def render_issue_workspace(datasets, active, original, issues, fixed, fixed_issues, protected,
                           privacy_reviewed, version, *, enabled_checks=None, custom_rules=None):
    _styles()
    with st.container(key="issue_workspace"):
        st.markdown(
            '<div class="issue-intro"><h2>' + escape(t("Issue log")) + '</h2><p>'
            + escape(t("Read the evidence, understand each finding, then choose corrections in Review & fix. Original data is read-only here."))
            + '</p></div>', unsafe_allow_html=True,
        )
        with st.expander(t("Workspace coverage"), expanded=False):
            rows = workspace_coverage(datasets, active, issues, st.session_state.get("quality_scan_cache", {}))
            coverage = pd.DataFrame(rows)
            for field in ("Findings", "Coverage"):
                coverage[field] = coverage[field].map(lambda value: t(value) if isinstance(value, str) else value)
            st.dataframe(coverage.rename(columns=t), hide_index=True, width="stretch", row_height=40)
            target = st.selectbox(t("File to inspect"), list(datasets), index=list(datasets).index(active), key="issue_file_target")
            st.button(t("Open selected file"), key="issue_open_file", disabled=target == active,
                      on_click=_select_file, args=(target,))
            st.caption(t("Counts use each file's last completed scan. Open a file to refresh its checks; uninspected files are not counted as clean."))
        fixed_ready = fixed is not None and fixed_issues is not None
        versions = ["Original data"] + (["Fixed copy"] if fixed_ready else [])
        version_key = "issues_version_" + version
        version_ui_key = _localized_choice_key(version_key, versions)
        choice = st.radio(
            t("Findings version"), versions,
            format_func=lambda value, locale=language(): t(value, locale),
            horizontal=True, key=version_ui_key,
            on_change=_remember_choice, args=(version_key, version_ui_key),
        )
        st.session_state[version_key + "_choice"] = choice
        current = fixed if choice == "Fixed copy" else original
        findings = fixed_issues if choice == "Fixed copy" else issues
        badge = "issue-version-badge--fixed" if choice == "Fixed copy" else ""
        st.markdown(
            '<div class="issue-context"><div><strong><bdi>' + escape(str(active)) + '</bdi></strong><p>'
            + escape(t("{0} rows · {1} columns · read-only").format(f"{len(current):,}", len(current.columns)))
            + '</p></div><span class="issue-version-badge ' + badge + '">' + escape(t(choice))
            + '</span></div>', unsafe_allow_html=True,
        )
        metrics = st.columns(3)
        metrics[0].metric(t("Original findings"), f"{len(issues):,}")
        metrics[1].metric(t("Fixed-copy findings"), f"{len(fixed_issues):,}" if fixed_ready else t("Not applied"))
        metrics[2].metric(t("Affected rows in this version"), f"{affected_rows(findings, len(current)):,}")
        if fixed_ready:
            st.caption(t("Net count change: {0}. Counts alone do not identify resolved findings.").format(
                f"{len(fixed_issues) - len(issues):+,}"))
            st.caption(t("Original and fixed row numbers refer to their own copies; rows may move after deduplication."))
        elif fixed is not None:
            st.info(t("Fixed-copy inspection is not available yet. Showing original findings."))
        else:
            st.caption(t("Create a fixed copy in Review & fix to compare scans."))
        if enabled_checks is not None:
            st.caption(t("{0} built-in checks enabled · {1} custom rules").format(
                len(enabled_checks), len(custom_rules or ())))
            if not enabled_checks and not custom_rules:
                st.info(t("No controls are enabled. No findings does not mean this file was assessed."))
        if not privacy_reviewed:
            st.info(t("Review Data privacy before downloading a findings report."))
        render_findings(findings, protected, "issues_" + version + "_" + choice, current,
                        downloads=privacy_reviewed, filename=f"{Path(active).stem}_issue_report.csv")
