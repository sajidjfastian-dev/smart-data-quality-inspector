"""Complete, paginated findings and row-level context without raw-value leakage."""
import math
from pathlib import Path
import pandas as pd
from localization import native as st, translate as t, translate_issue_type, display_findings, language
from security_guardrails import mask_dataframe, mask_findings


def render_findings(issues, protected, key, data, downloads=True, filename="issue_report.csv"):
    safe = mask_findings(issues, protected)
    a, b = st.columns(2)
    types = list(issues["Issue Type"].unique())
    columns = list(issues.loc[issues["Issue Type"] != "Duplicate Row", "Column Name"].unique())
    selected_types = a.multiselect(t("Issue types"), types,
                                  format_func=lambda value, locale=language(): translate_issue_type(value, locale),
                                  key=key+"_types")
    selected_columns = b.multiselect(t("Columns"), columns, key=key+"_columns")
    search = st.text_input(t("Search findings"), key=key+"_search")
    filtered = safe
    if selected_types:
        filtered = filtered[filtered["Issue Type"].isin(selected_types)]
    if selected_columns:
        filtered = filtered[filtered["Column Name"].isin(selected_columns)]
    if search.strip():
        mask = filtered.astype(str).apply(lambda col: col.str.contains(search.strip(), case=False, regex=False, na=False)).any(axis=1)
        filtered = filtered[mask]
    st.caption(t("Showing {0} of {1} findings.").format(f"{len(filtered):,}", f"{len(safe):,}"))
    if downloads:
        st.download_button(
            t("Download issue report"),
            data=lambda frame=filtered: frame.to_csv(index=False).encode("utf-8-sig"),
            file_name=filename, mime="text/csv", key=key+"_download", disabled=filtered.empty,
        )
    if filtered.empty:
        st.info(t("No findings match these search and filter choices."))
        return
    pages = max(1, math.ceil(len(filtered) / 100))
    page_key = key+"_page"
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = st.number_input(t("Findings page"), 1, pages, key=page_key)
    st.caption(t("Page {0} of {1}; all matching findings are accessible.").format(page, pages))
    st.dataframe(display_findings(filtered.iloc[(page-1)*100:page*100]), hide_index=True, width="stretch")
    with st.expander(t("Row-level issue detail")):
        row = st.number_input(t("Row number to inspect"), 1, max(1, len(data)), key=key+"_row")
        related = safe[safe["Row Number"] == row]
        st.caption(t("All findings for this row, regardless of the filters above."))
        st.dataframe(mask_dataframe(data.iloc[row-1:row], protected), hide_index=True, width="stretch")
        st.dataframe(display_findings(related), hide_index=True, width="stretch")


def _select_file(name):
    st.session_state["active_dataset"] = name


def render_issue_workspace(datasets, active, original, issues, fixed, fixed_issues, protected, privacy_reviewed, version):
    st.subheader(t("360° issue log"))
    st.caption(t("Explore every finding, inspect related issues on a row, and compare original and corrected scans."))
    with st.expander(t("Workspace coverage"), expanded=True):
        cache = st.session_state.get("quality_scan_cache", {})
        rows = []
        for name, frame in datasets.items():
            scan = cache.get(name)
            rows.append({
                t("File"): name, t("Rows"): len(frame),
                t("Findings"): f"{len(scan['issues']):,}" if scan else t("Not inspected"),
                t("Coverage"): t("Active rules") if name == active else t("Last inspected rules") if scan else t("Open file to inspect"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        target = st.selectbox(t("File to inspect"), list(datasets), index=list(datasets).index(active), key="issue_file_target")
        st.button(t("Open selected file"), key="issue_open_file", disabled=target == active,
                  on_click=_select_file, args=(target,))
        st.caption(t("Counts use each file's last completed scan. Open a file to refresh its checks; uninspected files are not counted as clean."))
    choice = st.radio(t("Findings version"), ["Original data"] + (["Fixed copy"] if fixed is not None else []),
                      format_func=lambda value, locale=language(): t(value, locale),
                      horizontal=True, key="issues_version_"+version)
    current = fixed if choice == "Fixed copy" else original
    findings = fixed_issues if choice == "Fixed copy" else issues
    metrics = st.columns(3)
    metrics[0].metric(t("Original findings"), f"{len(issues):,}")
    metrics[1].metric(t("Remaining findings"), f"{len(fixed_issues):,}" if fixed is not None else t("Not applied"))
    metrics[2].metric(t("Affected rows"), f"{findings['Row Number'].nunique():,}")
    left, right = st.columns(2)
    with left:
        st.caption(t("Findings by type"))
        summary = findings.groupby("Issue Type").size().reset_index(name="Issue Count")
        summary["Issue Type"] = summary["Issue Type"].map(translate_issue_type)
        st.dataframe(summary.rename(columns=t), hide_index=True, width="stretch")
    with right:
        st.caption(t("Findings by column"))
        summary = findings.groupby(["Column Name", "Issue Type"]).size().reset_index(name="Issue Count")
        summary["Issue Type"] = summary["Issue Type"].map(translate_issue_type)
        st.dataframe(summary.rename(columns=t), hide_index=True, width="stretch")
    st.caption(t("Corrected row numbers refer to the corrected copy. The checker review preserves original row references."))
    render_findings(findings, protected, "issues_"+version+"_"+choice, current,
                    downloads=privacy_reviewed, filename=f"{Path(active).stem}_issue_report.csv")
