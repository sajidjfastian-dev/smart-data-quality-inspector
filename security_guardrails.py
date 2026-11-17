"""Conservative, session-local masking of sensitive dataset values.

Detection is a safeguard, not a guarantee: reviewers must mark additional
columns containing confidential information before sharing data.
"""

import re

import pandas as pd


MASK = "••••"
_COLUMN_PATTERNS = (
    re.compile(
        r"(^|[^a-z0-9])(name|email|e_mail|phone|mobile|telephone|contact|address|"
        r"passport|identity|nationality|dob|birth|customer|client|account|acct|iban|"
        r"credit|debit|card|pan|ssn|emirates|national_id|id)([^a-z0-9]|$)"
    ),
    re.compile(
        r"(full.?name|first.?name|last.?name|customer.?name|customer.?id|"
        r"account.?number|card.?number|phone.?number|email.?address|"
        r"الاسم|اسم|البريد|الهاتف|جوال|العنوان|هوية|حساب|بطاقة|جواز)"
    ),
)
_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])", re.IGNORECASE)
_IBAN = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\s*\d{2}(?:\s*[A-Z0-9]){11,30}(?![A-Z0-9])", re.IGNORECASE)
_EMIRATES_ID = re.compile(r"(?<!\d)784[- ]?\d{4}[- ]?\d{7}[- ]?\d(?!\d)")
_LONG_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_PHONE = re.compile(r"(?<!\w)(?:\+|00)\d[\d\s().-]{7,19}\d(?!\w)")


def _sensitive_header(column):
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", str(column)).casefold()
    return any(pattern.search(name) for pattern in _COLUMN_PATTERNS)


def _contains_sensitive_value(value):
    if not isinstance(value, str):
        value = str(value)
    if len(value) < 6:
        return False
    return any(pattern.search(value) for pattern in (_EMAIL, _IBAN, _EMIRATES_ID, _LONG_NUMBER, _PHONE))


def detect_sensitive_columns(data, progress_callback=None, chunk_size=20_000):
    """Inspect column labels and all values in bounded chunks, failing closed."""
    detected = set()
    columns = list(data.columns)
    for index, column in enumerate(columns):
        if _sensitive_header(column):
            detected.add(column)
        else:
            series = data[column]
            for start in range(0, len(series), chunk_size):
                chunk = series.iloc[start:start + chunk_size].dropna()
                if chunk.map(_contains_sensitive_value).any():
                    detected.add(column)
                    break
                if progress_callback:
                    progress_callback((index + min(start + chunk_size, len(series)) / max(len(series), 1)) / max(len(columns), 1))
        if progress_callback:
            progress_callback((index + 1) / max(len(columns), 1))
    return detected


def mask_dataframe(data, sensitive_columns):
    """Return a masked copy, preserving missing cells and the original frame."""
    result = data.copy()
    for column in set(sensitive_columns).intersection(result.columns):
        series = result[column].astype(object)
        present = series.notna()
        if pd.api.types.is_string_dtype(data[column]) or data[column].dtype == object:
            present &= ~series.astype("string").str.strip().eq("").fillna(False)
        result[column] = series.mask(present, MASK)
    return result


def mask_findings(issues, sensitive_columns):
    """Mask values and potentially sensitive custom-rule suggestions."""
    result = issues.copy()
    if result.empty:
        return result
    affected = result["Column Name"].isin({str(column) for column in sensitive_columns})
    result.loc[affected, "Current Value"] = MASK
    custom = result["Issue Type"].astype(str).str.startswith("Custom:")
    result.loc[affected & custom, "Suggested Fix"] = "Review the configured rule."
    for column in ("Current Value", "Suggested Fix"):
        result[column] = result[column].map(mask_text)
    return result


def mask_text(text):
    """Mask recognizable identifiers in free text; unknown names need review."""
    result = str(text)
    for pattern in (_EMAIL, _IBAN, _EMIRATES_ID, _LONG_NUMBER, _PHONE):
        result = pattern.sub(MASK, result)
    return result


def mask_text_with_dataset(text, data, sensitive_columns):
    """Also redact exact protected cell values occurring in a conversation.

    Unknown names and partial values cannot reliably be identified; callers
    must still tell users not to include sensitive information in questions.
    """
    result = str(text)
    words = re.findall(r"[\w]+(?:[-'’][\w]+)*", result, flags=re.UNICODE)
    candidates = {
        " ".join(words[start:start + length]).casefold()
        for start in range(len(words))
        for length in range(1, min(6, len(words) - start) + 1)
        if len(" ".join(words[start:start + length])) >= 2
    }
    if candidates:
        for column in set(sensitive_columns).intersection(data.columns):
            series = data[column].dropna().astype("string").str.strip()
            matches = series[series.str.casefold().isin(candidates)]
            for value in matches.unique():
                result = re.sub(
                    rf"(?<!\w){re.escape(str(value))}(?!\w)",
                    MASK, result, flags=re.IGNORECASE,
                )
    return mask_text(result)
