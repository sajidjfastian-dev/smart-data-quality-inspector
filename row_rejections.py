"""Restore rejected corrections by original position, never by mutable row values."""
import pandas as pd
from correction_workbench import retained_rows, build_changes, save_copy
from review_approval import frame_digest
from request_workflow import current, WorkflowError, event, require_role


def restore_rows(original, corrected, changes, rejected):
    rejected = set(rejected)
    if any(not isinstance(row, int) or row < 1 or row > len(original) for row in rejected):
        raise WorkflowError("Invalid original row.")
    mapping = retained_rows(original, {"changes": changes})
    positions = {origin: pos for pos, origin in enumerate(mapping)}
    # A later deduplication may remove a previously rejected row. Rejection
    # never overrides removal; it only restores cells in retained rows.
    rows = mapping
    pieces = [original.iloc[[origin]] if origin + 1 in rejected else corrected.iloc[[positions[origin]]]
              for origin in rows]
    result = pd.concat(pieces, ignore_index=True) if pieces else original.iloc[:0].copy()
    return result, build_changes(original, result, rows, previous=changes)


def choices(state, reference, original):
    policy = current(state, reference).get("row_rejections", {})
    return policy.get("rows", []) if policy.get("original") == frame_digest(original) else []


def reject_row(state, reference, dataset, original, corrected, changes, row):
    require_role(state, "Submitter")
    from account_identity import owns
    if not owns(state, state["demo_requests"][reference]):
        raise WorkflowError("Request not found in this session.")
    rev = current(state, reference)
    if rev["status"] != "Draft":
        raise WorkflowError("Create a new draft revision before rejecting fixes.")
    record = state.get("fix_change_indexes", {}).get(dataset)
    if not record or record["original"] != frame_digest(original) or record["fixed"] != frame_digest(corrected):
        raise WorkflowError("The correction history changed. Reopen the review.")
    editable = changes.loc[changes["Column position"].notna(), "Original row"]
    if not record["changes"].equals(changes) or int(row) not in set(editable):
        raise WorkflowError("This row has no current correction to reject.")
    rejected = sorted(set(choices(state, reference, original)) | {int(row)})
    result, updated = restore_rows(original, corrected, changes, rejected)
    if state["demo_requests"][reference].get("synthetic"):
        from persistent_demo import make_private
        make_private(state, reference)
        reference = state["active_request_ref"]
        rev = current(state, reference)
    rev["row_rejections"] = {"original": frame_digest(original), "rows": rejected}
    rev["working"] = {**rev["working"], "selected": result, "changes": updated, "choice": "Fixed copy"}
    rev["_needs_rescan"] = True
    event(rev, "Row fix rejected", state["demo_user"], f"Original row {row}")
    save_copy(state, dataset, original, result, updated)
    state["batch_export_cache"] = None
    state["data_insights_cache"] = {}
    # A prior exact-version acknowledgement cannot carry over to the new copy.
    for key in list(state):
        if str(key).startswith("submit_ack_"):
            state.pop(key, None)
