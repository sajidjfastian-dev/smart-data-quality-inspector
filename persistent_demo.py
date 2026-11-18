"""Trusted synthetic-only boundary around the existing session workflow.

Only server-fetched frames can be enrolled. Writes reconstruct payloads from the
database-owned catalog; arbitrary upload values, filenames, rules and notes are
never serialized into shared storage.
"""
from copy import deepcopy

import demo_store
from public_sample import SOURCE_ID, LABEL
from review_approval import frame_digest
from demo_codec import encode

REASONS = ("Validate remaining findings", "Check source quality", "Review proposed corrections")


def initialize(state):
    if not state.get("demo_user"):
        return
    if not state.get("demo_session_id"):
        state["demo_session_id"] = demo_store.create_session()
    state["demo_catalog"] = demo_store.load_catalog(SOURCE_ID)
    shared = demo_store.list_requests()
    local = state.setdefault("demo_requests", {})
    # Never overwrite a cached draft silently: CAS checks detect conflicting edits.
    for reference, record in shared.items():
        if reference not in local:
            local[reference] = record
    state["_persistent_demo_ready"] = True


def refresh(state):
    shared = demo_store.list_requests()
    local = state.setdefault("demo_requests", {})
    local.update(shared)


def register_source(state, frame):
    """Called only after the fixed sample endpoint, never generic uploads/imports."""
    state.setdefault("_synthetic_origins", []).append(frame)


def eligible(state, record, payload):
    if record.get("_private"):
        return False
    return record.get("_db_version") is not None or any(
        frame is payload["original"] for frame in state.get("_synthetic_origins", [])
    )


def canonical_payload(state, payload, source_id=None):
    from request_workflow import WorkflowError
    catalog = state["demo_catalog"] if source_id is None or source_id == SOURCE_ID else demo_store.load_catalog(source_id)
    variants = catalog["variants"]
    base = variants["original"]
    rules = payload["rules"]
    expected = base["rules"]
    rules_match = (
        not rules.get("custom") and rules.get("iqr") == expected["iqr"] and
        all(sorted(rules.get(key, [])) == sorted(expected[key]) for key in ("email","date","numeric","enabled"))
    )
    if not rules_match or frame_digest(payload["original"]) != frame_digest(base["original"]):
        raise WorkflowError("Shared examples use the standard sample checks. Continue as a private request to use custom data or rules.")
    variant = next((key for key, value in variants.items()
                    if value["choice"] == payload["choice"]
                    and frame_digest(value["selected"]) == frame_digest(payload["selected"])), None)
    if variant is None:
        raise WorkflowError("Only the sample's supported safe fixes can be saved to the shared demo.")
    if not set(payload["protected"]) <= set(base["original"].columns):
        raise WorkflowError("Invalid sample privacy settings.")
    result = deepcopy(variants[variant])
    result["protected"] = set(payload["protected"])
    result["privacy_reviewed"] = bool(payload["privacy_reviewed"])
    return variant, result


def save_working(state, reference, payload):
    """Return True if handled; no writes for private source data."""
    from request_workflow import WorkflowError
    record = state["demo_requests"][reference]
    if not state.get("_persistent_demo_ready") or not eligible(state, record, payload):
        return False
    try:
        variant, trusted = canonical_payload(state, payload, record.get("source_id"))
        revision = record["revisions"][-1]
        if record.get("_db_version") and revision.get("variant") == variant and encode(revision.get("working")) == encode(trusted):
            return True
        candidate = deepcopy(record)
        candidate["revisions"][-1]["working"] = trusted
        candidate["revisions"][-1]["variant"] = variant
        if record.get("_db_version"):
            demo_store.update_request(candidate, record["_db_version"])
        else:
            # A new local draft has only generated metadata; never persist its filename.
            candidate.update(file=LABEL, source_id=SOURCE_ID, synthetic=True,
                             session_id=state["demo_session_id"])
            candidate["submitted_by"] = "Sajid"
            demo_store.insert_request(candidate)
        state["demo_requests"][reference] = candidate
        return True
    except demo_store.DemoStoreError as error:
        raise WorkflowError(str(error)) from None


def transaction(state, reference, operation):
    from request_workflow import WorkflowError
    record = state["demo_requests"][reference]
    # Revalidate a draft before freezing it, even if another widget has mutated
    # a restored in-session object. Raw text can never reach the write below.
    candidate_record = deepcopy(record)
    for revision in candidate_record["revisions"]:
        if revision.get("working"):
            variant, trusted = canonical_payload(state, revision["working"], record.get("source_id"))
            revision["working"] = trusted
            revision["variant"] = variant
    local = {"demo_user": state["demo_user"], "demo_role": state.get("demo_role","Submitter"),
             "demo_requests": {reference: candidate_record}, "_db_transaction": True}
    try:
        result = operation(local)
        candidate = local["demo_requests"][reference]
        demo_store.update_request(candidate, record["_db_version"])
        state["demo_requests"][reference] = candidate
        return result
    except demo_store.DemoStoreError as error:
        raise WorkflowError(str(error)) from None


def make_private(state, reference, payload=None):
    from request_workflow import new_request, open_draft
    prior = state["demo_requests"][reference]
    working = payload or prior["revisions"][-1].get("working")
    new = new_request(state)
    record = state["demo_requests"][new]
    record["_private"] = True
    record["file"] = prior["file"]
    record["revisions"][-1]["working"] = deepcopy(working)
    open_draft(state, new)
