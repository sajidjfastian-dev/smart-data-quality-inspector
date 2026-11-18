"""Correction lineage and a masked, rule-aware resolution workspace."""
import numpy as np
import pandas as pd
import hashlib
from decimal import Decimal, InvalidOperation
from review_approval import frame_digest, invalidate
from localization import native as st


def retained_rows(original, record):
    removed = set()
    if record is not None:
        changes = record["changes"]
        removed = set(changes.loc[changes["Column position"].isna(), "Original row"].astype(int) - 1)
    return [position for position in range(len(original)) if position not in removed]


def build_changes(original, corrected, row_map, previous=None, reasons=None):
    """Describe net changes using original row positions, including repeated edits."""
    reasons = reasons or {}
    prior = {}
    if previous is not None:
        for old_row, _, col, reason in previous.itertuples(index=False, name=None):
            if pd.notna(col):
                prior[(int(old_row)-1, int(col))] = reason
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
    rows.extend((pos+1, None, None, "Removed duplicate row")
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
    """Edit one or many finding cells, without ever displaying protected values."""
    from issue_workspace import render_findings
    st.subheader("2 · Resolve remaining findings")
    st.caption("Use a verified source value, not a guess. Every saved correction is rechecked against your active rules.")
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
    cells = findings[findings["Column Name"].isin(current.columns)]
    with st.expander("Correct a value or a group of findings", expanded=True):
        mode = st.radio("Choose correction", ["Resolve findings", "Edit any cell"],
                        index=1 if cells.empty else 0, horizontal=True, key=key+"_mode")
        if mode == "Resolve findings" and cells.empty:
            st.info("No cell findings remain. Choose Edit any cell to adjust a previously corrected value.")
        else:
            options = list(current.columns) if mode == "Edit any cell" else list(cells["Column Name"].unique())
            column = st.selectbox("Column to correct", options, key=key+"_col_"+mode)
            if mode == "Edit any cell":
                kind = "Verified source value"
                chosen = [int(st.number_input("Row to correct", min_value=1, max_value=len(current),
                                              step=1, key=key+"_single_row"))]
            else:
                kinds = list(cells.loc[cells["Column Name"] == column, "Issue Type"].unique())
                kind = st.selectbox("Finding to resolve", kinds, key=key+"_kind")
                selected = cells[(cells["Column Name"] == column) & (cells["Issue Type"] == kind)]
                positions = sorted(set(selected["Row Number"].astype(int)))
                st.caption(f"{len(positions):,} affected rows. The replacement is applied only to the rows you select.")
                scope = st.radio("Correction scope", ["Choose rows", "All matching rows"], horizontal=True, key=key+"_scope")
                chosen = positions if scope == "All matching rows" else st.multiselect(
                    "Rows to correct", positions, key=key+"_rows_"+str(column)+"_"+str(kind))
            form_version = hashlib.sha256(
                repr((frame_digest(current), column, kind, chosen)).encode()
            ).hexdigest()[:16]
            with st.form(key+"_manual_form_"+form_version):
                replacement = st.text_input("Verified replacement value",
                                            type="password" if column in protected else "default")
                confirmed = st.checkbox("I verified this value and the selected rows")
                apply = st.form_submit_button("Save correction and recheck", disabled=not chosen)
            if apply:
                if not confirmed or not replacement.strip():
                    st.error("Enter a verified, non-empty value and confirm the selected rows.")
                else:
                    candidate = current.copy()
                    col = current.columns.get_loc(column)
                    try:
                        value = replacement
                        if pd.api.types.is_numeric_dtype(current[column]) and not pd.api.types.is_bool_dtype(current[column]):
                            number = Decimal(replacement)
                            if not number.is_finite():
                                raise ValueError
                            value = int(number) if number == number.to_integral_value() else float(number)
                            if not np.isfinite(float(value)):
                                raise ValueError
                            candidate[column] = candidate[column].astype(object)
                        elif pd.api.types.is_bool_dtype(current[column]):
                            if replacement.casefold() not in ("true", "false"):
                                raise ValueError
                            value = replacement.casefold() == "true"
                        else:
                            candidate[column] = candidate[column].astype(object)
                        candidate.iloc[[p-1 for p in chosen], col] = value
                        remaining, _ = scan(candidate)
                        invalid = remaining[
                            remaining["Row Number"].isin(chosen)
                            & (remaining["Column Name"] == column)
                            & (remaining["Issue Type"] != "Numeric Outlier")
                        ]
                        if not invalid.empty:
                            st.error("This value still fails an active rule for these cells. Check the expected format or allowed values.")
                        else:
                            reasons = {(p-1, col): "Manual correction · " + kind for p in chosen}
                            changes = build_changes(original, candidate, retained_rows(original, record),
                                                    record["changes"] if record else None, reasons)
                            save_copy(state, dataset, original, candidate, changes)
                            state[key+"_notice"] = f"Saved {len(chosen):,} cell correction(s); {len(remaining):,} findings remain."
                            st.rerun()
                    except (ValueError, TypeError, OverflowError, InvalidOperation):
                        st.error("Enter a valid value for this column's data type.")
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
            "**Missing values:** use the source system or an agreed business default; numeric medians are estimates.\n\n"
            "**Emails and dates:** obtain the correct source value; do not invent an address or guess ambiguous dates.\n\n"
            "**Allowed values:** choose the exact approved category. Case-only differences can be normalized automatically.\n\n"
            "**Numeric limits and outliers:** verify the amount against its source. A valid outlier may remain for reviewer assessment.\n\n"
            "**Must contain:** verify the full value rather than appending text just to pass a check.\n\n"
            "Use the **AI assistant** tab for questions about the remaining findings. Advice never changes your data automatically."
        )
