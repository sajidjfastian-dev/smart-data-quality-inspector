"""Session-only demo review versions, row lineage and guarded destination sends.

No identity assurance or persistence is provided by this module.
"""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd


class ApprovalRequired(ValueError):
    pass


def frame_digest(frame):
    digest = hashlib.sha256()
    digest.update(repr((tuple(frame.columns), tuple(map(str, frame.dtypes)))).encode())
    try:
        digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())
    except TypeError:
        digest.update(frame.to_json(orient="split", date_format="iso").encode())
    return digest.hexdigest()


def invalidate(state, dataset):
    """Explicit reapplication invalidates even byte-identical fixes."""
    state.setdefault("review_generations", {})[dataset] = uuid4().hex
    state.setdefault("final_approvals", {}).pop(dataset, None)
    mark_ticket_outdated(state, dataset)


def mark_ticket_outdated(state, dataset):
    ticket = state.get("demo_change_tickets", {}).get(dataset)
    if ticket:
        ticket["outdated"] = True


def sync_context(state, dataset, original, fixed, rules, protected, privacy_reviewed):
    generations = state.setdefault("review_generations", {})
    generation = generations.setdefault(dataset, uuid4().hex)
    context = {
        "original": frame_digest(original),
        "fixed": frame_digest(fixed) if fixed is not None else None,
        "rules": repr(rules),
        "protected": sorted(map(str, protected)),
        "privacy_reviewed": bool(privacy_reviewed),
        "generation": generation,
    }
    context["version"] = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    previous = state.setdefault("review_contexts", {}).get(dataset)
    if previous != context:
        state.setdefault("final_approvals", {}).pop(dataset, None)
        mark_ticket_outdated(state, dataset)
    state["review_contexts"][dataset] = context
    return context


def is_approved(state, dataset, frame, choice):
    context = state.get("review_contexts", {}).get(dataset)
    approval = state.get("final_approvals", {}).get(dataset)
    if not context or not approval or not context["privacy_reviewed"]:
        return False
    expected = context["fixed" if choice == "Fixed copy" else "original"]
    return (
        approval["version"] == context["version"]
        and approval["choice"] == choice
        and approval["digest"] == expected == frame_digest(frame)
        and approval["status"] == "approved"
    )


def approve(state, dataset, frame, choice, remaining):
    context = state["review_contexts"][dataset]
    expected = context["fixed" if choice == "Fixed copy" else "original"]
    if not context["privacy_reviewed"] or expected != frame_digest(frame):
        raise ApprovalRequired("The reviewed version changed. Review it again before approval.")
    record = {
        "approval_id": uuid4().hex,
        "version": context["version"], "choice": choice, "digest": expected,
        "status": "approved", "mode": "demo", "remaining_findings": int(remaining),
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    mark_ticket_outdated(state, dataset)
    state.setdefault("final_approvals", {})[dataset] = record
    return record


def return_for_revision(state, dataset):
    state.setdefault("final_approvals", {}).pop(dataset, None)
    mark_ticket_outdated(state, dataset)


def guarded_push(state, dataset, original, selected, choice, protected, privacy_reviewed,
                 destination_consent, sender, *args, **kwargs):
    """Recheck at execution, not just through a disabled button."""
    raise ApprovalRequired("Live destination writes are disabled in the demo request workflow.")


def change_index(original, corrected, drop_duplicates):
    """Keep positional lineage before cleaning resets the index.

    Cleaning removes exact duplicates FIRST, then transforms retained cells.
    Store positions only; values are fetched and masked at display time.
    """
    retained = np.flatnonzero(~original.duplicated().to_numpy()) if drop_duplicates else np.arange(len(original))
    if len(retained) != len(corrected) or not original.columns.equals(corrected.columns):
        raise ValueError("The fixed copy does not match its original row lineage.")
    changes = []
    for col_pos in range(len(original.columns)):
        before = original.iloc[retained, col_pos].reset_index(drop=True)
        after = corrected.iloc[:, col_pos].reset_index(drop=True)
        equal = before.eq(after).fillna(False) | (before.isna() & after.isna())
        for fixed_pos in np.flatnonzero(~equal.to_numpy(dtype=bool)):
            old = before.iloc[fixed_pos]
            new = after.iloc[fixed_pos]
            if isinstance(old, str) and isinstance(new, str) and old.strip() == new:
                reason = "Trimmed whitespace"
            elif pd.isna(old) or (isinstance(old, str) and not old.strip()):
                reason = "Filled missing value"
            else:
                reason = "Standardized date"
            changes.append((int(retained[fixed_pos]) + 1, int(fixed_pos) + 1, col_pos, reason))
    removed = np.setdiff1d(np.arange(len(original)), retained)
    changes.extend((int(pos) + 1, None, None, "Removed duplicate row") for pos in removed)
    return pd.DataFrame(changes, columns=["Original row", "Corrected row", "Column position", "Change reason"])
