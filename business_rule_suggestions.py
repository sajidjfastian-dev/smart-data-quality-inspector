"""Evidence-based rule ideas, not inferred business policies or corrections."""
import re


def suggest_business_rules(data, configured, numeric_columns, protected):
    """Suggest reviewable rule types from field names/types, without using cell values.

    The owner must choose the business meaning and exact thresholds/allowed values.
    No rule is created or applied here.
    """
    protected_names = {str(c) for c in protected}
    numeric = {str(c) for c in numeric_columns}
    existing = {(str(rule.get("column", "")).casefold(), rule.get("kind"))
                for rule in configured}
    suggestions = []
    for column in data.columns[:100]:
        name = str(column)
        if name in protected_names:
            continue
        words = set(re.findall(r"[a-z]+", name.casefold()))
        kind = None
        explanation = None
        if words & {"status", "state", "category", "type"}:
            kind = "Allowed values"
            explanation = "A category-like field may need an approved list of values."
        elif name in numeric and words & {"amount", "balance", "price", "cost", "quantity", "count", "rate"}:
            kind = "Minimum number"
            explanation = "A numeric business measure may need a lower limit agreed by the data owner."
        if kind and (name.casefold(), kind) not in existing:
            suggestions.append({"column": name, "kind": kind, "reason": explanation})
        if len(suggestions) >= 8:
            break
    return suggestions
