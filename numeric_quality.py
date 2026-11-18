"""Consistent numeric parsing for inspection, without guessing malformed values."""
import re

import numpy as np
import pandas as pd


NUMBER = re.compile(
    r"^[+-]?(?:[$£€¥])?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)


def parse_numbers(series):
    """Accept finite, well-formed numbers, optionally grouped or currency-prefixed."""
    def parse(value):
        if isinstance(value, (bool, np.bool_)):
            return np.nan
        if isinstance(value, str):
            text = value.strip()
            negative = text.startswith("(") and text.endswith(")")
            if negative:
                text = text[1:-1]
                if text.startswith(("+", "-")):
                    return np.nan
            if not NUMBER.fullmatch(text):
                return np.nan
            text = re.sub(r"[$£€¥,]", "", text)
            return pd.to_numeric("-" + text if negative else text, errors="coerce")
        if isinstance(value, (int, float, np.number)):
            return value
        return np.nan

    if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
        parsed = pd.to_numeric(series, errors="coerce")
    else:
        parsed = pd.to_numeric(series.map(parse), errors="coerce")
    return parsed.where(np.isfinite(parsed.to_numpy(dtype=float, na_value=np.nan)))
