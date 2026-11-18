"""Session-wide business rules, using the existing custom-rule contract."""
import json
import math
import uuid

import pandas as pd

KINDS = ("Must contain", "Allowed values", "Minimum number", "Maximum number",
         "Value mapping", "Trim whitespace", "Lowercase", "Uppercase")
CORRECTABLE = {"Allowed values", "Value mapping", "Trim whitespace", "Lowercase", "Uppercase"}


def visible_rules(rules, protected):
    """Rule parameters may themselves contain protected old/new cell values."""
    names = {str(column) for column in protected}
    return [{**r, "expected": "••••" if str(r["column"]) in names else r["expected"]} for r in rules]


def validate(rule):
    if not rule["column"].strip():
        raise ValueError("Enter the target column name.")
    kind, expected = rule["kind"], rule["expected"].strip()
    if len(expected) > 10000 or len(rule["column"]) > 256:
        raise ValueError("Keep rule values under 10,000 characters and column names under 256.")
    if kind not in KINDS:
        raise ValueError("Unsupported rule type.")
    if rule.get("mode") not in ("Check only", "Correct automatically"):
        raise ValueError("Select a supported rule behavior.")
    if rule.get("mode") == "Correct automatically" and kind not in CORRECTABLE:
        raise ValueError("This rule can validate data but cannot safely correct it.")
    if kind in ("Minimum number", "Maximum number"):
        try:
            if not math.isfinite(float(expected)):
                raise ValueError
        except ValueError:
            raise ValueError("Enter a finite number for the limit.") from None
    elif kind == "Value mapping":
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("A mapping source must have exactly one destination.")
                result[key] = value
            return result
        try:
            mapping = json.loads(expected, object_pairs_hook=unique)
        except (json.JSONDecodeError, TypeError):
            raise ValueError('Enter a JSON object such as {"old": "approved"}.') from None
        if not isinstance(mapping, dict) or not mapping or any(
            not isinstance(v, str) or not k.strip() or not v.strip() for k, v in mapping.items()
        ):
            raise ValueError("Mappings must contain nonempty text sources and text destinations.")
        if any(v in mapping and mapping[v] != v for v in mapping.values()):
            raise ValueError("Chained or cyclic mappings are ambiguous; map directly to final values.")
    elif kind in ("Must contain", "Allowed values") and not expected:
        raise ValueError("Enter an expected value.")
    elif kind == "Allowed values":
        allowed = [v.strip() for v in expected.split(",") if v.strip()]
        if not allowed or len({v.casefold() for v in allowed}) != len(allowed):
            raise ValueError("Allowed values must be distinct, including case-insensitive matches.")
    return rule


def missing(value):
    return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())


def candidate(value, rule):
    if missing(value) or not isinstance(value, str):
        return value
    kind = rule["kind"]
    if kind == "Trim whitespace":
        return value.strip()
    if kind == "Lowercase":
        return value.lower()
    if kind == "Uppercase":
        return value.upper()
    if kind == "Value mapping":
        return json.loads(rule["expected"]).get(value, value)
    if kind == "Allowed values":
        options = [v.strip() for v in rule["expected"].split(",") if v.strip()]
        matches = [v for v in options if v.casefold() == value.strip().casefold()]
        return matches[0] if len(matches) == 1 else value
    return value


def valid(value, rule):
    if missing(value):
        return True  # Missingness remains governed by the existing missing-value check.
    kind, expected = rule["kind"], rule["expected"]
    if kind == "Must contain":
        return expected.casefold() in str(value).strip().casefold()
    if kind == "Allowed values":
        return str(value).strip() in {v.strip() for v in expected.split(",")}
    if kind in ("Minimum number", "Maximum number"):
        try:
            from numeric_quality import parse_numbers
            number = parse_numbers(pd.Series([value])).iloc[0]
            return math.isfinite(number) and (number >= float(expected) if kind == "Minimum number" else number <= float(expected))
        except (ValueError, TypeError):
            return False
    return isinstance(value, str) and candidate(value, rule) == value


def applicability(data, rules):
    messages = []
    for rule in rules:
        column = rule["column"]
        if column not in data:
            messages.append(f"{column}: column not present in this file.")
        elif rule["kind"] in CORRECTABLE:
            if any(not missing(v) and not isinstance(v, str) for v in data[column]):
                messages.append(f"{column}: text rule does not apply to non-text cells.")
        elif rule["kind"] in ("Minimum number", "Maximum number"):
            from numeric_quality import parse_numbers
            if (data[column].map(lambda v: not missing(v)) & parse_numbers(data[column]).isna()).any():
                messages.append(f"{column}: numeric rule found nonnumeric values; verify their source.")
    for column in {r["column"] for r in rules}:
        relevant = [r for r in rules if r["column"] == column]
        kinds = {r["kind"] for r in relevant}
        sets = [{v.strip() for v in r["expected"].split(",") if v.strip()}
                for r in relevant if r["kind"] == "Allowed values"]
        if sets and not set.intersection(*sets):
            messages.append(f"{column}: allowed-value rules have no common value.")
        if sum(r.get("mode") == "Correct automatically" for r in relevant) > 1:
            messages.append(f"{column}: competing corrections are skipped unless they agree and satisfy all rules.")
        if {"Uppercase", "Lowercase"} <= kinds:
            messages.append(f"{column}: uppercase and lowercase rules conflict; no automatic correction.")
        lower = [float(r["expected"]) for r in rules if r["column"] == column and r["kind"] == "Minimum number"]
        upper = [float(r["expected"]) for r in rules if r["column"] == column and r["kind"] == "Maximum number"]
        if lower and upper and max(lower) > min(upper):
            messages.append(f"{column}: minimum exceeds maximum.")
    return messages


def findings(data, rules):
    rows = []
    for rule in rules:
        if not rule.get("enabled", True) or rule["column"] not in data:
            continue
        series = data[rule["column"]]
        if rule["kind"] in ("Minimum number", "Maximum number"):
            from numeric_quality import parse_numbers
            numbers = parse_numbers(series)
            accepted = numbers.ge(float(rule["expected"])) if rule["kind"] == "Minimum number" else numbers.le(float(rule["expected"]))
            flags = ~series.map(missing) & ~accepted
        else:
            flags = series.map(lambda value: not valid(value, rule))
        for pos, (value, failed) in enumerate(zip(series, flags)):
            if failed:
                rows.append({"Row Number": pos + 1, "Column Name": rule["column"],
                             "Issue Type": "Custom: " + rule["kind"],
                             "Current Value": str(value),
                             "Suggested Fix": "Apply the configured rule only when unambiguous; otherwise verify the source."})
    return rows


def apply_rules(data, rules):
    """Reject ambiguous proposals or changes violating another rule on the column."""
    corrected = data.copy(deep=True)
    reasons = {}
    for col, column in enumerate(data.columns):
        relevant = [r for r in rules if r["column"] == column and r.get("enabled", True)]
        automatic = [r for r in relevant if r.get("business") and r.get("mode") == "Correct automatically"]
        if not automatic:
            continue
        for pos, value in enumerate(data[column]):
            if missing(value):
                continue
            proposals = [candidate(value, r) for r in automatic]
            changed = {v for v in proposals if v != value}
            if len(changed) != 1:
                continue
            proposed = next(iter(changed))
            if all(valid(proposed, r) for r in relevant):
                corrected.iloc[pos, col] = proposed
                kinds = sorted({r["kind"] for r in automatic if candidate(value, r) != value})
                reasons[(pos, col)] = "Business rule: " + kinds[0] if len(kinds) == 1 else "Applied compatible business rules"
    return corrected, reasons


def render_editor(st, state, data=None):
    from localization import translate
    rules = state.setdefault("business_rules", [])
    st.markdown("### Business rules")
    st.caption("Define column names before upload. Rules apply to matching columns in every file in this session.")
    st.caption("Built-in cleanup runs first. Business corrections must agree and satisfy the other rules for their column. No missing facts are invented.")
    if state.pop("business_rules_notice", False):
        st.success("Rules updated. Apply automatic fixes again to prepare a fresh correction preview.")
    selection = st.selectbox("Business rule to edit", range(len(rules) + 1),
                            format_func=lambda i: "New rule" if i == 0 else f"{i}. {rules[i-1]['column']} · {rules[i-1]['kind']}",
                            key="business_rule_selection")
    selected = rules[selection - 1] if selection else None
    with st.form(f"business_rule_editor_{selection}"):
        column = st.text_input("Target column name", value=selected["column"] if selected else "",
                               help="Matches the column name exactly, including spaces and case.")
        kind = st.selectbox("Business rule type", KINDS, index=KINDS.index(selected["kind"]) if selected else 0,
                            format_func=translate)
        expected = st.text_input("Business rule value", value=selected["expected"] if selected else "",
                                 help='Text, comma-separated allowed values, numeric limit, or JSON mapping. Formatting rules need no value.')
        mode = st.selectbox("Rule behavior", ["Check only", "Correct automatically"],
                            index=int(bool(selected and selected.get("mode") == "Correct automatically")),
                            format_func=translate)
        save = st.form_submit_button("Save business rule" if selected else "Add business rule")
    delete = st.button("Delete business rule", disabled=not selected)
    if save or delete:
        try:
            if delete:
                rules.pop(selection - 1)
            else:
                rule = validate(dict(column=column, kind=kind, expected=expected.strip(),
                                     mode=mode, enabled=True, business=True,
                                     id=selected["id"] if selected else uuid.uuid4().hex))
                if selected:
                    rules[selection - 1] = rule
                else:
                    rules.append(rule)
            from review_approval import invalidate
            for dataset in list(state.get("review_contexts", {})):
                invalidate(state, dataset)
            for key in ("quality_scan_cache", "review_scan_cache", "fixed_export_cache"):
                state[key] = {}
            state["batch_export_cache"] = None
            # A proposal generated under old rules must not be submitted as if it
            # used the new rules. Keep originals, lineage and row-choice stores;
            # the next Apply regenerates only the corrected working copies.
            state["fixed_datasets"] = {}
            state["business_rules_notice"] = True
            state["business_rule_reset_selection"] = True
            st.rerun()
        except ValueError as error:
            st.error(str(error))
    return [{**r, "enabled": True} for r in rules]
