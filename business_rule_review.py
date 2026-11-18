"""Read-only business-rule coverage for the current correction workspace."""
import html
import hashlib
import json

from business_rules import CORRECTABLE, applicability, findings, missing, visible_rules


# Shared by Settings and Review & fix; inspection itself still uses existing keys.
STANDARD_RULES = (
    ("missing", "Missing values", ("Missing Value",), "All columns",
     "Selected numeric gaps can be filled with the median; other gaps need source verification."),
    ("duplicates", "Duplicate rows", ("Duplicate Row",), "All columns",
     "Exact duplicate rows can be removed."),
    ("email", "Invalid email formats", ("Invalid Email",), "Email columns",
     "Check only; invalid addresses require source verification."),
    ("date", "Invalid and inconsistent dates", ("Invalid Date", "Inconsistent Date Format"), "Date columns",
     "Valid unambiguous dates can be standardized; invalid or ambiguous dates need source verification."),
    ("outliers", "Numeric outliers", ("Numeric Outlier",), "Numeric columns",
     "Check only; outliers require source verification."),
    ("numeric", "Invalid numeric values", ("Invalid Number",), "Numeric columns",
     "Check only; invalid numbers require source verification."),
)


def selection_key(scope, category, rule):
    """Stable within a file and revision, even for duplicate legacy rules."""
    identity = str(rule) if category in ("standard", "fix") else json.dumps(rule, sort_keys=True, default=str)
    if category == "business":
        identity = str(rule["id"])
    digest = hashlib.sha256(identity.encode()).hexdigest()[:16]
    return f"review_rule_{scope}_{category}_{digest}"

def saved_selections(scope, choices, legacy_rules):
    """Capture choices without the revision-specific widget prefix."""
    prefix = f"review_rule_{scope}_"
    return {
        "choices": {key[len(prefix):]: value for key, value in choices.items()
                    if key.startswith(prefix) and isinstance(value, bool)},
        "legacy_rules": [dict(rule) for rule in legacy_rules],
    }


def restore_selections(scope, saved, choices):
    """Restore only this revision's choices; unknown definitions default to selected."""
    prefix = f"review_rule_{scope}_"
    for identity, value in saved.get("choices", {}).items():
        if isinstance(identity, str) and isinstance(value, bool):
            choices.setdefault(prefix + identity, value)


def rule_results(data, rules):
    """Use the inspection engine's predicates, without caching session results."""
    results = []
    for rule in rules:
        enabled = rule.get("enabled", True)
        column = rule["column"]
        notes = applicability(data, [rule])
        status = "Applicable"
        populated = []
        if column not in data:
            status = "Not applicable"
        else:
            populated = [value for value in data[column] if not missing(value)]
            if populated:
                if rule["kind"] in CORRECTABLE:
                    compatible = sum(isinstance(value, str) for value in populated)
                elif rule["kind"] in ("Minimum number", "Maximum number"):
                    from numeric_quality import parse_numbers
                    compatible = int(parse_numbers(data[column]).notna().sum())
                else:
                    compatible = len(populated)
                if compatible == 0:
                    status = "Not applicable"
                elif compatible < len(populated):
                    status = "Partially applicable"
        # Do not describe an absent/incompatible column or a disabled rule as passed.
        count = None
        if enabled and status != "Not applicable" and populated:
            count = len(findings(data, [rule]))
        results.append({
            "rule": rule, "enabled": enabled, "applicability": status,
            "notes": notes, "count": count,
            "empty": column in data and not populated,
        })
    return results


def render_business_rule_review(data, rules, protected, corrected=False, *,
                                enabled_checks=None, standard_findings=None,
                                email_columns=(), date_columns=(), numeric_columns=(),
                                legacy_rules=(), fix_settings=None, selection_scope=None,
                                on_selection_change=None, selection_args=(), choices=None):
    from localization import native as st, translate as t
    choices = choices or {}

    all_count = len(rules) + len(legacy_rules) + (
        len(STANDARD_RULES) + int(fix_settings is not None) if enabled_checks is not None else 0
    )
    with st.expander(t("Configured business rules") + f" · {all_count}", expanded=selection_scope is not None):
        if not all_count:
            st.info(t("No business rules configured. Add rules in Settings → Business rules; they will appear here for every file."))
            return
        st.caption(t("Results use the current corrected copy." if corrected else "Results use the original file."))
        if selection_scope is not None:
            st.caption(t("All rules are selected by default. Uncheck a rule for this file, then apply fixes again."))
        st.caption(t("Inspection flags count rows per rule, not unique issues across rules. Mixed-type columns can include flags for incompatible cells."))
        if enabled_checks is not None:
            targets = {"All columns": list(data.columns), "Email columns": list(email_columns),
                       "Date columns": list(date_columns), "Numeric columns": list(numeric_columns)}
            for key, label, issue_types, target, behavior in STANDARD_RULES:
                enabled = key in enabled_checks
                applicable = bool(targets[target])
                with st.container(border=True):
                    if selection_scope is not None:
                        widget_key = selection_key(selection_scope, "standard", key)
                        st.checkbox(t(label), value=choices.get(widget_key, True), key=widget_key,
                                    on_change=on_selection_change, args=selection_args + (widget_key,))
                    else:
                        st.markdown("**" + html.escape(t(label)) + "**")
                    st.caption(" · ".join((t("Enabled" if enabled else "Disabled"),
                                             t("Applicable" if applicable else "Not applicable"))))
                    st.caption(t("Target") + ": " + t(target))
                    st.caption(t(behavior))
                    fix_key = {"missing": "missing_numeric", "duplicates": "duplicates", "date": "dates"}.get(key)
                    if fix_key and fix_settings is not None:
                        fix_on = (fix_settings.get(fix_key, True) and enabled and applicable
                                  and (key != "missing" or bool(numeric_columns)))
                        st.caption(t("Automatic correction enabled" if fix_on else "Automatic correction off or not applicable"))
                    if not enabled:
                        st.caption(t("Not evaluated — rule is disabled."))
                    elif not applicable:
                        st.caption(t("Not evaluated — no matching columns are selected."))
                    elif standard_findings is not None:
                        count = int(standard_findings["Issue Type"].isin(issue_types).sum())
                        st.caption(t("Inspection flags") + f": {count:,}")
            if fix_settings is not None:
                with st.container(border=True):
                    if selection_scope is not None:
                        widget_key = selection_key(selection_scope, "fix", "whitespace")
                        st.checkbox(t("Trim leading and trailing whitespace"), value=choices.get(widget_key, True),
                                    key=widget_key, on_change=on_selection_change, args=selection_args + (widget_key,))
                    else:
                        st.markdown("**" + t("Trim leading and trailing whitespace") + "**")
                    st.caption(t("Enabled" if fix_settings.get("whitespace", True) else "Disabled") + " · "
                               + t("Automatic correction"))
                    st.caption(t("Target") + ": " + t("Text columns"))
        for index, (raw_legacy, legacy) in enumerate(zip(legacy_rules, visible_rules(legacy_rules, protected))):
            with st.container(border=True):
                widget_key = selection_key(selection_scope, f"legacy_{index}", raw_legacy) if selection_scope else None
                selected = choices.get(widget_key, True)
                if selection_scope is not None:
                    st.checkbox(t(legacy["kind"]) + " · " + str(legacy["column"]), value=selected,
                                key=widget_key, on_change=on_selection_change, args=selection_args + (widget_key,))
                else:
                    st.markdown("**" + html.escape(t(legacy["kind"])) + "**")
                st.caption(t("Enabled" if selected else "Disabled") + " · " + t("Applicable" if legacy["column"] in data else "Not applicable"))
                st.markdown(
                    "<div><strong>" + html.escape(t("Target column")) + ":</strong> <bdi>"
                    + html.escape(str(legacy["column"])) + "</bdi><br><strong>"
                    + html.escape(t("Condition")) + ":</strong> <bdi>"
                    + html.escape(str(legacy["expected"])) + "</bdi></div>",
                    unsafe_allow_html=True,
                )
                if legacy["kind"] == "Allowed values":
                    st.caption(t("Unambiguous allowed values can be normalized."))
                    if fix_settings is not None:
                        st.caption(t("Automatic correction enabled" if selected and fix_settings.get("allowed", True)
                                     else "Automatic correction off or not applicable"))
                else:
                    st.caption(t("Check only"))
        safe_rules = visible_rules(rules, protected)
        results = rule_results(data, rules)
        for index, (result, safe) in enumerate(zip(results, safe_rules), 1):
            rule = result["rule"]
            with st.container(border=True):
                if selection_scope is not None:
                    widget_key = selection_key(selection_scope, "business", rule)
                    st.checkbox(f"{index} · {t(rule['kind'])} · {rule['column']}",
                                value=choices.get(widget_key, True), key=widget_key,
                                on_change=on_selection_change, args=selection_args + (widget_key,))
                else:
                    st.markdown(f"**{index} · {t(rule['kind'])}**")
                st.caption(" · ".join([
                    t("Enabled" if result["enabled"] else "Disabled"),
                    t(result["applicability"]),
                    t("Automatic correction supported" if rule.get("mode") == "Correct automatically"
                      and rule["kind"] in CORRECTABLE else "Check only"),
                ]))
                # Column names and parameters are user data: escape, never translate.
                condition = safe["expected"] or t(rule["kind"])
                st.markdown(
                    "<div><strong>" + html.escape(t("Target column")) + ":</strong> <bdi>"
                    + html.escape(str(rule["column"])) + "</bdi><br><strong>"
                    + html.escape(t("Condition")) + ":</strong> <bdi>"
                    + html.escape(str(condition)) + "</bdi></div>",
                    unsafe_allow_html=True,
                )
                if not result["enabled"]:
                    st.caption(t("Not evaluated — rule is disabled."))
                elif result["applicability"] == "Not applicable":
                    st.caption(t("Not evaluated — target column is absent or has incompatible values."))
                elif result["empty"]:
                    st.caption(t("Not evaluated — no populated values. Missing values are covered by the missing-value check."))
                else:
                    st.caption(t("Inspection flags") + f": {result['count']:,}")
                for note in result["notes"]:
                    # Applicability diagnostics contain column names, but no cell values.
                    st.text(note)
        conflicts = applicability(data, [r for r in rules if r.get("enabled", True)])
        individual_notes = {note for r in results for note in r["notes"]}
        for note in conflicts:
            if note not in individual_notes:
                st.warning(note)
