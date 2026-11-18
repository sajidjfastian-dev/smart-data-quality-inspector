"""Correction lineage and a masked, rule-aware resolution workspace."""
import numpy as np
import pandas as pd
from review_approval import frame_digest, invalidate
from localization import native as st


def retained_rows(original, record):
    removed = set()
    if record is not None:
        changes = record["changes"]
        removed = set(changes.loc[changes["Column position"].isna(), "Original row"].astype(int) - 1)
    return [position for position in range(len(original)) if position not in removed]


def build_changes(original, corrected, row_map, previous=None, reasons=None, removed_reasons=None):
    """Describe net changes using original row positions, including repeated edits."""
    reasons = reasons or {}
    prior = {}
    prior_removed = {}
    if previous is not None:
        for old_row, _, col, reason in previous.itertuples(index=False, name=None):
            if pd.notna(col):
                prior[(int(old_row)-1, int(col))] = reason
            else:
                prior_removed[int(old_row)-1] = reason
    rows = []
    for col in range(len(original.columns)):
        before = original.iloc[row_map, col].reset_index(drop=True)
        after = corrected.iloc[:, col].reset_index(drop=True)
        same = before.eq(after).fillna(False) | (before.isna() & after.isna())
        for pos in np.flatnonzero(~same.to_numpy(dtype=bool)):
            origin = row_map[pos]
            reason = reasons.get((pos, col), prior.get((origin, col), "Manual correction"))
            rows.append((origin+1, pos+1, col, reason))
    kept = set(row_map)
    removed_reasons = removed_reasons or {}
    rows.extend((pos+1, None, None, removed_reasons.get(pos, prior_removed.get(pos, "Removed duplicate row")))
                for pos in range(len(original)) if pos not in kept)
    return pd.DataFrame(rows, columns=["Original row", "Corrected row", "Column position", "Change reason"])


def canonical_allowed_values(frame, rules):
    """Only unambiguous case/space normalization; never invent a domain value."""
    result = frame.copy()
    reasons = {}
    for column in frame.columns:
        relevant = [r for r in rules if r["column"] == column and r["kind"] == "Allowed values"]
        if not relevant:
            continue
        allowed_sets = [{v.strip() for v in r["expected"].split(",") if v.strip()} for r in relevant]
        allowed = set.intersection(*allowed_sets)
        col = frame.columns.get_loc(column)
        for pos, value in enumerate(frame[column]):
            if not isinstance(value, str) or value in allowed:
                continue
            matches = [v for v in allowed if v.casefold() == value.strip().casefold()]
            if len(matches) == 1:
                result.iloc[pos, col] = matches[0]
                reasons[(pos, col)] = "Normalized to allowed value"
    return result, reasons


def save_copy(state, dataset, original, corrected, changes):
    state.setdefault("fixed_datasets", {})[dataset] = corrected
    state.setdefault("fix_change_indexes", {})[dataset] = {
        "original": frame_digest(original), "fixed": frame_digest(corrected), "changes": changes,
    }
    invalidate(state, dataset)
    for cache in ("fixed_export_cache", "review_scan_cache"):
        state.setdefault(cache, {}).pop(dataset, None)


def render_resolution(state, dataset, original, current, findings, protected, scan, key):
    """Explain unresolved findings without accepting manually entered corrections."""
    from issue_workspace import render_findings
    st.subheader("2 · Review automatic results")
    st.caption("Applicable corrections are applied by the system. Remaining findings require source verification; no values are guessed.")
    counts = st.columns(3)
    counts[0].metric("Original rows", f"{len(original):,}")
    counts[1].metric("Current rows", f"{len(current):,}")
    counts[2].metric("Remaining findings", f"{len(findings):,}")
    if findings.empty:
        st.success("No findings remain under the enabled quality controls.")
    else:
        with st.expander("Findings and recommended actions", expanded=False):
            render_findings(findings, protected, "resolve_" + key, current, downloads=False)
    if current.empty:
        return
    record = state.get("fix_change_indexes", {}).get(dataset)
    if record and (record["original"] != frame_digest(original) or record["fixed"] != frame_digest(current)):
        st.error("The correction history no longer matches this file. Restore the original before continuing.")
        return
    if (findings["Issue Type"] == "Duplicate Row").any():
        if st.button("Remove remaining exact duplicate rows", key=key+"_dedup"):
            keep = ~current.duplicated().to_numpy()
            row_map = [r for r, retained in zip(retained_rows(original, record), keep) if retained]
            candidate = current.iloc[np.flatnonzero(keep)].reset_index(drop=True)
            changes = build_changes(original, candidate, row_map, record["changes"] if record else None)
            save_copy(state, dataset, original, candidate, changes)
            st.rerun()
    with st.expander("Assistance for unresolved findings"):
        st.markdown(
            "**Automatically correctable:** exact duplicates, surrounding whitespace, selected numeric gaps using the median, "
            "unambiguous valid dates, and unique case/spacing matches to allowed values.\n\n"
            "**Source verification needed:** invalid numbers and emails, ambiguous dates, missing text, numeric limits and outliers. "
            "Correct these in the source system and upload a new file, or disclose them to the reviewer.\n\n"
            "The **AI assistant** can explain remaining findings. It cannot invent missing facts or bypass review."
        )
