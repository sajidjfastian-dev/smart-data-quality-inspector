"""Private session evidence: never copied into shared request records."""
from hashlib import sha256
from io import BytesIO
from pathlib import PurePath
import re
from datetime import datetime
from PIL import Image
from request_workflow import valid_snapshot, WorkflowError, timestamp, demo_review_action

MAX_FILE = 5 * 1024 * 1024
MAX_SESSION = 20 * 1024 * 1024


def validate_file(name, data):
    if not data or len(data) > MAX_FILE:
        raise WorkflowError("Evidence must be nonempty and at most 5 MB.")
    ext = PurePath(name).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".txt"):
        raise WorkflowError("Use PNG, JPEG or plain-text evidence.")
    if ext == ".txt":
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise WorkflowError("Text evidence must be UTF-8.") from None
        if "\x00" in text:
            raise WorkflowError("Text evidence contains invalid control characters.")
    else:
        try:
            with Image.open(BytesIO(data)) as image:
                if image.format != ("PNG" if ext == ".png" else "JPEG") or image.width * image.height > 20_000_000:
                    raise ValueError()
                image.verify()
        except Exception:
            raise WorkflowError("Evidence must be a valid PNG or JPEG image under 20 megapixels.") from None
    name = re.sub(r"[\x00-\x1f\x7f]", "", name.replace("\\", "/").split("/")[-1])[:160]
    return {"name": name, "data": data,
            "size": len(data), "sha256": sha256(data).hexdigest()}


def binding(state, reference, number):
    record = state.get("demo_requests", {}).get(reference)
    from account_identity import owns
    from request_workflow import require_role
    require_role(state, "Submitter")
    if not state.get("demo_user") or not owns(state, record):
        raise WorkflowError("Request not found in this session.")
    if number < 1 or number > len(record["revisions"]):
        raise WorkflowError("Revision not found.")
    revision = record["revisions"][number - 1]
    return valid_snapshot(revision)["seal"]


def approve_with_evidence(state, reference, number, action, evidence=None, expected_seal=None):
    seal = binding(state, reference, number)
    if expected_seal is not None and seal != expected_seal:
        raise WorkflowError("The submitted snapshot changed. Reopen approval.")
    if action not in ("ticket", "cab"):
        raise WorkflowError("Evidence is supported for ticket and CAB approvals.")
    key = (reference, number, action, seal)
    if evidence:
        evidence = validate_file(evidence["name"], evidence["data"])
        used = sum(x["file"]["size"] for k, x in state.get("private_approval_evidence", {}).items()
                   if x["file"] and k != (reference, number, action, seal))
        if used + evidence["size"] > MAX_SESSION:
            raise WorkflowError("Session evidence limit is 20 MB. Start a new session to clear evidence.")
    existing = state.get("private_approval_evidence", {}).get(key)
    if existing and existing["file"] != evidence:
        raise WorkflowError("Recorded approval evidence cannot be replaced. Create a new revision.")
    demo_review_action(state, reference, number, action)
    records = state.setdefault("private_approval_evidence", {})
    # Approval and attachment are recorded together only after the action succeeds.
    if key not in records:
        records[key] = {"reference": reference, "revision": number, "stage": action,
                        "seal": seal, "actor": state["demo_user"], "approved_by": "Demo Approver",
                        "timestamp": timestamp(), "file": evidence}


def render_evidence(state, reference, number, translate, st):
    seal = binding(state, reference, number)
    entries = [v for k, v in state.get("private_approval_evidence", {}).items()
               if k[0] == reference and k[1] == number and k[3] == seal]
    if not entries:
        return
    with st.expander(translate("Private approval evidence")):
        st.caption(translate("Session-only: cleared on logout or session loss. Not a permanent audit archive."))
        for entry in entries:
            when = datetime.fromisoformat(entry["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
            st.write(f'{entry["stage"].upper()} · {entry["approved_by"]} · {when} (Asia/Dubai)')
            st.caption(translate("Initiated by") + f': {entry["actor"]} · ' + translate("Revision") + f" {number}")
            file = entry["file"]
            if file:
                st.text(file["name"])
                st.text("SHA-256: " + file["sha256"])
                st.download_button(translate("Download evidence"), file["data"],
                                   file_name=file["name"], mime="application/octet-stream",
                                   key=f'evidence_download_{reference}_{number}_{entry["stage"]}')
            else:
                st.caption(translate("No evidence attached."))
