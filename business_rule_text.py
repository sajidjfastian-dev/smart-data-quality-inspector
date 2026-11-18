"""Interpret explicit rule sentences without guessing business facts."""
import json
import re
import uuid


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Check the quotation marks in your rule.") from None
        if not isinstance(decoded, str):
            raise ValueError("Use text inside the quotation marks.")
        return decoded
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1]
    return value


def _quoted(value):
    return json.dumps(str(value), ensure_ascii=False)


def parse_rule_text(text, rule_id=None):
    from business_rules import validate

    text = text.strip()
    if not text or len(text) > 12000:
        raise ValueError("Enter a business rule under 12,000 characters.")
    if re.fullmatch(r"(?:remove|drop)\s+(?:exact\s+)?duplicates?(?:\s+rows?)?", text, re.I):
        raise ValueError("Duplicate-row removal is already included. Select it in Review & fix.")

    rules = (
        (r"^(.+?)\s+must\s+contain\s+(.+)$", "Must contain", "Check only"),
        (r"^(.+?)\s+must\s+be\s+(?:one\s+of|in)\s+(.+)$", "Allowed values", "Correct automatically"),
        (r"^(.+?)\s+must\s+be\s+(?:at\s+least|greater\s+than\s+or\s+equal\s+to)\s+(.+)$", "Minimum number", "Check only"),
        (r"^(.+?)\s+must\s+be\s+(?:at\s+most|less\s+than\s+or\s+equal\s+to)\s+(.+)$", "Maximum number", "Check only"),
    )
    column = kind = expected = mode = None
    for pattern, rule_kind, rule_mode in rules:
        match = re.fullmatch(pattern, text, flags=re.I | re.S)
        if match:
            column, expected = _unquote(match.group(1)), _unquote(match.group(2))
            kind, mode = rule_kind, rule_mode
            break
    if kind is None:
        token = r'("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\s]+)'
        replacement = re.fullmatch(
            rf"replace\s+{token}\s+with\s+{token}\s+in\s+(.+)", text, re.I | re.S
        )
        mapping = re.fullmatch(r"map\s+(\{.*\})\s+in\s+(.+)", text, re.I | re.S)
        transform = re.fullmatch(r"(?:trim\s+(?:whitespace|spaces)\s+in|lowercase|uppercase)\s+(.+)", text, re.I | re.S)
        if replacement:
            old, new, column = (_unquote(part) for part in replacement.groups())
            kind, expected, mode = "Value mapping", json.dumps({old: new}, ensure_ascii=False), "Correct automatically"
        elif mapping:
            expected, column = mapping.groups()
            column = _unquote(column)
            kind, mode = "Value mapping", "Correct automatically"
        elif transform:
            column = _unquote(transform.group(1))
            kind = "Trim whitespace" if text.lower().startswith("trim ") else (
                "Lowercase" if text.lower().startswith("lowercase ") else "Uppercase"
            )
            expected, mode = "", "Correct automatically"
    if kind is None:
        raise ValueError(
            'Rule not understood. Try “age must be at least 18”, '
            '“status must be one of Open, Closed”, or “trim whitespace in name”.'
        )
    return validate({"id": rule_id or uuid.uuid4().hex, "column": column, "kind": kind,
                     "expected": expected, "mode": mode, "enabled": True, "business": True})


def rule_as_text(rule, protected=False):
    column = _quoted(rule["column"])
    kind, value = rule["kind"], rule.get("expected", "")
    if protected and value:
        return f'{column} · {kind} · protected values hidden'
    if kind == "Must contain":
        return f"{column} must contain {_quoted(value)}"
    if kind == "Allowed values":
        return f"{column} must be one of {value}"
    if kind == "Minimum number":
        return f"{column} must be at least {value}"
    if kind == "Maximum number":
        return f"{column} must be at most {value}"
    if kind == "Value mapping":
        return f"map {value} in {column}"
    if kind == "Trim whitespace":
        return f"trim whitespace in {column}"
    if kind == "Lowercase":
        return f"lowercase {column}"
    if kind == "Uppercase":
        return f"uppercase {column}"
    return f"{column} · {kind}"
