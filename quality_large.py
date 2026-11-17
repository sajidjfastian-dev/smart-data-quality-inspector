"""Chunked quality checks for large in-memory dataframes.

All checks cover the whole dataset; chunks bound temporary masks and make
progress visible without changing cross-chunk duplicate or outlier semantics.
"""
from collections import Counter
from functools import lru_cache

import numpy as np
import pandas as pd


def scan_large_data(data, email_columns, date_columns, numeric_columns,
                    iqr_multiplier, progress_callback, enabled_checks, custom_rules,
                    email_pattern, parse_date, date_shape, parse_numeric_series,
                    display_value, issue_columns):
    rows = len(data)
    chunk_size = 100_000
    chunks = max((rows + chunk_size - 1) // chunk_size, 1)
    passes = (
        (len(data.columns) if "missing" in enabled_checks else 0)
        + (len(email_columns) if "email" in enabled_checks else 0)
        + (2 * len(date_columns) if "date" in enabled_checks else 0)
        + (len(numeric_columns) if "outliers" in enabled_checks else 0)
        + len(custom_rules)
    )
    total_steps = max(1, passes * chunks + 1)
    steps_done = 0
    frames = []

    def report(label):
        nonlocal steps_done
        steps_done += 1
        if progress_callback:
            progress_callback(min(steps_done / total_steps, .99), label)

    def slices():
        for start in range(0, rows, chunk_size):
            yield start, min(start + chunk_size, rows)

    def missing_mask(series):
        missing = series.isna()
        if not pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            missing = missing | series.astype("string").str.strip().eq("").fillna(False)
        return missing.to_numpy(dtype=bool)

    def add_mask(start, series, mask, column, issue_type, suggestion):
        positions = np.flatnonzero(np.asarray(mask, dtype=bool))
        if not len(positions):
            return
        values = series.iloc[positions].map(display_value).to_numpy()
        frames.append(pd.DataFrame({
            "Row Number": positions + start + 1,
            "Column Name": column,
            "Issue Type": issue_type,
            "Current Value": values,
            "Suggested Fix": suggestion,
        }))

    if progress_callback:
        progress_callback(0.0, "Identifying duplicate rows across the full file")
    duplicate_mask = data.duplicated(keep="first").to_numpy() if "duplicates" in enabled_checks else np.zeros(rows, dtype=bool)
    report("Duplicate-row check complete")
    cached_parse_date = lru_cache(maxsize=65_536)(parse_date)
    cached_date_shape = lru_cache(maxsize=65_536)(date_shape)

    for column in data.columns:
        series = data[column]
        if "missing" in enabled_checks:
            for start, end in slices():
                part = series.iloc[start:end]
                add_mask(start, part, missing_mask(part), column, "Missing Value",
                         "Provide a value or fill using an appropriate default.")
                report(f"Checking missing values · {column} · rows {end:,} of {rows:,}")

        if "email" in enabled_checks and column in email_columns:
            for start, end in slices():
                part = series.iloc[start:end]
                valid = part.astype("string").str.strip().str.fullmatch(email_pattern, na=False).to_numpy(dtype=bool)
                add_mask(start, part, ~missing_mask(part) & ~valid, column, "Invalid Email",
                         "Correct the address to a valid name@domain format.")
                report(f"Validating email formats · {column} · rows {end:,} of {rows:,}")

        if "date" in enabled_checks and column in date_columns:
            shape_counts = Counter()
            for start, end in slices():
                for value in series.iloc[start:end]:
                    if isinstance(value, str) and value.strip() and cached_parse_date(value):
                        shape_counts[cached_date_shape(value)] += 1
                report(f"Learning date formats · {column} · rows {end:,} of {rows:,}")
            common_shape = shape_counts.most_common(1)[0][0] if shape_counts else None
            for start, end in slices():
                part = series.iloc[start:end]
                # Preserve the original ordering when invalid and inconsistent
                # dates appear in the same chunk.
                date_issues = []
                for offset, value in enumerate(part):
                    if missing_mask_value(value):
                        continue
                    if not cached_parse_date(value):
                        date_issues.append((offset, "Invalid Date", "Replace with a valid date, such as YYYY-MM-DD."))
                    elif isinstance(value, str) and value.strip() and common_shape is not None and cached_date_shape(value) != common_shape:
                        date_issues.append((offset, "Inconsistent Date Format", f"Standardize to the most common format ({common_shape})."))
                if date_issues:
                    positions, kinds, suggestions = zip(*date_issues)
                    frames.append(pd.DataFrame({
                        "Row Number": np.asarray(positions) + start + 1,
                        "Column Name": column,
                        "Issue Type": kinds,
                        "Current Value": part.iloc[list(positions)].map(display_value).to_numpy(),
                        "Suggested Fix": suggestions,
                    }))
                report(f"Validating date formats · {column} · rows {end:,} of {rows:,}")

        if "outliers" in enabled_checks and column in numeric_columns:
            numeric = parse_numeric_series(series)
            finite = np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))
            valid = numeric[finite].dropna()
            if valid.empty:
                lower = upper = None
            else:
                first, third = valid.quantile(.25), valid.quantile(.75)
                lower = first - iqr_multiplier * (third - first)
                upper = third + iqr_multiplier * (third - first)
            for start, end in slices():
                part = series.iloc[start:end]
                values = numeric.iloc[start:end].to_numpy(dtype=float, na_value=np.nan)
                mask = np.isfinite(values) & ((values < lower) | (values > upper)) if lower is not None else np.zeros(len(part), dtype=bool)
                add_mask(start, part, mask, column, "Numeric Outlier",
                         "Review this value; confirm it or replace with a validated value.")
                report(f"Checking numeric outliers · {column} · rows {end:,} of {rows:,}")

    for rule in custom_rules:
        column, kind, expected = rule["column"], rule["kind"], rule["expected"]
        if column not in data.columns:
            continue
        allowed = {value.strip() for value in expected.split(",") if value.strip()}
        for start, end in slices():
            part = data[column].iloc[start:end]
            text = part.astype("string").str.strip()
            if kind == "Must contain":
                valid = text.str.casefold().str.contains(expected.casefold(), regex=False, na=False)
                suggestion = f"Include the text: {expected}"
            elif kind == "Allowed values":
                valid = text.isin(allowed)
                suggestion = f"Use one of: {expected}"
            else:
                numeric = pd.to_numeric(text, errors="coerce")
                valid = numeric.notna() & np.isfinite(numeric.astype(float))
                valid = valid & (numeric >= float(expected) if kind == "Minimum number" else numeric <= float(expected))
                suggestion = f"Use a number {'at least' if kind == 'Minimum number' else 'at most'} {expected}."
            add_mask(start, part, ~missing_mask(part) & ~valid.to_numpy(dtype=bool, na_value=False),
                     column, f"Custom: {kind}", suggestion)
            report(f"Checking custom rule · {column} · rows {end:,} of {rows:,}")

    positions = np.flatnonzero(duplicate_mask)
    if len(positions):
        frames.append(pd.DataFrame({
            "Row Number": positions + 1,
            "Column Name": "Entire row",
            "Issue Type": "Duplicate Row",
            "Current Value": "Exact match to an earlier row",
            "Suggested Fix": "Remove the duplicate row and keep the first occurrence.",
        }))
    if progress_callback:
        progress_callback(1.0, "Finalizing the inspection report")
    return (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=issue_columns),
            int(duplicate_mask.sum()))


def missing_mask_value(value):
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
