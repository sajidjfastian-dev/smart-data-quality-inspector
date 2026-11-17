"""Bilingual history controls with an explicitly disabled SSO setup state."""

from datetime import timezone

from localization import native as st, translate as t
from inspection_history import HistoryRepository, HistoryUnavailable, current_history_owner


def show_history():
    st.session_state["workspace_page"] = "history"


def back_to_inspection():
    st.session_state["workspace_page"] = "inspection"


def render_history():
    st.header(t("Inspection history"))
    st.caption(t("Inspection summaries only · 30-day retention"))
    st.button(t("Back to inspection"), icon=":material/arrow_back:",
              key="history_back", on_click=back_to_inspection)
    st.info(t("History never stores uploaded files, raw values, filenames, or column names. It cannot reopen a previous file."))
    owner = current_history_owner()
    if owner is None:
        with st.container(border=True):
            st.subheader(t("Organisation SSO setup pending"))
            st.write(t("Saving and viewing history are disabled until your approved SSO connection and retention cleanup are configured. Current inspections remain available."))
            st.button(t("Sign in with organisation SSO"), icon=":material/lock:",
                      disabled=True, key="history_signin_pending")
        return
    page = st.number_input(t("History page"), min_value=1, value=1, step=1, key="history_page")
    try:
        records = HistoryRepository().list(owner, page=int(page) - 1)
    except HistoryUnavailable as error:
        st.error(t(str(error)))
        return
    if not records:
        st.info(t("No inspection summaries on this page."))
        return
    if len(records) > 50:
        st.caption(t("More summaries are available on the next page."))
    for record in records[:50]:
        label = f"{t('Inspection')} · {record['created_at'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        with st.expander(label):
            metrics = st.columns(4)
            for target, title, value in zip(metrics,
                    ("Rows", "Columns", "Findings", "Data Health Score"),
                    (record["row_count"], record["column_count"], record["finding_count"], f"{record['health_score']}%")):
                target.metric(t(title), value)
            st.caption(t("Expires on {0}").format(record["expires_at"].astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")))
            st.write(t("Enabled checks") + ": " + ", ".join(t(c) for c in record["enabled_checks"]))
            st.write({
                t("Missing values"): record["missing_count"],
                t("Duplicate rows"): record["duplicate_count"],
                t("Invalid email formats"): record["email_count"],
                t("Invalid and inconsistent dates"): record["date_count"],
                t("Numeric outliers"): record["outlier_count"],
                t("Custom checks"): record["custom_count"],
            })
            confirmed = st.checkbox(t("Confirm permanent deletion"), key=f"history_confirm_{record['id']}")
            if st.button(t("Delete summary"), key=f"history_delete_{record['id']}", disabled=not confirmed):
                try:
                    HistoryRepository().delete(owner, record["id"])
                except HistoryUnavailable as error:
                    st.error(t(str(error)))
                else:
                    st.rerun()


def render_save_summary(summary, run_key):
    owner = current_history_owner()
    with st.expander(t("Save inspection summary"), icon=":material/history:"):
        st.caption(t("Save counts, quality score, and enabled checks for 30 days. Files and raw data are not stored."))
        if owner is None:
            st.info(t("Organisation SSO setup pending. No inspection history is being saved."))
        if st.button(t("Save summary for 30 days"), disabled=owner is None, key="save_history_summary"):
            try:
                created = HistoryRepository().save(owner, run_key, summary)
            except HistoryUnavailable as error:
                st.error(t(str(error)))
            else:
                st.success(t("Inspection summary saved.") if created else t("This inspection summary is already saved."))
