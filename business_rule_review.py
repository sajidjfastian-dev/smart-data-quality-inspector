"""Read-only business-rule coverage for the current correction workspace."""
import html

from business_rules import CORRECTABLE, applicability, findings, missing, visible_rules


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


def render_business_rule_review(data, rules, protected, corrected=False):
    from localization import native as st, translate as t

    with st.expander(t("Configured business rules") + f" · {len(rules)}", expanded=False):
        if not rules:
            st.info(t("No business rules configured. Add rules in Settings → Business rules; they will appear here for every file."))
            return
        st.caption(t("Results use the current corrected copy." if corrected else "Results use the original file."))
        st.caption(t("Inspection flags count rows per rule, not unique issues across rules. Mixed-type columns can include flags for incompatible cells."))
        safe_rules = visible_rules(rules, protected)
        results = rule_results(data, rules)
        for index, (result, safe) in enumerate(zip(results, safe_rules), 1):
            rule = result["rule"]
            with st.container(border=True):
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
