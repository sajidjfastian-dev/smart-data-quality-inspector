"""Read-only submitted request details and explicit demo-role decisions."""
import pandas as pd
from localization import native as st, translate as t, language, display_findings
from request_workflow import (
    requests, current, open_draft, revise, owner_decision, advance,
    WorkflowError, valid_snapshot,
)
from review_ui import render_checker_review
from issue_workspace import render_findings
from security_guardrails import mask_text_with_dataset


def render_request_details(state, reference):
    record = requests(state).get(reference)
    if not record:
        st.warning(t("Request not found in this session."))
        return
    role = state.get("demo_role", "Submitter")
    if role == "Submitter" and record["submitted_by"] != state.get("demo_user"):
        st.warning(t("Request not found in this session."))
        return
    st.header(reference)
    st.caption(t("Session-only demo. No real service-desk request or production change is performed."))
    number = st.selectbox(t("Revision"), list(range(1, len(record["revisions"])+1)),
                          index=len(record["revisions"])-1, key="detail_revision_"+reference)
    rev = record["revisions"][number-1]
    latest = rev is record["revisions"][-1]
    st.text(t("Submitted by") + ": " + record["submitted_by"])
    st.text(t("File") + ": " + record["file"])
    st.text(t("Status") + ": " + t(rev["status"]))
    st.text(t("Submitted date (Asia/Dubai)") + ": " + (rev["submitted_at"] or "—"))
    if rev["rejected_by"]:
        st.text(t("Rejected by") + ": " + t(rev["rejected_by"]))
        st.text(t("Rejection reason") + ": " + rev["rejection_reason"])
    if not latest:
        st.info(t("Historical revision. Decisions are available only for the latest revision."))
    if role == "Submitter" and latest:
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
        st.info(t("Upload a file in the sidebar to begin inspection."))
        st.subheader(t("Request timeline"))
        st.dataframe(pd.DataFrame(rev["timeline"]).rename(columns=t), hide_index=True, width="stretch")
        return
    protected = snap["protected"] if snap["privacy_reviewed"] else set(snap["original"].columns)
    if rev.get("snapshot"):
        try:
            valid_snapshot(rev)
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
    with st.expander(t("Original findings")):
        render_findings(snap["issues"], protected, f"request_{reference}_{number}_original",
                        snap["original"], downloads=False)
    if rev.get("snapshot"):
        namespace = f"{reference}/r{number}"
        render_checker_review(rev["approval_state"], namespace, snap["original"], snap["selected"],
                              snap["changes"], snap["remaining"], snap["protected"], snap["choice"], actions=False)
    else:
        st.info(t("Continue the draft to review changes and submit."))
    ticket = rev.get("ticket")
    if ticket:
        with st.container(border=True):
            st.subheader(t("Demo production-change ticket"))
            st.text(t("Demo reference") + ": " + ticket["reference"])
            st.caption(t("Aggregate summary only: filenames, column names, row identifiers and cell values are omitted."))
            st.text(t("Approved dataset version") + ": " + ticket["version"])
            for label, field in [("Changed cells", "changed_cells"), ("Rows removed", "removed_rows"),
                                 ("Affected rows", "affected_rows"), ("Remaining findings", "remaining_findings")]:
                st.text(t(label) + ": " + str(ticket[field]))
            for reason, count in ticket["fixes"].items():
                st.text(t(reason) + ": " + str(count))
            st.caption(t("Validate in staging and take a verified backup before any real production change. This demo does neither."))
    with st.container(border=True):
        st.subheader(t("Demo approval steps"))
        st.caption(t("Request review → ticket approval → CAB approval → simulated application"))
        if latest and role == "Approver" and rev["status"] == "Submitted":
            checked = st.checkbox(t("I reviewed the changes and remaining findings"), key=f"owner_ack_{reference}_{number}")
            reason = st.text_area(t("Rejection reason"), key=f"reject_reason_{reference}_{number}")
            left, right = st.columns(2)
            decision = None
            if left.button(t("Approve request"), disabled=not checked, key=f"owner_yes_{reference}_{number}"):
                decision = True
            if right.button(t("Reject request"), key=f"owner_no_{reference}_{number}"):
                decision = False
            if decision is not None:
                try:
                    safe_reason = mask_text_with_dataset(reason, snap["original"], snap["protected"])
                    owner_decision(state, reference, decision, safe_reason)
                    st.rerun()
                except WorkflowError as error:
                    st.error(t(str(error)))
        elif latest and role == "Approver":
            for stage, expected_role, expected_status, label in [
                ("ticket", "Approver", "Approved", "Approve demo ticket"),
                ("cab", "Approver", "Ticket approved", "Approve CAB step"),
                ("simulate", "Approver", "CAB approved", "Simulate production application"),
            ]:
                if role != expected_role:
                    continue
                if st.button(t(label), disabled=rev["status"] != expected_status,
                             key=f"{stage}_{reference}_{number}", type="primary"):
                    try:
                        advance(state, reference, stage)
                        st.rerun()
                    except WorkflowError as error:
                        st.error(t(str(error)))
        else:
            st.info(t("Switch demo role in the sidebar to perform the next approval step."))
        if rev["status"] == "Simulated":
            st.success(t("Simulation completed. No production data was changed."))
    st.subheader(t("Request timeline"))
    timeline = pd.DataFrame(rev["timeline"])
    if not timeline.empty:
        timeline["Action"] = timeline["Action"].map(t)
        timeline["By"] = timeline["By"].map(t)
        st.dataframe(timeline.rename(columns=t), hide_index=True, width="stretch")
