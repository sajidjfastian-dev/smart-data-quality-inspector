"""Session-only simulated change requests. Never store cell values or send requests."""
from uuid import uuid4

from review_approval import ApprovalRequired, frame_digest, is_approved


FIX_REASONS = (
    "Trimmed whitespace", "Filled missing value", "Standardized date",
    "Removed duplicate row", "Removed duplicate after normalization",
    "Normalized to allowed value",
)


def generate_ticket(state, dataset, original, selected, choice, changes):
    context = state.get("review_contexts", {}).get(dataset, {})
    if (context.get("original") != frame_digest(original)
            or not is_approved(state, dataset, selected, choice)):
        raise ApprovalRequired("Current final demo approval is required to generate a ticket.")
    approval = state["final_approvals"][dataset]
    previous = state.get("demo_change_tickets", {}).get(dataset)
    if previous and not previous["outdated"] and previous["approval_id"] == approval["approval_id"]:
        return previous
    # Only application-owned categories and aggregate counts enter the ticket.
    # No file/column names, custom rule text, row identifiers, or values.
    if choice == "Original data":
        changes = changes.iloc[:0]
    reasons = changes["Change reason"]
    if not reasons.isin(FIX_REASONS).all():
        raise ValueError("Unsupported change category.")
    ticket = {
        "reference": "DEMO-CHG-" + uuid4().hex[:12].upper(),
        "approval_id": approval["approval_id"],
        "version": approval["version"],
        "digest": approval["digest"],
        "choice": choice,
        "outdated": False,
        "affected_rows": int(changes["Original row"].nunique()),
        "changed_cells": int(changes["Column position"].notna().sum()),
        "removed_rows": int(changes["Column position"].isna().sum()),
        "remaining_findings": approval["remaining_findings"],
        "original_rows": len(original),
        "proposed_rows": len(selected),
        "fixes": {reason: int(reasons.eq(reason).sum()) for reason in FIX_REASONS
                  if reasons.eq(reason).any()},
    }
    state.setdefault("demo_change_tickets", {})[dataset] = ticket
    return ticket


def render_demo_ticket(state, dataset, original, selected, choice, changes):
    from localization import native as st, translate as t

    st.subheader(t("Demo production-change ticket"))
    st.caption(t("Simulation only. No service desk request is submitted and no production data is changed."))
    approved = is_approved(state, dataset, selected, choice)
    if not approved:
        st.info(t("Current final demo approval is required to generate a ticket."))
    if st.button(t("Generate demo ticket"), key=f"demo_ticket_{dataset}", disabled=not approved):
        try:
            generate_ticket(state, dataset, original, selected, choice, changes)
        except ApprovalRequired as error:
            st.error(t(str(error)))
    ticket = state.get("demo_change_tickets", {}).get(dataset)
    if not ticket:
        return
    with st.container(border=True):
        if ticket["outdated"]:
            st.warning(t("Outdated demo ticket — review and approve the current version, then generate a new ticket."))
        else:
            st.success(t("Demo ticket preview — not submitted"))
        st.text(t("Demo reference") + ": " + ticket["reference"])
        st.text(t("Approved dataset version") + ": " + ticket["version"])
        st.text(t("Approved data fingerprint") + ": " + ticket["digest"])
        st.text(t("Data to send") + ": " + t(ticket["choice"]))
        st.caption(t("Aggregate summary only: filenames, column names, row identifiers and cell values are omitted."))
        for label, field in [
            ("Affected rows", "affected_rows"), ("Changed cells", "changed_cells"),
            ("Rows removed", "removed_rows"), ("Original rows", "original_rows"),
            ("Proposed rows", "proposed_rows"), ("Remaining findings", "remaining_findings"),
        ]:
            st.text(t(label) + ": " + str(ticket[field]))
        st.markdown("**" + t("Proposed fixes") + "**")
        if not ticket["fixes"]:
            st.info(t("No fixes proposed; the approved version is unchanged."))
        for reason, count in ticket["fixes"].items():
            st.text(t(reason) + ": " + str(count))
        st.caption(t("Fix counts are changed cells, except duplicate removal which counts rows. Affected rows are counted once."))
        st.markdown("**" + t("Proposed validation") + "**")
        st.write(t("Before any real change, independently authorize the request and confirm the dataset version. Test the fixes in staging, compare row counts and changed cells, rerun the approved quality rules, and review every remaining finding. Stop if results differ from the approved summary."))
        st.markdown("**" + t("Proposed rollback") + "**")
        st.write(t("Before execution, take an access-controlled backup and verify restoration in staging. If validation fails, stop the change, restore the pre-change snapshot using the approved operational procedure, and rerun integrity and quality checks. This demo creates no backup and performs no rollback."))
        st.caption(t("Session only; cleared on logout. Destination sending still requires current final approval and separate destination consent. Generating a ticket sends nothing."))
