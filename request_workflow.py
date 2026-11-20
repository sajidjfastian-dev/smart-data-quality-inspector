"""Demo request lifecycle. All state is session-only; this module performs no I/O.

Submitted snapshots are detached from working data. Approval/ticket records live
inside a revision-local namespace, never under the uploaded filename.
"""
from copy import deepcopy
from datetime import datetime
from secrets import randbelow
import hashlib
import json
from zoneinfo import ZoneInfo

import pandas as pd

from review_approval import frame_digest, sync_context, approve
from demo_change_ticket import generate_ticket
from account_identity import owns, auth_state, is_seed, is_local_demo, sample_seed_state

ROLES = ("Submitter", "Approver")
STATUSES = ("Draft", "Submitted", "Approved", "Rejected", "Ticket approved", "CAB approved", "Simulated")
IDENTITIES = {"Approver": "Demo Approver"}


class WorkflowError(ValueError):
    pass


def timestamp():
    return datetime.now(ZoneInfo("Asia/Dubai")).isoformat(timespec="seconds")


def require_role(state, role):
    if not is_seed(state) and not is_local_demo(state):
        from account_auth import session_identity
        identity = session_identity(state.get("_auth_session"))
        if not identity or identity["subject"] != state.get("auth_subject"):
            raise WorkflowError("Your account session expired. Sign in again.")
    if not state.get("demo_user") or state.get("demo_role", "Submitter") != role:
        raise WorkflowError("Switch to the required demo role before performing this action.")


def requests(state):
    return state.setdefault("demo_requests", {})


def current(state, reference):
    if not owns(state, requests(state).get(reference)):
        raise WorkflowError("Request not found in this session.")
    return requests(state)[reference]["revisions"][-1]


def event(revision, action, actor, reason=""):
    revision["timeline"].append({"Date (Asia/Dubai)": timestamp(), "Action": action, "By": actor, "Reason": reason})


def new_request(state, number_factory=None):
    require_role(state, "Submitter")
    all_requests = requests(state)
    year = datetime.now(ZoneInfo("Asia/Dubai")).year
    draw = number_factory or (lambda: randbelow(1_000_000))
    for _ in range(100):
        reference = f"DQ-{year}-{draw():06d}"
        if reference not in all_requests:
            break
    else:
        raise WorkflowError("Could not allocate a unique request reference. Try again.")
    rev = {"number": 1, "status": "Draft", "submitted_at": None, "rejected_by": "",
           "rejection_reason": "", "timeline": [], "snapshot": None, "approval_state": {}}
    event(rev, "Draft created", state["demo_user"])
    all_requests[reference] = {"reference": reference, "submitted_by": state["demo_user"],
                               "created_at": timestamp(), "revisions": [rev], "file": "",
                               "session_id": state.get("demo_session_id", "Current private session")}
    if state.get("auth_subject"):
        all_requests[reference]["owner_id"] = state["auth_subject"]
    state["active_request_ref"] = reference
    return reference


def bind_draft(state, dataset, data):
    """Create once per imported file object, or bind a New request placeholder."""
    bindings = state.setdefault("request_bindings", {})
    bound = bindings.get(dataset)
    if bound and bound["data"] is data:
        return bound["reference"]
    pending = state.get("active_request_ref")
    if pending in requests(state) and current(state, pending)["status"] == "Draft" and not requests(state)[pending]["file"]:
        reference = pending
    else:
        reference = new_request(state)
    requests(state)[reference]["file"] = dataset
    bindings[dataset] = {"data": data, "reference": reference}
    return reference


def save_draft(state, reference, payload):
    require_role(state, "Submitter")
    revision = current(state, reference)
    if revision["status"] != "Draft":
        raise WorkflowError("This version is frozen. Create a new draft revision to change it.")
    from persistent_demo import save_working
    if save_working(state, reference, payload):
        return
    # Working references only. A detached snapshot is taken exactly once on submission.
    revision["working"] = payload
    revision.pop("_needs_rescan", None)


def submit(state, reference):
    if current(state, reference).get("_needs_rescan"):
        raise WorkflowError("Refresh the correction review before submitting.")
    if requests(state)[reference].get("_db_version") and not state.get("_db_transaction"):
        from persistent_demo import transaction
        return transaction(state, reference, lambda local: submit(local, reference))
    require_role(state, "Submitter")
    rev = current(state, reference)
    if rev["status"] != "Draft":
        raise WorkflowError("Only a draft can be submitted.")
    payload = rev.get("working")
    if not payload or not payload["privacy_reviewed"]:
        raise WorkflowError("Inspect the data and review its privacy settings before submission.")
    snapshot = deepcopy(payload)
    # Avoid retaining two copies when the original itself is submitted.
    if snapshot["choice"] == "Original data":
        snapshot["selected"] = snapshot["original"]
    snapshot["original_digest"] = frame_digest(snapshot["original"])
    snapshot["selected_digest"] = frame_digest(snapshot["selected"])
    snapshot["seal"] = snapshot_seal(snapshot)
    namespace = f"{reference}/r{rev['number']}"
    sync_context(rev["approval_state"], namespace, snapshot["original"],
                 snapshot["selected"] if snapshot["choice"] == "Fixed copy" else None,
                 snapshot["rules"], snapshot["protected"], snapshot["privacy_reviewed"])
    rev.update(snapshot=snapshot, status="Submitted", submitted_at=timestamp())
    rev.pop("working", None)
    event(rev, "Submitted for approver review", state["demo_user"])
    return rev


def snapshot_seal(snap):
    contents = (
        frame_digest(snap["original"]), frame_digest(snap["selected"]),
        frame_digest(snap["issues"]), frame_digest(snap["remaining"]), frame_digest(snap["changes"]),
        json.dumps(snap["rules"], sort_keys=True), sorted(map(str, snap["protected"])), snap["privacy_reviewed"], snap["choice"],
    )
    # Older sealed histories did not contain selection metadata.
    if "rule_selections" in snap:
        contents += (json.dumps(snap["rule_selections"], sort_keys=True),)
    return hashlib.sha256(repr(contents).encode()).hexdigest()


def valid_snapshot(revision):
    snap = revision.get("snapshot")
    if not snap or snapshot_seal(snap) != snap["seal"]:
        raise WorkflowError("The submitted snapshot changed. Create a new revision and resubmit.")
    return snap


def approved_download(state, reference, number):
    """Validate the latest approved revision again when preparing its download."""
    require_role(state, "Submitter")
    record = requests(state).get(reference)
    if not owns(state, record):
        raise WorkflowError("Request not found in this session.")
    rev = record["revisions"][-1]
    if rev["number"] != number or rev["status"] not in ("CAB approved", "Simulated"):
        raise WorkflowError("Complete request, ticket and CAB approvals before downloading this revision.")
    snap = valid_snapshot(rev)
    ticket = rev.get("ticket")
    from review_approval import is_approved
    if (not snap["privacy_reviewed"] or not ticket or ticket.get("outdated")
            or ticket.get("digest") != snap["selected_digest"]
            or not is_approved(rev["approval_state"], f"{reference}/r{number}",
                               snap["selected"], snap["choice"])):
        raise WorkflowError("A current approved demo ticket is required.")
    from security_guardrails import mask_dataframe
    return mask_dataframe(snap["selected"], snap["protected"]).to_csv(index=False).encode("utf-8-sig")


def owner_decision(state, reference, approved, reason=""):
    if requests(state)[reference].get("_db_version") and not state.get("_db_transaction"):
        from persistent_demo import transaction, REASONS
        if not approved and reason not in REASONS:
            raise WorkflowError("Choose a predefined reason for a shared demo request.")
        return transaction(state, reference, lambda local: owner_decision(local, reference, approved, reason))
    require_role(state, "Approver")
    rev = current(state, reference)
    if rev["status"] == "Approved" and approved:
        valid_snapshot(rev)
        return rev
    if rev["status"] != "Submitted":
        raise WorkflowError("Only submitted requests can receive an owner decision.")
    snap = valid_snapshot(rev)
    if not approved:
        if not reason.strip():
            raise WorkflowError("Enter a rejection reason.")
        rev.update(status="Rejected", rejected_by=IDENTITIES["Approver"], rejection_reason=reason.strip())
        event(rev, "Rejected", IDENTITIES["Approver"], reason.strip())
        return rev
    local = rev["approval_state"]
    namespace = f"{reference}/r{rev['number']}"
    sync_context(local, namespace, snap["original"],
                 snap["selected"] if snap["choice"] == "Fixed copy" else None,
                 snap["rules"], snap["protected"], snap["privacy_reviewed"])
    approve(local, namespace, snap["selected"], snap["choice"], len(snap["remaining"]))
    rev["ticket"] = generate_ticket(local, namespace, snap["original"], snap["selected"], snap["choice"], snap["changes"])
    rev["status"] = "Approved"
    event(rev, "Request approved; demo ticket generated", IDENTITIES["Approver"])
    return rev


def record_delivery_step(state, reference, number, implement=False):
    """Record a download request or an explicit simulated implementation.

    A browser download event is not evidence of file receipt or a production write.
    Revalidate inside the stored-request transaction to reject concurrent revisions.
    """
    record = requests(state).get(reference)
    if record and record.get("_db_version") and not state.get("_db_transaction"):
        from persistent_demo import transaction
        return transaction(state, reference, lambda local: record_delivery_step(local, reference, number, implement))
    approved_download(state, reference, number)
    rev = current(state, reference)
    digest = valid_snapshot(rev)["selected_digest"]
    if implement:
        if rev.get("download_requested", {}).get("digest") != digest:
            raise WorkflowError("Request the approved file download before confirming implementation.")
        if rev.get("implementation"):
            return rev
        rev["implementation"] = {"digest": digest, "by": state["demo_user"], "at": timestamp(), "simulated": True}
        rev["status"] = "Simulated"
        event(rev, "Implemented on production (simulated)", state["demo_user"])
    elif not rev.get("download_requested"):
        rev["download_requested"] = {"digest": digest, "by": state["demo_user"], "at": timestamp()}
        event(rev, "Approved file download requested", state["demo_user"])
    return rev


def advance(state, reference, stage):
    if requests(state)[reference].get("_db_version") and not state.get("_db_transaction"):
        from persistent_demo import transaction
        return transaction(state, reference, lambda local: advance(local, reference, stage))
    stages = {
        "ticket": ("Approver", "Approved", "Ticket approved"),
        "cab": ("Approver", "Ticket approved", "CAB approved"),
        "simulate": ("Approver", "CAB approved", "Simulated"),
    }
    role, before, after = stages[stage]
    require_role(state, role)
    rev = current(state, reference)
    snap = valid_snapshot(rev)
    ticket = rev.get("ticket")
    if not ticket or ticket["outdated"] or ticket["digest"] != snap["selected_digest"]:
        raise WorkflowError("A current approved demo ticket is required.")
    namespace = f"{reference}/r{rev['number']}"
    from review_approval import is_approved
    if not is_approved(rev["approval_state"], namespace, snap["selected"], snap["choice"]):
        raise WorkflowError("A current approved demo ticket is required.")
    if rev["status"] == after:
        return rev  # Idempotent duplicate action.
    if rev["status"] != before:
        raise WorkflowError("Complete the preceding approval step first.")
    rev["status"] = after
    event(rev, after, IDENTITIES[role])
    return rev


def revise(state, reference):
    if requests(state)[reference].get("_db_version") and not state.get("_db_transaction"):
        from persistent_demo import transaction
        return transaction(state, reference, lambda local: revise(local, reference))
    require_role(state, "Submitter")
    old = current(state, reference)
    if old["status"] == "Draft":
        return old
    snap = valid_snapshot(old)
    revision = {"number": old["number"] + 1, "status": "Draft", "submitted_at": None,
                "rejected_by": "", "rejection_reason": "", "timeline": [], "snapshot": None,
                "approval_state": {}, "working": deepcopy(snap)}
    revision["working"].pop("seal", None)
    if old.get("row_rejections"):
        revision["row_rejections"] = deepcopy(old["row_rejections"])
    if "variant" in old:
        revision["variant"] = old["variant"]
    event(revision, "New draft revision", state["demo_user"])
    requests(state)[reference]["revisions"].append(revision)
    state["active_request_ref"] = reference
    return revision


def open_draft(state, reference):
    """Callback before widgets render: restore isolated working data and settings."""
    require_role(state, "Submitter")
    rev = current(state, reference)
    if rev["status"] != "Draft":
        raise WorkflowError("This version is frozen. Create a new draft revision to change it.")
    working = rev.get("working")
    state["active_request_ref"] = reference
    state["workspace_page"] = "inspection"
    state["request_view"] = None
    if working:
        file = working["file"]
        state["inspector_datasets"] = {file: working["original"]}
        state["active_dataset"] = file
        state["request_bindings"] = {file: {"data": working["original"], "reference": reference}}
        state["fixed_datasets"] = {file: working["selected"]} if working["choice"] == "Fixed copy" else {}
        state["fix_change_indexes"] = {file: {
            "original": frame_digest(working["original"]), "fixed": frame_digest(working["selected"]),
            "changes": working["changes"],
        }} if working["choice"] == "Fixed copy" else {}
        state["request_restore_rules"] = working["rules"]
        state["request_restore_rule_selections"] = deepcopy(working.get("rule_selections"))
        state["request_restore_fixed_rules"] = (
            {"reference": reference, "rules": deepcopy(working["rules"])}
            if working["choice"] == "Fixed copy" else None
        )
        state["request_restore_protected"] = working["protected"]
        state["request_restore_reviewed"] = working["privacy_reviewed"]
        for key in ("quality_scan_cache", "review_scan_cache", "privacy_detection_cache",
                    "fixed_export_cache", "data_insights_cache", "final_approvals"):
            state[key] = {}
    else:
        reset_uploader(state)
        state["inspector_datasets"] = {}
        state["fixed_datasets"] = {}
        state["request_bindings"] = {}


def start_new(state):
    reference = new_request(state)
    # The uploader's current files must not be re-imported into a new request.
    reset_uploader(state)
    state["inspector_datasets"] = {}
    state["fixed_datasets"] = {}
    state["request_bindings"] = {}
    state["workspace_page"] = "inspection"
    state["request_view"] = None
    return reference


def upload_widget_key(state):
    return f"data_upload_{state.get('request_upload_epoch', 0)}"


def demo_review_action(state, reference, number, action, reason=""):
    """Explicit simulation from the signed-in user's own request, not real authorization."""
    require_role(state, "Submitter")
    record = requests(state)[reference]
    if not owns(state, record) or current(state, reference)["number"] != number:
        raise WorkflowError("This request changed. Reopen it before confirming.")
    simulated = {"demo_user": state["demo_user"], "demo_role": "Approver", "demo_requests": requests(state),
                 "demo_catalog": state.get("demo_catalog")}
    simulated.update(auth_state(state))
    if action in ("approve", "reject"):
        return owner_decision(simulated, reference, action == "approve", reason)
    return advance(simulated, reference, action)


def reset_uploader(state):
    """Reset both server import tracking and the browser's file selection."""
    state.pop(upload_widget_key(state), None)
    state.pop("data_upload", None)  # Retire the pre-epoch widget on existing sessions.
    state["request_upload_epoch"] = state.get("request_upload_epoch", 0) + 1
    state.pop("inspector_upload_signature", None)
