"""Read-only submitted request details and explicit demo-role decisions."""
from html import escape
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from localization import native as st, translate, language
from request_approval_translations import REQUEST_APPROVAL_ARABIC
from request_workflow import (
    requests, open_draft, revise,
    WorkflowError, valid_snapshot, demo_review_action, approved_download, record_delivery_step,
)
from review_approval import is_approved
from review_ui import render_checker_review
from issue_workspace import render_findings
from security_guardrails import mask_text_with_dataset
from account_identity import owns, public_example


def t(value, locale=None):
    selected = language() if locale is None else locale
    if selected == "العربية" and value in REQUEST_APPROVAL_ARABIC:
        return REQUEST_APPROVAL_ARABIC[value]
    return translate(value, selected)


def _display_datetime(value):
    """Format application timestamps without modifying stored or uploaded data."""
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo("Asia/Dubai"))
        return parsed.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return str(value)


def _timeline_frame(events):
    frame = pd.DataFrame(events)
    if "Date (Asia/Dubai)" in frame:
        frame["Date (Asia/Dubai)"] = frame["Date (Asia/Dubai)"].map(_display_datetime)
    return frame


def confirm_demo_action(state, reference, number, action):
    from approval_evidence import binding
    expected_seal = binding(state, reference, number)
    @st.dialog(t("Confirm approval"))
    def confirmation():
        st.write(t("Confirm this action for request {0}, revision {1}?").format(reference, number))
        st.caption(t("This is a demo approval. No external ticket or production change will be sent."))
        evidence = None
        if action in ("ticket", "cab"):
            st.caption(t("Optional evidence: PNG, JPEG or UTF-8 text, up to 5 MB per file and 20 MB per session. Cleared on logout; never saved to shared sample history."))
            evidence = st.file_uploader(t("Approval evidence"), type=["png", "jpg", "jpeg", "txt"],
                                        max_upload_size=5, key=f"evidence_{reference}_{number}_{action}")
        yes, no = st.columns(2)
        def apply_confirmation():
            try:
                if action in ("ticket", "cab"):
                    from approval_evidence import approve_with_evidence
                    approve_with_evidence(state, reference, number, action,
                                          {"name": evidence.name, "data": evidence.getvalue()} if evidence else None,
                                          expected_seal=expected_seal)
                else:
                    if binding(state, reference, number) != expected_seal:
                        raise WorkflowError("The submitted snapshot changed. Reopen approval.")
                    demo_review_action(state, reference, number, action)
            except WorkflowError as error:
                state["approval_confirmation_error"] = str(error)
        if yes.button(t("Confirm"), key="confirm_demo_approval", type="primary", on_click=apply_confirmation):
            st.rerun()
        if no.button(t("Cancel"), key="cancel_demo_approval"):
            st.rerun()
    confirmation()


def _render_approval_steps(state, record, rev, latest, reference, number, snap, snapshot_verified):
    css = (Path(__file__).parent / "assets" / "request_approval_steps.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    status = rev["status"]
    completed = {
        "Draft": 0, "Submitted": 0, "Approved": 1, "Ticket approved": 2,
        "CAB approved": 3, "Simulated": 3, "Rejected": 0,
    }
    active = {"Submitted": 0, "Approved": 1, "Ticket approved": 2, "CAB approved": 3, "Simulated": 3}.get(status)
    if status in ("CAB approved", "Simulated") and rev.get("download_requested"):
        completed[status], active = (5, None) if rev.get("implementation") else (4, 4)
    def delivery(implement=False):
        try:
            record_delivery_step(state, reference, number, implement)
        except WorkflowError as error:
            state["approval_confirmation_error"] = str(error)
    can_act = bool(
        latest and snapshot_verified and state.get("demo_user")
        and state.get("demo_role", "Submitter") == "Submitter"
        and owns(state, record)
    )
    ticket = rev.get("ticket")
    ticket_ready = bool(
        can_act and snap and ticket and not ticket.get("outdated")
        and ticket.get("digest") == snap.get("selected_digest")
        and is_approved(rev["approval_state"], f"{reference}/r{number}", snap["selected"], snap["choice"])
    )
    steps = [
        (
            "Request review",
            "Review proposed changes and remaining findings before approving or rejecting the request.",
            "Request approval recorded.", None, None,
        ),
        (
            "Service-desk ticket approval",
            "Review the generated service-desk ticket. No real ticket is sent.",
            "Ticket approval recorded.", "ticket", "Approve ticket",
        ),
        (
            "CAB approval",
            "Record the change-advisory-board approval after ticket approval.",
            "CAB approval recorded.", "cab", "Approve CAB step",
        ),
        (
            "Download approved file",
            "Download the reviewed version after all approvals. Privacy masking remains applied; no production system is changed.",
            "Approved file download requested.", None, None,
        ),
        ("Implemented on production", "Record a simulated implementation. No production system is changed.",
         "Implementation confirmed (simulated).", None, None),
    ]
    locked = [
        "Submit this draft to begin request review.",
        "Locked until request review is approved.",
        "Locked until the service-desk ticket is approved.",
        "Locked until CAB approval is recorded.",
        "Locked until the approved file download is requested.",
    ]
    with st.container(key="demo_approval_steps"):
        st.markdown(
            '<div class="approval-sequence-intro"><h3>' + escape(t("Approval steps"))
            + '</h3><p>' + escape(t(
                "Complete each step in order. Approvals and implementation are simulated. Times are Asia/Dubai."
            )) + '</p></div>', unsafe_allow_html=True,
        )
        if status not in completed:
            st.info(t("Approval status is unavailable. Actions are locked."))
        for index, (title, description, done, action, label) in enumerate(steps):
            phase, badge, detail = "waiting", "Waiting", locked[index]
            if index < completed.get(status, 0):
                phase, badge, detail = "completed", "Completed", done
            elif status == "Rejected":
                if index == 0:
                    phase, badge, detail = "rejected", "Rejected", "Request review was rejected. Later steps did not start."
                else:
                    detail = "Locked because request review was rejected."
            elif status not in completed:
                detail = "Approval status is unavailable. Actions are locked." if index == 0 else "Not reached in this revision."
            elif index == active:
                if latest:
                    phase, badge, detail = "current", "Current step", description
                else:
                    badge, detail = "Not completed", "This revision stopped at this stage. Decisions are available only for the latest revision."
            elif not latest:
                detail = ("This revision was not submitted; no approval steps were started."
                          if status == "Draft" and index == 0 else "Not reached in this revision.")
            elif status == "Draft" and index == 0:
                badge = "Not started"
            with st.container(key=f"demo_approval_step_{index + 1}"):
                event_names = ["Request approved; demo ticket generated", "Ticket approved", "CAB approved",
                               "Approved file download requested", "Implemented on production (simulated)"]
                match = next((entry for entry in reversed(rev.get("timeline", []))
                              if entry["Action"] == event_names[index]), None)
                metadata = ('<div class="approval-step-meta">' + escape(str(match["By"])) + ' · '
                            + escape(_display_datetime(match["Date (Asia/Dubai)"])) + '</div>') if match else ""
                st.markdown(
                    f'<div class="approval-step-header approval-step-header--{phase}">'
                    f'<span class="approval-step-number">{index + 1}</span><div><h4>'
                    + escape(t(title)) + '</h4><p>' + escape(t(detail))
                    + '</p>' + metadata + '</div><span class="approval-step-status">' + escape(t(badge))
                    + '</span></div>', unsafe_allow_html=True,
                )
                if latest and index == active:
                    if not snapshot_verified:
                        st.caption(t("Submitted snapshot unavailable. Approval actions are locked."))
                    elif not can_act:
                        st.caption(t("Demo decisions are not available in this view."))
                    elif index > 0 and not ticket_ready:
                        st.caption(t("A current approved demo ticket is required."))
                if index == 4:
                    eligible = bool(latest and ticket_ready and status in ("CAB approved", "Simulated")
                                    and rev.get("download_requested") and not rev.get("implementation"))
                    if not rev.get("implementation"):
                        ack = st.checkbox(t("I confirm implementation for this revision in the demo only."),
                                          key=f"implementation_ack_{reference}_{number}", disabled=not eligible)
                        st.button(t("Confirm simulated implementation"), type="primary",
                                  key=f"implement_{reference}_{number}", disabled=not (eligible and ack),
                                  on_click=delivery, args=(True,))
                elif index == 3:
                    ready = latest and ticket_ready and status in ("CAB approved", "Simulated")
                    payload = b""
                    if ready:
                        try:
                            # Authorization uses the live session on the script thread.
                            # Deferred download workers cannot read st.session_state.
                            payload = approved_download(state, reference, number)
                        except WorkflowError as error:
                            ready = False
                            st.warning(t(str(error)))
                    st.download_button(
                        t("Download approved file"),
                        data=payload,
                        file_name=f"{reference}_r{number}_approved.csv",
                        mime="text/csv", disabled=not ready, on_click=delivery,
                        key=f"approved_download_{reference}_{number}", type="primary",
                    )
                    if ready:
                        st.caption(t("A download request is not proof of receipt or production implementation."))
                elif latest and index == 0 and status == "Submitted":
                    checked = st.checkbox(
                        t("I reviewed the changes and remaining findings"),
                        key=f"owner_ack_{reference}_{number}", disabled=not can_act,
                    )
                    if record.get("synthetic"):
                        from persistent_demo import REASONS
                        reason = st.selectbox(
                            t("Rejection reason"), REASONS,
                            format_func=lambda value, locale=language(): t(value, locale),
                            key=f"reject_reason_{reference}_{number}", disabled=not can_act,
                        )
                    else:
                        reason = st.text_area(
                            t("Rejection reason"), key=f"reject_reason_{reference}_{number}", disabled=not can_act,
                        )
                    if can_act and not reason.strip():
                        st.caption(t("Enter a rejection reason to enable Reject request."))
                    if can_act and not snap["privacy_reviewed"]:
                        st.caption(t("Review data privacy before approving this revision."))
                    left, right = st.columns(2)
                    decision = None
                    if left.button(
                        t("Approve request"), disabled=not (can_act and checked and snap["privacy_reviewed"]),
                        key=f"owner_yes_{reference}_{number}",
                    ):
                        decision = True
                    if right.button(
                        t("Reject request"), disabled=not can_act or not reason.strip(),
                        key=f"owner_no_{reference}_{number}",
                    ):
                        decision = False
                    if decision is not None:
                        try:
                            safe_reason = reason if record.get("synthetic") else mask_text_with_dataset(
                                reason, snap["original"], snap["protected"],
                            )
                            if decision:
                                confirm_demo_action(state, reference, number, "approve")
                            else:
                                demo_review_action(state, reference, number, "reject", safe_reason)
                                st.rerun()
                        except WorkflowError as error:
                            st.error(t(str(error)))
                elif (latest and index > 0 and status in completed
                      and status not in ("Rejected", "Simulated") and index >= completed[status]):
                    if st.button(
                        t(label), disabled=not (index == active and ticket_ready),
                        key=f"{action}_{reference}_{number}", type="primary",
                    ):
                        try:
                            confirm_demo_action(state, reference, number, action)
                        except WorkflowError as error:
                            st.error(t(str(error)))


def render_request_details(state, reference):
    error = state.pop("approval_confirmation_error", None)
    if error:
        st.error(t(error))
    record = requests(state).get(reference)
    if not record:
        st.warning(t("Request not found in this session."))
        return
    role = state.get("demo_role", "Submitter")
    if not owns(state, record) and not public_example(record):
        st.warning(t("Request not found in this session."))
        return
    st.header(reference)
    if not public_example(record) and record.get("sample_copy_of"):
        st.info(t("Personal sample copy · approval history is simulated."))
    from public_sample import SOURCE_ID, ATTRIBUTION, NOTICE
    if record.get("source_id") == SOURCE_ID:
        st.caption(ATTRIBUTION + " " + NOTICE)
    else:
        st.caption(t("Personal sample copy stored in the database.") if record.get("sample_copy_of")
                   else t("Shared synthetic example stored in the database.") if record.get("synthetic")
                   else t("Private request: cleared on logout."))
    st.caption(t("No real service-desk request or production change is performed."))
    st.text(t("Session") + ": " + record.get("session_id", t("Current private session")))
    number = st.selectbox(t("Revision"), list(range(1, len(record["revisions"])+1)),
                          index=len(record["revisions"])-1, key="detail_revision_"+reference)
    rev = record["revisions"][number-1]
    latest = rev is record["revisions"][-1]
    st.text(t("Submitted by") + ": " + record["submitted_by"])
    st.text(t("File") + ": " + record["file"])
    st.text(t("Status") + ": " + t(rev["status"]))
    st.text(t("Submitted date (Asia/Dubai)") + ": " + _display_datetime(rev["submitted_at"]))
    if rev["rejected_by"]:
        st.text(t("Rejected by") + ": " + t(rev["rejected_by"]))
        st.text(t("Rejection reason") + ": " + rev["rejection_reason"])
    if not latest:
        st.info(t("Historical revision. Decisions are available only for the latest revision."))
    if role == "Submitter" and latest and owns(state, record):
        if rev["status"] == "Draft":
            st.button(t("Continue draft"), key="continue_"+reference, type="primary",
                      on_click=open_draft, args=(state, reference))
        else:
            def edit_revision():
                revise(state, reference)
                open_draft(state, reference)
                state.pop("detail_revision_"+reference, None)
            st.button(t("Create new draft revision"), key="revise_"+reference, on_click=edit_revision)
    snap = rev.get("snapshot") or rev.get("working")
    if not snap:
        st.info(t("Choose Continue draft to open the upload area.") if latest and role == "Submitter" and rev["status"] == "Draft"
                else t("No submitted dataset is available for this revision."))
        _render_approval_steps(state, record, rev, latest, reference, number, None, False)
        st.subheader(t("Request timeline"))
        st.dataframe(_timeline_frame(rev["timeline"]).rename(columns=t), hide_index=True, width="stretch")
        return
    protected = snap["protected"] if snap["privacy_reviewed"] else set(snap["original"].columns)
    snapshot_verified = False
    if rev.get("snapshot"):
        try:
            valid_snapshot(rev)
            snapshot_verified = True
        except WorkflowError as error:
            st.error(t(str(error)))
            return
    metrics = st.columns(3)
    metrics[0].metric(t("Original rows"), f"{len(snap['original']):,}")
    metrics[1].metric(t("Original findings"), f"{len(snap['issues']):,}")
    metrics[2].metric(t("Remaining findings"), f"{len(snap['remaining']):,}")
    with st.expander(t("Submitted quality rules"), expanded=False):
        rules = snap["rules"]
        st.write(t("Enabled checks") + ": " + ", ".join(t(value) for value in rules["enabled"]))
        for label, key in [("Email columns", "email"), ("Date columns", "date"), ("Numeric columns", "numeric")]:
            st.text(t(label) + ": " + ", ".join(map(str, rules[key])))
        st.text(t("Outlier multiplier") + ": " + str(rules["iqr"]))
        for rule in rules["custom"]:
            expected = mask_text_with_dataset(rule["expected"], snap["original"], protected)
            st.text(str(rule["column"]) + " · " + t(rule["kind"]) + " · " + expected)
    if rev.get("snapshot"):
        namespace = f"{reference}/r{number}"
        with st.container(key="submitted_preview"):
            st.subheader(t("Preview & export"))
            st.caption(t("Demo approver review in this session. Review this submitted revision before deciding."))
            data_label = "Corrected data preview" if snap["choice"] == "Fixed copy" else "Submitted data preview"
            comparison_tab, data_tab = st.tabs([t("Compare changes"), t(data_label)])
            with comparison_tab:
                render_checker_review(rev["approval_state"], namespace, snap["original"], snap["selected"],
                                      snap["changes"], snap["remaining"], protected, snap["choice"], actions=False,
                                      show_findings=False)
            with data_tab:
                from change_preview import render_change_preview
                render_change_preview(snap["selected"], snap["changes"], protected,
                                      f"submitted_{reference}_{number}_{snap['seal']}", label=data_label)
    elif latest and role == "Submitter" and rev["status"] == "Draft":
        st.info(t("Continue the draft to review changes and submit."))
    ticket = rev.get("ticket")
    if not ticket:
        _render_approval_steps(state, record, rev, latest, reference, number, snap, snapshot_verified)
    if ticket:
        with st.container(border=True):
            st.subheader(t("Production-change ticket"))
            st.text(t("Ticket reference") + ": " + ticket["reference"])
            st.caption(t("Aggregate summary only: filenames, column names, row identifiers and cell values are omitted."))
            st.text(t("Approved dataset version") + ": " + ticket["version"])
            for label, field in [("Changed cells", "changed_cells"), ("Rows removed", "removed_rows"),
                                 ("Affected rows", "affected_rows"), ("Remaining findings", "remaining_findings")]:
                st.text(t(label) + ": " + str(ticket[field]))
            for reason, count in ticket["fixes"].items():
                st.text(t(reason) + ": " + str(count))
            st.caption(t("Validate in staging and take a verified backup before any real production change. This demo does neither."))
        _render_approval_steps(state, record, rev, latest, reference, number, snap, snapshot_verified)
    if snapshot_verified and owns(state, record):
        from approval_evidence import render_evidence
        render_evidence(state, reference, number, t, st)
    st.subheader(t("Request timeline"))
    timeline = _timeline_frame(rev["timeline"])
    if not timeline.empty:
        timeline["Action"] = timeline["Action"].map(t)
        timeline["By"] = timeline["By"].map(t)
        st.dataframe(timeline.rename(columns=t), hide_index=True, width="stretch")
