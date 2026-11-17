"""Session-only, role-scoped request register using native Streamlit controls."""

from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

import localization
import request_workflow


_DUBAI = ZoneInfo("Asia/Dubai")
_PAGE_SIZE = 10
_APPROVED = {"Approved", "Ticket approved", "CAB approved", "Simulated"}
_FILTER_DEFAULTS = {
    "rd_reference": "",
    "rd_submitter": None,
    "rd_statuses": [],
    "rd_use_dates": False,
    "rd_dates": (),
}


def _submission(record):
    revision = record["revisions"][-1]
    if revision["status"] == "Draft" or not revision.get("submitted_at"):
        return None
    try:
        value = datetime.fromisoformat(revision["submitted_at"])
        return (value.replace(tzinfo=_DUBAI) if value.tzinfo is None else value).astimezone(_DUBAI)
    except (TypeError, ValueError):
        return None


def _clear_filters():
    for key, value in _FILTER_DEFAULTS.items():
        st.session_state[key] = value.copy() if isinstance(value, list) else value
    st.session_state["rd_page"] = 1


def _new_request(state):
    try:
        request_workflow.start_new(state)
    except request_workflow.WorkflowError:
        st.session_state["rd_creation_error"] = True
    # Native widget callbacks execute before Streamlit's automatic full rerun.


def _view_request(state, reference):
    state["request_view"] = reference
    state["workspace_page"] = "requests"
    # The automatic callback rerun lets the main application dispatch details.


def _change_page(delta):
    st.session_state["rd_page"] = max(1, st.session_state.get("rd_page", 1) + delta)


def _cell(label, value, css=""):
    return (
        '<div class="request-register-cell">'
        f"<small>{escape(label)}</small>"
        f'<span class="{css}">{escape(str(value))}</span></div>'
    )


def render_request_dashboard(state):
    """Render latest revisions; never mutate records or persist outside session."""
    css = Path(__file__).resolve().parent / "assets" / "request_dashboard.css"
    st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
    with st.container(key="request_dashboard"):
        st.markdown(
            '<div class="request-register-heading"><h2>'
            + escape(localization.translate("Request dashboard"))
            + "</h2><p>"
            + escape(localization.translate("Track the latest revision of each demo request."))
            + "</p></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="request-register-notice">'
            + escape(localization.translate(
                "Demo session only. Roles are unverified. Requests and uploaded data are cleared on logout."
            ))
            + "</div>",
            unsafe_allow_html=True,
        )
        user = state.get("demo_user")
        role = state.get("demo_role", "Submitter")
        if not user:
            st.warning(localization.translate("Sign in to view this session's requests."))
            return
        if role not in request_workflow.ROLES:
            st.warning(localization.translate("This demo role cannot access the request dashboard."))
            return

        identity = (user, role)
        if st.session_state.get("rd_identity") != identity:
            _clear_filters()
            st.session_state["rd_identity"] = identity
            st.session_state["rd_scope"] = "all"
        records = list(request_workflow.requests(state).values())
        if role == "Submitter":
            records = [item for item in records if item["submitted_by"] == user]
        records.sort(key=lambda item: (item.get("created_at", ""), item["reference"]), reverse=True)

        copy, action = st.columns([4, 1])
        with copy:
            st.caption(localization.translate(
                "Your requests only. Other submitters' requests are not shown."
                if role == "Submitter" else
                "Demo review view: all requests in this session are visible."
            ))
        with action:
            if role == "Submitter":
                st.button(
                    localization.translate("New request"), key="rd_new", type="primary",
                    on_click=_new_request, args=(state,), use_container_width=True,
                )
            else:
                st.caption(localization.translate("Only the Submitter demo role can create requests."))
        if st.session_state.pop("rd_creation_error", False):
            st.error(localization.translate("The request could not be created. Please try again."))

        with st.container(key="rd_filters"):
            st.markdown("**" + localization.translate("Filters") + "**")
            left, middle, right = st.columns([2, 1.3, 2])
            with left:
                reference = st.text_input(
                    localization.translate("Reference contains"), key="rd_reference",
                    placeholder=localization.translate("Search request references"),
                )
            submitters = sorted({item["submitted_by"] for item in records}, key=str.casefold)
            if st.session_state.get("rd_submitter") not in [None, *submitters]:
                st.session_state["rd_submitter"] = None
            with middle:
                submitter = st.selectbox(
                    localization.translate("Submitter"), [None, *submitters], key="rd_submitter",
                    format_func=lambda value, locale=localization.language(): localization.translate("All submitters", locale) if value is None else value,
                )
            with right:
                statuses = st.multiselect(
                    localization.translate("Statuses"), request_workflow.STATUSES,
                    key="rd_statuses", format_func=lambda value, locale=localization.language(): localization.translate(value, locale),
                    placeholder=localization.translate("All statuses"),
                )
            date_filter = st.checkbox(localization.translate("Filter by submission date"), key="rd_use_dates")
            interval = ()
            if date_filter:
                interval = st.date_input(
                    localization.translate("Submission date interval (Asia/Dubai, UTC+04:00)"),
                    value=(), key="rd_dates",
                    format="YYYY-MM-DD",
                )
                st.caption(localization.translate(
                    "Select a start and end date. Drafts have no submission date and are excluded when this filter is on."
                ))
                if len(interval) != 2:
                    st.info(localization.translate("Choose an end date to apply the submission date interval."))
            st.button(localization.translate("Clear filters"), key="rd_clear", on_click=_clear_filters)

        filtered = []
        for item in records:
            revision = item["revisions"][-1]
            submitted = _submission(item)
            if reference.strip().casefold() not in item["reference"].casefold():
                continue
            if submitter is not None and item["submitted_by"] != submitter:
                continue
            if statuses and revision["status"] not in statuses:
                continue
            if date_filter:
                if submitted is None:
                    continue
                if len(interval) == 2 and not interval[0] <= submitted.date() <= interval[1]:
                    continue
            filtered.append(item)

        scope = st.radio(
            localization.translate("Metric scope"), ["all", "filtered"], key="rd_scope", horizontal=True,
            format_func=lambda value, locale=localization.language(): localization.translate(
                "All visible session requests" if value == "all" else "Filtered requests", locale
            ),
        )
        st.caption(localization.translate(
            "Metrics use your role-visible session requests before filters." if scope == "all" else
            "Metrics use all matching requests across every page."
        ))
        metric_records = records if scope == "all" else filtered
        counts = [item["revisions"][-1]["status"] for item in metric_records]
        metrics = st.columns(4)
        for column, label, count in zip(
            metrics,
            ("Draft", "Submitted / pending", "Approved", "Rejected"),
            (counts.count("Draft"), counts.count("Submitted"),
             sum(status in _APPROVED for status in counts), counts.count("Rejected")),
        ):
            column.metric(localization.translate(label), count)
        st.caption(localization.translate("Approved includes Approved, Ticket approved, CAB approved and Simulated."))
        st.subheader(localization.translate("Request register"))
        st.caption(localization.translate("{0} matching requests of {1} visible in this session").format(
            len(filtered), len(records)
        ))
        if not filtered:
            title = localization.translate("No requests yet" if not records else "No matching requests")
            if records:
                body = localization.translate(
                    "Try a different reference, submitter, status or date interval, or clear the filters."
                )
            elif role == "Submitter":
                body = localization.translate("Create a request to begin inspecting a dataset and tracking its review.")
            else:
                body = localization.translate(
                    "Requests will appear here when a submitter creates one in this session."
                )
            st.markdown(
                f'<div class="request-register-empty"><h3>{escape(title)}</h3><p>{escape(body)}</p></div>',
                unsafe_allow_html=True,
            )
            return

        signature = (identity, reference, submitter, tuple(statuses), date_filter, tuple(interval))
        if st.session_state.get("rd_filter_signature") != signature:
            st.session_state["rd_page"] = 1
            st.session_state["rd_filter_signature"] = signature
        page_count = (len(filtered) + _PAGE_SIZE - 1) // _PAGE_SIZE
        page = min(max(1, st.session_state.get("rd_page", 1)), page_count)
        st.session_state["rd_page"] = page
        start = (page - 1) * _PAGE_SIZE
        for index, item in enumerate(filtered[start:start + _PAGE_SIZE], start=start):
            revision = item["revisions"][-1]
            status = revision["status"]
            tone = "approved" if status in _APPROVED else (
                "rejected" if status == "Rejected" else "pending" if status == "Submitted" else ""
            )
            submitted = _submission(item)
            with st.container(key=f"rd_record_{index}"):
                detail, view = st.columns([9, 1.2], vertical_alignment="center")
                with detail:
                    cells = [
                        _cell(localization.translate("Reference"), item["reference"], "request-register-reference"),
                        _cell(localization.translate("Submitter"), item["submitted_by"]),
                        _cell(localization.translate("Submission date (Asia/Dubai, UTC+04:00)"),
                              submitted.strftime("%Y-%m-%d %H:%M") if submitted else ""),
                        _cell(localization.translate("Status"), localization.translate(status),
                              "request-register-status " + tone),
                        _cell(localization.translate("Rejected by"), localization.translate(revision.get("rejected_by", ""))),
                    ]
                    st.markdown('<div class="request-register-row">' + "".join(cells) + "</div>", unsafe_allow_html=True)
                with view:
                    st.button(
                        localization.translate("View"), key=f"rd_view_{item['reference']}",
                        help=localization.translate("View request {0}").format(item["reference"]),
                        on_click=_view_request, args=(state, item["reference"]), use_container_width=True,
                    )

        previous, summary, following = st.columns([1, 3, 1])
        with previous:
            st.button(localization.translate("Previous"), key="rd_previous", disabled=page == 1,
                      on_click=_change_page, args=(-1,), use_container_width=True)
        with summary:
            st.caption(localization.translate("Page {0} of {1} · Requests {2}–{3} of {4}").format(
                page, page_count, start + 1, min(start + _PAGE_SIZE, len(filtered)), len(filtered)
            ))
        with following:
            st.button(localization.translate("Next"), key="rd_next", disabled=page == page_count,
                      on_click=_change_page, args=(1,), use_container_width=True)
