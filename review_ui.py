"""Masked, paginated before/after checker review."""
import math
import html
import pandas as pd
from localization import native as st, translate as t, language, display_findings
from security_guardrails import MASK, mask_dataframe
from review_approval import approve, is_approved, return_for_revision


def render_checker_review(state, dataset, original, corrected, changes, remaining, protected, choice, actions=True):
    context = state["review_contexts"][dataset]
    version = context["version"]
    key = f"checker_{version}_{choice}"
    with st.container(border=True):
        st.subheader(t("Checker review and final approval") if actions else t("Review changes"))
        if actions:
            st.caption(t("Demo only: this is not an independent authenticated checker or a production authorization."))
            st.caption(t("Review version") + ": " + version[:12] + " · " + t(choice))
        changed_cells = int(changes["Column position"].notna().sum())
        removed = int(changes["Column position"].isna().sum())
        labels = ["Changed cells", "Affected rows", "Rows removed", "Remaining findings"] if actions else ["Changed cells", "Rows removed", "Remaining findings"]
        values = [changed_cells, changes["Original row"].nunique(), removed, len(remaining)] if actions else [changed_cells, removed, len(remaining)]
        metrics = st.columns(len(labels))
        for col, label, value in zip(metrics,
                                    labels, values):
            col.metric(t(label), f"{value:,}")
        if actions or not changes.empty:
            st.caption(t("Original values are on the left; corrected values are on the right. Protected values stay masked."))
        if changes.empty:
            if actions:
                st.info(t("No changes in this version. Review the original data and remaining findings before approving."))
                page_count = max(1, math.ceil(len(original) / 50))
                page = st.number_input(t("Data review page"), 1, page_count, key=key + "_data_page")
                st.dataframe(mask_dataframe(original.iloc[(page-1)*50:page*50], protected), hide_index=True, width="stretch")
            else:
                st.info(t("No values changed in this version."))
        else:
            options = list(changes["Change reason"].unique())
            reasons = []
            if actions or (len(options) > 1 and len(changes) > 50):
                reasons = st.multiselect(t("Filter changes"), options,
                                         format_func=lambda value, locale=language(): t(value, locale),
                                         key=key + "_reasons")
            filtered = changes[changes["Change reason"].isin(reasons)] if reasons else changes
            page_count = max(1, math.ceil(len(filtered) / 50))
            page_key = key + "_page_" + str(tuple(reasons))
            page = st.number_input(t("Changes page"), 1, page_count, key=page_key) if actions or page_count > 1 else 1
            if actions or page_count > 1:
                st.caption(t("Showing {0} changes; page {1} of {2}.").format(len(filtered), page, page_count))
            records = []
            for row in filtered.iloc[(page-1)*50:page*50].itertuples(index=False, name=None):
                original_row, corrected_row, column_pos, reason = row
                if pd.isna(column_pos):
                    before = mask_dataframe(original.iloc[[int(original_row)-1]], protected).to_dict("records")[0]
                    old, new, label = str(before), t("Row removed"), t("Entire row")
                else:
                    column_pos = int(column_pos)
                    label = str(original.columns[column_pos])
                    old = original.iloc[int(original_row)-1, column_pos]
                    new = corrected.iloc[int(corrected_row)-1, column_pos]
                    if original.columns[column_pos] in protected:
                        old = new = MASK
                    else:
                        old = t("(empty)") if pd.isna(old) else old
                        new = t("(empty)") if pd.isna(new) else new
                records.append({
                    t("Original row"): int(original_row), t("Column"): label,
                    t("Original value"): str(old), t("Corrected value"): str(new),
                    t("Change reason"): t(reason),
                })
            # Keep original physically left of corrected even in Arabic. A single
            # table keeps corresponding values aligned when long content wraps.
            headings = [t("Original row"), t("Column"), t("Original value"), t("Corrected value"), t("Change reason")]
            header = "".join("<th>" + html.escape(label) + "</th>" for label in headings)
            body = "".join(
                "<tr>" + "".join("<td><bdi>" + html.escape(str(record[label])) + "</bdi></td>" for label in headings) + "</tr>"
                for record in records
            )
            st.markdown(
                '<div class="checker-comparison" dir="ltr" tabindex="0"><table><thead><tr>'
                + header + "</tr></thead><tbody>" + body + "</tbody></table></div>",
                unsafe_allow_html=True,
            )
            st.caption(t("On small screens, scroll the comparison horizontally to see both values."))
        if actions or not remaining.empty:
            st.warning(t("Approval does not mean error-free data. Review all remaining findings before proceeding."))
            if actions:
                with st.expander(t("Review unresolved issues")):
                    from issue_workspace import render_findings
                    render_findings(remaining, protected, key + "_remaining", corrected, downloads=False)
            elif not remaining.empty:
                with st.expander(t("Review unresolved issues")):
                    from security_guardrails import mask_findings
                    safe = mask_findings(remaining, protected)
                    page_count = max(1, math.ceil(len(safe) / 50))
                    page = st.number_input(t("Issues page"), 1, page_count, key=key + "_issues_page") if page_count > 1 else 1
                    st.caption(t("Showing {0} issues · page {1} of {2}").format(f"{len(safe):,}", page, page_count))
                    st.dataframe(display_findings(safe.iloc[(page-1)*50:page*50]), hide_index=True, width="stretch")
        else:
            st.success(t("No remaining findings."))
        if not actions:
            return
        checked = st.checkbox(t("I reviewed the changes and remaining findings"), key=key + "_ack")
        if is_approved(state, dataset, corrected, choice):
            st.success(t("Final demo approval granted for this version. Destination consent is still required."))
        approve_col, return_col = st.columns(2)
        if approve_col.button(t("Approve reviewed version"), key=key + "_approve",
                              type="primary", disabled=not checked or not context["privacy_reviewed"]):
            approve(state, dataset, corrected, choice, len(remaining))
            st.rerun()
        def return_action():
            return_for_revision(state, dataset)
            state[key + "_ack"] = False
        return_col.button(t("Return for revision"), key=key + "_return", on_click=return_action)
        from demo_change_ticket import render_demo_ticket
        render_demo_ticket(state, dataset, original, corrected, choice, changes)
