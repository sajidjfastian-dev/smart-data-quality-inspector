"""Grounded summaries and optional-control suggestions for the current dataset."""

import pandas as pd


def dataset_facts(data, profile, numeric_columns, date_columns, protected):
    """Return full-file structural facts without exposing protected values."""
    protected_names = {str(column) for column in protected}
    public = [str(column) for column in data.columns if str(column) not in protected_names]
    total = len(data) * len(data.columns)
    missing = int(profile["Missing"].sum()) if len(profile) else 0
    numeric = [str(column) for column in numeric_columns if str(column) in public]
    dates = [str(column) for column in date_columns if str(column) in public]
    return {
        "rows": len(data), "columns": len(data.columns),
        "missing_cells": missing, "cells": total,
        "visible_fields": public, "numeric_fields": numeric, "date_fields": dates,
        "protected_fields": len(data.columns) - len(public),
    }


def quality_suggestions(data, enabled, email_columns, date_columns, numeric_columns):
    """Suggest only checks that can be configured for this file; never promise fixes."""
    if data.empty or not len(data.columns):
        return []
    suggestions = []
    if "missing" not in enabled:
        suggestions.append("Enable Missing values to identify empty cells; numeric gaps may be eligible for a reviewed median fill.")
    if "duplicates" not in enabled:
        suggestions.append("Enable Duplicate rows to find exact duplicates that can be removed after review.")
    if email_columns and "email" not in enabled:
        suggestions.append("Enable Invalid email formats for selected email columns; addresses require source verification.")
    if date_columns and "date" not in enabled:
        suggestions.append("Enable Invalid and inconsistent dates; unambiguous valid dates can be standardized.")
    if numeric_columns and "outliers" not in enabled:
        suggestions.append("Enable Numeric outliers to flag unusual values for review, not automatic changes.")
    if not email_columns and any("email" in str(c).lower() or "e_mail" in str(c).lower() for c in data.columns):
        suggestions.append("Select the email column in Inspection checks to assess email formats.")
    if not date_columns and any("date" in str(c).lower() for c in data.columns):
        suggestions.append("Select the date column in Inspection checks to assess date formats.")
    return suggestions


def masked_sample(data, protected, limit=25):
    """An evenly spaced sample; values in protected columns are never sent."""
    from security_guardrails import mask_dataframe
    if len(data) > limit:
        indices = [i * (len(data) - 1) // (limit - 1) for i in range(limit)]
        data = data.iloc[indices]
    return mask_dataframe(data, protected).reset_index(drop=True)
