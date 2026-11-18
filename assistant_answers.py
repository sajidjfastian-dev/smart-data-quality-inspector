"""Grounded local chat answers. No generated code, network calls or data mutation."""
import re
import numpy as np
import pandas as pd


def _label(value):
    return "`" + str(value).replace("`", "'").replace("\n", " ") + "`"


def matching_columns(question, columns):
    text = question.casefold()
    return [c for c in columns if any(
        alias and re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text)
        for alias in (str(c).casefold(), str(c).replace("_", " ").casefold())
    )]


def answer_extended(question, frame, findings, original, original_findings, changes,
                    enabled, rules, protected, privacy_reviewed, history, numeric_parser,
                    corrected=False):
    """Return a supported answer or None so established quality answers can handle it."""
    q = re.sub(r"\s+", " ", question.casefold().strip())
    columns = matching_columns(q, frame.columns)
    followup = False
    if not columns and re.search(r"\b(it|that column|this column|its|average|mean|median|minimum|maximum|sum|total|top values)\b", q):
        for message in reversed(history):
            if message.get("role") == "user":
                previous = matching_columns(message.get("content", ""), frame.columns)
                if len(previous) == 1:
                    columns = previous
                    followup = True
                break
    prefix = f"Continuing with {_label(columns[0])}.\n\n" if followup else ""
    scope = "corrected copy" if corrected else "original file"
    if any(term in q for term in ("what can", "help me", "examples", "what to ask", "capabilities")):
        return (
            "**Ask about your current file**\n\n"
            "- **Quality:** “Summarize quality issues”, “Which rows have missing values?”, “Why are outliers flagged?”\n"
            "- **Numbers:** “Average amount”, “Total annual spend”, “Median age”. Name a numeric column.\n"
            "- **Breakdowns:** “Average amount by region”, “Top values in status”, “How many unique regions?”\n"
            "- **Corrections:** “What changed after fixes?”, “What should I fix first?”, “What remains unresolved?”\n"
            "- **Controls:** “Which quality rules are active?”, “Is this ready for review?”, “How do I download the approved file?”\n"
            "- **Follow-ups:** ask about a column, then “What is its average?”\n\n"
            "Local answers are calculated from your data and checks—not a general-purpose AI model. "
            "I cannot invent facts, reveal protected values, edit data through chat, or grant approval."
        )
    if any(term in q for term in ("what changed", "applied fix", "after fixes", "before and after", "improvement", "corrections applied")) or ("compare" in q and ("original" in q or "corrected" in q)):
        if not corrected:
            return "No corrected copy has been applied yet. Open **Review & fix → Apply automatic fixes**, then ask again."
        counts = changes["Change reason"].value_counts()
        details = "\n".join(f"- {kind}: **{int(n):,}**" for kind, n in counts.items()) or "- No values or rows changed."
        affected = int(findings["Row Number"].nunique()) if not findings.empty else 0
        return (
            f"**Original → corrected copy**\n\n"
            f"- Rows: **{len(original):,} → {len(frame):,}**\n"
            f"- Findings under current rules: **{len(original_findings):,} → {len(findings):,}**\n"
            f"- Rows still affected: **{affected:,}**\n\n"
            f"**Applied changes**\n{details}\n\n"
            "Counts above describe changed cells, except duplicate removal, which counts rows. "
            "See **Review & fix** for original-versus-corrected values and **Preview & export** for cell hover details. "
            "A median fill is an estimate, not a recovered source value."
        )
    if any(term in q for term in ("rules", "controls", "checks are", "checks enabled", "checks active")):
        labels = {"missing": "Missing values", "duplicates": "Exact duplicates", "email": "Email formats",
                  "date": "Dates and date formats", "outliers": "Numeric outliers",
                  "numeric": "Invalid numeric values"}
        active = ", ".join(v for k, v in labels.items() if k in enabled) or "None"
        inactive = ", ".join(v for k, v in labels.items() if k not in enabled) or "None"
        from business_rules import visible_rules
        custom = "\n".join(f"- {_label(r['column'])}: {r['kind']} — {_label(r['expected'])}" for r in visible_rules(rules, protected)) or "- None"
        return f"**Active built-in checks:** {active}.\n\n**Disabled checks:** {inactive}.\n\n**Custom rules**\n{custom}\n\nSettings → Inspection checks controls these results. Disabled checks are not evidence that a file is error-free."
    if any(term in q for term in ("ready", "submit", "approval", "approve", "download", "export", "production")):
        if not enabled and not rules:
            result = "**Not assessed:** no quality controls are enabled. Enable checks before judging readiness."
        elif len(findings):
            result = f"**{len(findings):,} findings remain** in the {scope}. Review them before submission; approval must not imply they were resolved."
        else:
            result = f"**No findings remain under the configured controls** in the {scope}. This does not prove all possible errors are absent."
        return result + (
            "\n\n**Next steps**\n"
            "1. Apply available automatic fixes, if needed.\n"
            "2. Review the before/after comparison and remaining findings.\n"
            "3. Confirm the exact version and select **Submit for review**.\n"
            "4. Complete reviewer, ticket and CAB approvals before **Download approved file**.\n\n"
            + ("Privacy review is currently marked complete; protected columns stay masked."
               if privacy_reviewed else "**Privacy review is incomplete:** review sensitive columns in Settings before submission.")
            + "\n\nSign-in and approval/ticket steps are simulated. Chat cannot approve requests or write to production."
        )
    if any(term in q for term in ("fix first", "fix all", "how to fix", "recommend", "remaining", "unresolved", "next step", "can you fix", "clean my")):
        counts = findings["Issue Type"].value_counts()
        detail = "\n".join(f"- **{int(n):,}** {kind}" for kind, n in counts.items()) or "- No current findings."
        return (
            f"**Current findings in the {scope}**\n{detail}\n\n"
            "**Apply automatic fixes** in Review & fix. Depending on enabled controls, the system removes exact duplicates, "
            "trims spaces, fills selected numeric gaps using the median, standardizes unambiguous dates and normalizes unique allowed-value matches.\n\n"
            "**Not automatically recoverable:** incorrect email addresses, ambiguous dates, missing text, outliers and "
            "business values outside limits. Verify these in the source system and upload a corrected file, or disclose them to the reviewer. "
            "There is no manual cell editor, and chat does not apply fixes."
        )
    if any(term in q for term in ("why", "explain", "meaning", "how does")) and any(term in q for term in ("median", "fill", "date", "duplicate", "whitespace")):
        return (
            "**How automatic corrections work**\n\n"
            "- **Duplicates:** keep the first exact row and remove later identical occurrences.\n"
            "- **Whitespace:** remove surrounding spaces, not meaningful characters inside values.\n"
            "- **Numeric gaps:** use the median of available numeric values in the selected column. "
            "This is a statistical estimate, not a verified original value; review whether it is appropriate for your business.\n"
            "- **Dates:** standardize valid, unambiguous dates to YYYY-MM-DD. Invalid or ambiguous dates stay unchanged.\n"
            "- **Allowed values:** normalize case/spacing only when exactly one allowed value matches.\n\n"
            "Your original stays unchanged. Ask “What changed after fixes?” for the actual changes in this file."
        )
    if any(term in q for term in ("why", "explain", "meaning")) and "outlier" in q:
        count = int((findings["Issue Type"] == "Numeric Outlier").sum())
        return (
            f"**{count:,} current outlier findings.** The app compares selected numeric values with the interquartile range: "
            "Q1 − multiplier × IQR through Q3 + multiplier × IQR, where IQR = Q3 − Q1. "
            "The multiplier is in Settings → Inspection checks → Advanced column configuration. "
            "Outliers may be legitimate; they are not changed automatically."
            + (" This check is currently disabled." if "outliers" not in enabled else "")
        )
    if any(term in q for term in ("summarize my data", "summary of my data", "overview", "describe my data", "tell me about my data", "insights")):
        affected = int(findings["Row Number"].nunique()) if not findings.empty else 0
        details = "\n".join(f"- {kind}: **{int(n):,}**" for kind, n in findings["Issue Type"].value_counts().items())
        return (
            f"**{scope.capitalize()} · {len(frame):,} rows · {len(frame.columns):,} columns**\n\n"
            f"**{len(findings):,} findings** across **{affected:,} rows** "
            f"({100*affected/max(len(frame),1):.1f}% of rows).\n\n"
            + (details or "No findings under the enabled controls.")
            + "\n\n**Columns:** " + ", ".join(_label(c) for c in frame.columns)
            + "\n\nAsk for a numeric summary, a category breakdown, active rules or the changes applied."
        )
    aggregate = re.search(r"\b(average|mean|median|sum|total|min|minimum|max|maximum|range|statistics|stats|percentile)\b", q)
    if columns and any(term in q for term in ("summarize", "summary")):
        aggregate = True
    categorical = any(term in q for term in ("top values", "most common", "distribution", "breakdown", "frequency", "unique", "distinct"))
    if columns and (aggregate or categorical):
        if re.search(r"\b(where|excluding|except|between|greater than|less than|above|below|only|correlation|forecast|predict)\b|[<>=]", q):
            return "I cannot reliably evaluate that condition in local chat. Ask for an unfiltered column summary or a grouped average, total, median, minimum or maximum."
        if any(c in protected for c in columns):
            return "I cannot list or calculate value-based breakdowns for protected columns. You can still ask about their quality findings and missing-value counts."
        group = next((c for c in columns if re.search(
            r"\bby\s+[`'\"]?" + re.escape(str(c).replace("_", " ").casefold()) + r"\b", q.replace("_", " "))), None)
        measures = [c for c in columns if c != group]
        if group is not None and aggregate and len(measures) == 1:
            measure = measures[0]
            if not re.search(r"\b(average|mean|median|sum|total|min|minimum|max|maximum)\b", q):
                return "Which grouped calculation do you want: average, total, median, minimum or maximum?"
            values = numeric_parser(frame[measure]).replace([np.inf, -np.inf], np.nan)
            operation = "mean" if any(w in q for w in ("average", "mean")) else "median" if "median" in q else "sum" if any(w in q for w in ("sum", "total")) else "min" if re.search(r"\b(min|minimum)\b",q) else "max"
            grouped = pd.DataFrame({"group": frame[group].astype("string").fillna("(empty)"), "value": values}).dropna(subset=["value"]).groupby("group")["value"].agg(operation).sort_values(ascending=False)
            if grouped.empty:
                return "No finite numeric values are available for that calculation."
            return (
                f"**{operation.capitalize()} of {_label(measure)} by {_label(group)}** · {scope}\n\n"
                + "\n".join(f"- {_label(k)}: **{v:,.4g}**" for k, v in grouped.head(15).items())
                + f"\n\nShowing {min(15,len(grouped))} of {len(grouped)} groups. Missing/non-numeric/infinite values excluded. No currency conversion performed."
            )
        if len(columns) != 1:
            return "Please name one numeric column, or ask for “average [numeric column] by [category column]”."
        column = columns[0]
        if categorical and not aggregate:
            counts = frame[column].dropna().astype(str).value_counts()
            return prefix + (
                f"**{_label(column)} · {scope}**\n\n**{len(counts):,} distinct non-null values**.\n\n"
                + "\n".join(f"- {_label(v)}: **{n:,}** ({n/max(len(frame),1)*100:.1f}% of rows)" for v,n in counts.head(10).items())
                + "\n\nTop 10 shown, ordered by frequency. Nulls excluded; empty strings remain distinct values."
            )
        values = numeric_parser(frame[column]).replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            return f"No finite numeric values in {_label(column)}. Ask for its top values or quality findings instead."
        return prefix + (
            f"**Numeric summary · {_label(column)} · {scope}**\n\n"
            f"- Valid numeric values: **{len(values):,}**; excluded: **{len(frame)-len(values):,}**\n"
            f"- Total: **{values.sum():,.6g}**\n- Average: **{values.mean():,.6g}**\n"
            f"- Median: **{values.median():,.6g}**\n- Minimum: **{values.min():,.6g}**\n"
            f"- Maximum: **{values.max():,.6g}**\n- 25th / 75th percentile: **{values.quantile(.25):,.6g} / {values.quantile(.75):,.6g}**\n\n"
            "Calculated from finite numeric values; missing/non-numeric/infinite entries excluded. No currency conversion performed."
        )
    if aggregate and not columns and re.search(r"\b(rows?|records?|columns?)\b", q):
        return None
    if aggregate or categorical:
        return "Which column should I calculate? Include its exact name, for example “average amount” or “top values in region”."
    if any(word in q for word in ("missing", "null", "blank", "empty")) and "missing" not in enabled:
        return "The missing-values quality check is disabled. Enable it in Settings → Inspection checks before interpreting missing-value findings."
    return None
