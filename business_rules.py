"""Account-owned business rules, using the existing custom-rule contract."""
import json
import math
from html import escape

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


def invalidate_rule_results(state):
    from review_approval import invalidate
    for dataset in list(state.get("review_contexts", {})):
        invalidate(state, dataset)
    for key in ("quality_scan_cache", "review_scan_cache", "fixed_export_cache"):
        state[key] = {}
    state["batch_export_cache"] = None
    state["fixed_datasets"] = {}


def render_editor(st, state, data=None, protected_columns=()):
    from localization import translate
    from business_rule_text import parse_rule_text, rule_as_text
    from business_rule_store import load_into_state, save as save_rules
    from demo_store import DemoStoreError, DemoConflict
    rules = state.setdefault("business_rules", [])
    reset_input = state.pop("business_rule_reset_input", None)
    if reset_input:
        state.pop(reset_input, None)
    editing_id = state.get("business_rule_edit_id")
    selected = next((r for r in rules if r.get("id") == editing_id), None)
    if editing_id and selected is None:
        state.pop("business_rule_edit_id", None)
        editing_id = None
    input_key = f"business_rule_text_{editing_id or 'new'}"
    protected = {str(c) for c in protected_columns}
    hide_values = bool(selected and str(selected["column"]) in protected and selected.get("expected"))
    st.markdown("### Business rules")
    st.caption("Rules are private to your account and kept until you delete them. Rule values are saved; uploaded files remain session-only.")
    st.caption("Use the examples and the exact column name. Rules apply to matching files.")
    if state.pop("business_rules_notice", False):
        st.success("Rules updated. Apply automatic fixes again to prepare a fresh correction preview.")
    if hide_values:
        st.info("Protected values are hidden. Re-enter the full rule to update it.")
    if selected and st.button("Cancel editing", key="cancel_business_rule_edit"):
        state["business_rule_reset_input"] = input_key
        state.pop("business_rule_edit_id", None)
        st.rerun()

    def has_manual_corrections():
        for dataset, record in state.get("fix_change_indexes", {}).items():
            if (dataset in state.get("fixed_datasets", {}) and
                    record["changes"]["Change reason"].str.startswith("Manual correction").any()):
                return True
        return False

    if state.get("_business_rules_conflict"):
        st.warning("Your saved rules changed in another session. Reload them before editing.")
        if st.button("Reload saved rules"):
            try:
                if has_manual_corrections():
                    raise ValueError("Existing manual corrections are preserved. Resolve them before changing business rules.")
                load_into_state(state)
                invalidate_rule_results(state)
                state.pop("_business_rules_conflict", None)
                state.pop("business_rule_edit_id", None)
                state["business_rule_reset_input"] = input_key
                state["business_rules_notice"] = True
                st.rerun()
            except DemoStoreError:
                st.error("Saved rules could not be loaded. Please retry.")
            except ValueError as error:
                st.error(str(error))

    with st.form(f"business_rule_editor_{editing_id or 'new'}"):
        text = st.text_input(
            "Business rule",
            value=rule_as_text(selected) if selected and not hide_values else "",
            placeholder=translate("Example: age must be at least 18"),
            key=input_key,
        )
        st.caption('Examples: “age must be at least 18”, “status must be one of Open, Closed”, “replace pending with approved in status”, or “trim whitespace in name”.')
        save = st.form_submit_button("Save business rule" if selected else "Add business rule",
                                     disabled=bool(state.get("_business_rules_conflict")))

    def persist(updated):
        saved, version = save_rules(state.get("_auth_session"), state.get("auth_subject"),
                                    updated, state["_business_rules_version"])
        state["business_rules"] = saved
        state["_business_rules_version"] = version
        invalidate_rule_results(state)
        state["business_rules_notice"] = True

    if save:
        try:
            if has_manual_corrections():
                raise ValueError("Existing manual corrections are preserved. Resolve them before changing business rules.")
            rule = parse_rule_text(text, selected["id"] if selected else None)
            updated = [dict(existing) for existing in rules]
            if selected:
                updated[rules.index(selected)] = rule
            else:
                updated.append(rule)
            persist(updated)
            state["business_rule_reset_input"] = input_key
            state.pop("business_rule_edit_id", None)
            st.rerun()
        except DemoConflict:
            state["_business_rules_conflict"] = True
            st.rerun()
        except DemoStoreError:
            st.error("Rules could not be saved. Your previous saved rules are unchanged; please retry.")
        except ValueError as error:
            st.error(str(error))

    if rules:
        st.markdown("#### Your business rules")
        for rule in list(rules):
            label, edit, delete = st.columns([4, 1.5, 1.5], vertical_alignment="center")
            with label:
                text = rule_as_text(rule, str(rule["column"]) in protected)
                st.markdown("<span>" + escape(text) + "</span>", unsafe_allow_html=True)
                st.caption(translate("Automatic correction" if rule["mode"] == "Correct automatically" else "Check only"))
            with edit:
                if st.button("Edit", key=f"business_rule_edit_{rule['id']}",
                             disabled=bool(state.get("_business_rules_conflict"))):
                    state["business_rule_edit_id"] = rule["id"]
                    state["business_rule_reset_input"] = f"business_rule_text_{rule['id']}"
                    st.rerun()
            with delete:
                if st.button("Delete", key=f"business_rule_delete_{rule['id']}",
                             disabled=bool(state.get("_business_rules_conflict"))):
                    if has_manual_corrections():
                        st.error("Existing manual corrections are preserved. Resolve them before changing business rules.")
                    else:
                        try:
                            persist([dict(existing) for existing in rules if existing["id"] != rule["id"]])
                            if editing_id == rule["id"]:
                                state.pop("business_rule_edit_id", None)
                                state["business_rule_reset_input"] = input_key
                            st.rerun()
                        except DemoConflict:
                            state["_business_rules_conflict"] = True
                            st.rerun()
                        except DemoStoreError:
                            st.error("Rules could not be saved. Your previous saved rules are unchanged; please retry.")
                        except ValueError as error:
                            st.error(str(error))
    return [{**r, "enabled": True} for r in state["business_rules"]]
