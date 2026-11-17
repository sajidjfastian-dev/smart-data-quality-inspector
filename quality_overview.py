"""Exact, value-free quality aggregates and embedded Plotly overview charts.

No inspection, persistence or correction happens here. Row positions refer to
the immutable input order (one-based), never time or an inferred business trend.
"""
from collections import Counter
from html import escape
from math import ceil
from textwrap import wrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from quality_overview_translations import QUALITY_OVERVIEW_ARABIC


BUILTINS = {
    "missing": ("Missing values", ("Missing Value",)),
    "duplicates": ("Duplicate rows", ("Duplicate Row",)),
    "email": ("Email formats", ("Invalid Email",)),
    "date": ("Date formats", ("Invalid Date", "Inconsistent Date Format")),
    "outliers": ("Numeric outliers", ("Numeric Outlier",)),
}
TEAL = "#17796b"
GOLD = "#b38b2d"
SLATE = "#69827b"
CONFIG = {"displayModeBar": False, "responsive": True, "scrollZoom": False}


def overview_translate(text):
    """Translate this component's UI, never dataset names or rule parameters.

    Keep its vocabulary local as well as registered with the app's general
    translator: embedded workspaces can retain localization across reruns.
    """
    from localization import language, translate

    if language() == "العربية" and text in QUALITY_OVERVIEW_ARABIC:
        return QUALITY_OVERVIEW_ARABIC[text]
    return translate(text)


def plot_label(value):
    """Dataset names are literal, not translated or interpreted as Plotly HTML."""
    return escape(str(value), quote=True).replace("%", "&#37;")


def _tick_label(value):
    """Bound visible label width; the exact full name remains in every hover."""
    lines = wrap(str(value), 18) or [""]
    visible = lines[:2]
    if len(lines) > 2:
        visible[-1] += "…"
    return "<br>".join(plot_label(line) for line in visible)


def aggregate_quality(data, issues, enabled_checks, custom_rules=(),
                      email_columns=(), date_columns=(), numeric_columns=(),
                      iqr_multiplier=1.5, max_ranges=24):
    """Aggregate only position/type/column metadata; never copy cell values.

    Custom findings cannot identify individual rules of the same kind, so the
    control chart deliberately aggregates by rule kind, not by expected text.
    Disabled/inapplicable controls have no assessed result, even at zero.
    """
    row_count = len(data)
    columns = list(data.columns)
    enabled = set(enabled_checks)
    selected = {
        "missing": len(columns), "duplicates": len(columns),
        "email": len(set(email_columns) & set(columns)),
        "date": len(set(date_columns) & set(columns)),
        "outliers": len(set(numeric_columns) & set(columns)),
    }
    types = issues["Issue Type"].astype(str) if not issues.empty else pd.Series(dtype=str)
    type_counts = Counter(types)
    controls = []
    for key, (label, output_types) in BUILTINS.items():
        assessed = key in enabled and selected[key] > 0 and row_count > 0
        reason = ("Disabled · not assessed" if key not in enabled else
                  "No selected columns · not assessed" if not selected[key] else
                  "No rows to assess" if not row_count else "Enabled")
        controls.append({
            "key": key, "label": label, "custom": False,
            "enabled": key in enabled, "assessed": assessed, "status": reason,
            "columns": selected[key], "rules": 0,
            "types": output_types, "count": sum(type_counts[t] for t in output_types),
        })
    configured = Counter(str(rule["kind"]) for rule in custom_rules if rule.get("column") in columns)
    # Retain recorded custom kinds even if a caller supplies an incomplete config.
    custom_kinds = list(dict.fromkeys([*configured, *(
        t.removeprefix("Custom: ") for t in types.unique() if t.startswith("Custom: ")
    )]))
    for kind in custom_kinds:
        matching = [r for r in custom_rules if r.get("kind") == kind and r.get("column") in columns]
        assessed = configured[kind] > 0 and row_count > 0
        controls.append({
            "key": f"custom:{kind}", "label": kind, "custom": True,
            "enabled": bool(configured[kind]), "assessed": assessed,
            "status": "Enabled" if assessed else "No rows to assess" if not row_count else "Recorded findings",
            "columns": len({r["column"] for r in matching}), "rules": configured[kind],
            "types": (f"Custom: {kind}",), "count": type_counts[f"Custom: {kind}"],
        })
    known_types = {t for c in controls for t in c["types"]}
    for issue_type in type_counts.keys() - known_types:
        controls.append({
            "key": f"recorded:{issue_type}", "label": issue_type, "custom": False,
            "enabled": False, "assessed": False, "status": "Recorded findings",
            "columns": 0, "rules": 0, "types": (issue_type,), "count": type_counts[issue_type],
        })

    positions = pd.to_numeric(issues["Row Number"], errors="coerce") if not issues.empty else pd.Series(dtype=float)
    valid = positions.notna() & positions.between(1, row_count) & positions.eq(positions.round())
    valid_positions = positions[valid].astype(np.int64).to_numpy()
    per_row = Counter(valid_positions)
    multiplicity = Counter(min(count, 6) for count in per_row.values())

    # Numeric category IDs distinguish duplicate-row scope from a real column
    # literally named "Entire row". Include every input column, even at zero.
    buckets = [{"id": f"column:{i}", "label": str(c), "whole_row": False, "count": 0}
               for i, c in enumerate(columns)]
    column_ids = {c: i for i, c in enumerate(columns)}
    whole_index = len(buckets)
    if "duplicates" in enabled or type_counts["Duplicate Row"]:
        buckets.append({"id": "whole-row", "label": "Whole row · duplicates", "whole_row": True, "count": 0})
    cell_counts = Counter()
    for column, issue_type in zip(issues.get("Column Name", ()), types):
        if issue_type == "Duplicate Row":
            index = whole_index
        else:
            index = column_ids.get(column)
            if index is None:
                # Preserve totals if the inspection engine ever reports a field
                # outside the supplied schema, without exposing its cell value.
                index = len(buckets)
                column_ids[column] = index
                buckets.append({"id": f"recorded:{index}", "label": str(column), "whole_row": False, "count": 0})
        buckets[index]["count"] += 1
        cell_counts[(index, issue_type)] += 1
    heat_types = list(dict.fromkeys([
        *(t for control in controls if control["assessed"] for t in control["types"]),
        *type_counts,
    ]))
    heat = [[cell_counts[(i, t)] for i in range(len(buckets))] for t in heat_types]

    bins = min(max(1, int(max_ranges)), row_count) if row_count else 0
    ends = [(i + 1) * row_count // bins for i in range(bins)]
    range_counts = np.bincount(np.searchsorted(ends, valid_positions), minlength=bins) if bins else []
    ranges = [{"start": 1 if i == 0 else ends[i - 1] + 1, "end": ends[i], "count": int(count)}
              for i, count in enumerate(range_counts)]
    unpositioned = int((~valid).sum())
    return {
        "rows": row_count, "findings": len(issues), "affected": len(per_row),
        "unflagged": row_count - len(per_row), "controls": controls,
        "assessed": any(c["assessed"] for c in controls),
        "columns": buckets, "types": heat_types, "heat": heat,
        "multiplicity": [{"findings": i, "rows": multiplicity[i]} for i in range(1, 7)],
        "ranges": ranges, "unpositioned": unpositioned, "iqr": float(iqr_multiplier),
    }


def _base(title, subtitle, tr, height=420):
    fig = go.Figure()
    # These are embedded charts, not standalone artifacts: use the workspace
    # type/palette and generous Plotly title margins rather than a second runtime.
    fig.update_layout(
        title={"text": "<b>" + "<br>".join(plot_label(line) for line in wrap(tr(title), 30))
               + "</b><br><sup>" + "<br>".join(plot_label(line) for line in wrap(subtitle, 42)) + "</sup>",
               "x": .04, "xanchor": "left", "font": {"size": 19}},
        height=height, margin={"l": 30, "r": 28, "t": 94, "b": 58},
        paper_bgcolor="#fcfdf9", plot_bgcolor="#fcfdf9",
        font={"family": "DM Sans, Noto Sans Arabic, sans-serif", "size": 15, "color": "#28594f"},
        hoverlabel={"bgcolor": "#f4f9f5", "font_size": 15, "font_family": "DM Sans, Noto Sans Arabic, sans-serif"},
        showlegend=False, bargap=.32, meta={"accessible_title": tr(title)},
    )
    fig.update_xaxes(showgrid=False, zeroline=False, automargin=True)
    fig.update_yaxes(gridcolor="#e4eee7", zeroline=False, automargin=True)
    return fig


def _empty(fig, text):
    fig.add_annotation(text=plot_label(text), x=.5, y=.5, xref="paper", yref="paper",
                       showarrow=False, font={"size": 16, "color": SLATE})
    return fig


def build_row_coverage(summary, tr=lambda s: s):
    fig = _base("Rows affected by findings", tr("Unique original rows · not a cell-based quality score"), tr)
    if not summary["rows"] or not summary["assessed"]:
        return _empty(fig, tr("No assessed rows"))
    names = [tr("Affected rows"), tr("Rows without findings")]
    values = [summary["affected"], summary["unflagged"]]
    # One composition, exactly two mutually exclusive parts; no "passed" claim.
    fig.add_trace(go.Pie(labels=names, values=values, hole=.66, sort=False,
                         marker={"colors": [GOLD, TEAL], "line": {"color": "#fcfdf9", "width": 3}},
                         textinfo="value+percent", textposition="inside",
                         hovertemplate="%{label}<br>%{value:,} · %{percent}<extra></extra>"))
    fig.update_layout(showlegend=True, legend={"orientation": "h", "y": -.12, "x": 0, "font_size": 14})
    return fig


def build_control_findings(summary, tr=lambda s: s):
    controls = summary["controls"]
    fig = _base("Findings by inspection control", tr("Zero is shown; disabled controls are not assessed"), tr,
                max(420, 112 + len(controls) * 38))
    labels, statuses = [], []
    for c in controls:
        label = tr(c["label"])
        if c["custom"]:
            label = tr("Custom") + " · " + label + f" ({c['rules']} " + tr("rule" if c["rules"] == 1 else "rules") + ")"
        labels.append(plot_label(label))
        if c["assessed"]:
            status = tr("Enabled") + f" · {c['columns']} " + tr("columns")
            if c["key"] == "outliers":
                status += f" · IQR {summary['iqr']:g}×"
        else:
            status = tr(c["status"])
        statuses.append(plot_label(status))
    ids = [c["key"] for c in controls]
    colors = [GOLD if c["custom"] else TEAL if c["assessed"] else SLATE for c in controls]
    fig.add_trace(go.Bar(x=[c["count"] for c in controls], y=ids, orientation="h",
                         marker_color=colors, customdata=list(zip(labels, statuses)),
                         text=[str(c["count"]) if c["assessed"] or c["count"] else " · " + tr("Not assessed") for c in controls],
                         textposition="outside", cliponaxis=False,
                         hovertemplate="%{customdata[0]}<br>%{x:,} " + tr("findings") + "<br>%{customdata[1]}<extra></extra>"))
    # A hollow origin marker makes a genuinely enabled zero visible, without
    # giving disabled controls a fake count or a nonzero bar.
    zeros = [c["key"] for c in controls if not c["count"]]
    fig.add_trace(go.Scatter(x=[0] * len(zeros), y=zeros, mode="markers",
                             marker={"size": 7, "symbol": "circle-open", "color": SLATE},
                             hoverinfo="skip", showlegend=False))
    tick_labels = []
    for c in controls:
        label = tr(c["label"])
        if c["custom"]:
            label = tr("Custom") + " · " + label + f" ({c['rules']} " + tr("rule" if c["rules"] == 1 else "rules") + ")"
        tick_labels.append(_tick_label(label))
    fig.update_yaxes(type="category", tickvals=ids, ticktext=tick_labels,
                     tickfont_size=14, autorange="reversed", showgrid=False, automargin=False)
    fig.update_xaxes(type="linear", rangemode="tozero", dtick=1 if max(c["count"] for c in controls) < 8 else None,
                     title_text=tr("Findings"), range=[0, max(1, max(c["count"] for c in controls)) * 1.42])
    # Non-assessed status stays visible even without opening a tooltip.
    fig.update_layout(margin={"l": 150, "r": 28})
    return fig


def _column_text(column, tr, short=False):
    label = tr(column["label"]) if column["whole_row"] else column["label"]
    if short:
        return _tick_label(label)
    return plot_label(label)


def build_column_findings(summary, indices, tr=lambda s: s):
    fields = [summary["columns"][i] for i in indices]
    fig = _base("Findings across columns", tr("All column windows include zero-findings fields"), tr, max(420, 130 + len(fields) * 38))
    fig.add_trace(go.Bar(
        x=[c["count"] for c in fields], y=[c["id"] for c in fields], orientation="h",
        marker_color=[GOLD if c["whole_row"] else TEAL for c in fields],
        customdata=[_column_text(c, tr) for c in fields],
        text=[c["count"] for c in fields], textposition="outside", cliponaxis=False,
        hovertemplate="%{customdata}<br>%{x:,} " + tr("findings") + "<extra></extra>",
    ))
    fig.update_yaxes(type="category", tickvals=[c["id"] for c in fields],
                     ticktext=[_column_text(c, tr, True) for c in fields], autorange="reversed", showgrid=False,
                     automargin=False, tickfont_size=14)
    fig.update_xaxes(type="linear", rangemode="tozero", title_text=tr("Findings"),
                     range=[0, max([c["count"] for c in fields] + [1]) * 1.25])
    fig.update_layout(margin={"l": 150, "r": 28})
    return fig


def build_type_heatmap(summary, indices, tr=lambda s: s):
    fields = [summary["columns"][i] for i in indices]
    fig = _base("Finding types × columns", tr("Exact counts · whole-row duplicates are separate"), tr, 470)
    if not summary["types"] or not fields:
        return _empty(fig, tr("No findings under assessed controls"))
    type_labels = [tr(t.removeprefix("Custom: ")) if t.startswith("Custom: ") else tr(t) for t in summary["types"]]
    type_labels = [(tr("Custom") + " · " + label) if t.startswith("Custom: ") else label
                   for t, label in zip(summary["types"], type_labels)]
    z = [[row[i] for i in indices] for row in summary["heat"]]
    names = [[[_column_text(c, tr), plot_label(label)] for c in fields] for label in type_labels]
    fig.add_trace(go.Heatmap(
        x=[c["id"] for c in fields], y=summary["types"], z=z, customdata=names,
        colorscale=[[0, "#eef4ee"], [.25, "#c0dcd0"], [.6, "#64a590"], [1, "#176c5b"]],
        zmin=0, zmax=max(1, max((max(row, default=0) for row in z), default=0)),
        xgap=3, ygap=3, colorbar={"title": tr("Findings"), "thickness": 11, "len": .75},
        hovertemplate="%{customdata[1]}<br>%{customdata[0]}<br>%{z:,} " + tr("findings") + "<extra></extra>",
    ))
    fig.update_xaxes(type="category", tickvals=[c["id"] for c in fields],
                     ticktext=[_column_text(c, tr, True) for c in fields], tickangle=-35)
    fig.update_yaxes(type="category", tickvals=summary["types"], ticktext=[_tick_label(t) for t in type_labels],
                     autorange="reversed", showgrid=False, automargin=False, tickfont_size=14)
    fig.update_layout(margin={"l": 150, "r": 20})
    return fig


def build_multiplicity(summary, tr=lambda s: s):
    fig = _base("Findings per affected row", tr("Each affected original row is counted once"), tr)
    if not summary["affected"]:
        return _empty(fig, tr("No affected rows"))
    fig.add_trace(go.Bar(
        x=[str(i) if i < 6 else "6+" for i in range(1, 7)],
        y=[b["rows"] for b in summary["multiplicity"]], marker_color=TEAL,
        hovertemplate="%{x} " + tr("findings per row") + "<br>%{y:,} " + tr("rows") + "<extra></extra>",
    ))
    fig.update_xaxes(type="category", title_text=tr("Findings per row"))
    fig.update_yaxes(type="linear", rangemode="tozero", title_text=tr("Affected rows"))
    return fig


def build_row_ranges(summary, tr=lambda s: s):
    fig = _base("Findings across original row ranges", tr("Original file positions · not a timeline or trend"), tr)
    ranges = summary["ranges"]
    labels = [f"{r['start']:,}–{r['end']:,}" for r in ranges]
    counts = [r["count"] for r in ranges]
    if summary["unpositioned"]:
        labels.append(tr("Unpositioned findings"))
        counts.append(summary["unpositioned"])
    fig.add_trace(go.Bar(x=labels, y=counts, marker_color=GOLD,
                         hovertemplate=tr("Original rows") + " %{x}<br>%{y:,} " + tr("findings") + "<extra></extra>"))
    fig.update_xaxes(type="category", title_text=tr("Original row range"), nticks=6)
    fig.update_yaxes(type="linear", rangemode="tozero", title_text=tr("Findings"))
    return fig


def render_quality_overview(data, issues, enabled_checks, custom_rules, email_columns,
                            date_columns, numeric_columns, iqr_multiplier, dataset_key):
    """Six charts only, plus chart-navigation controls and honest empty notices."""
    from localization import native

    translate = overview_translate

    summary = aggregate_quality(data, issues, enabled_checks, custom_rules, email_columns,
                                date_columns, numeric_columns, iqr_multiplier)
    with native.container(key="quality_overview"):
        if not summary["rows"]:
            native.info(translate("This file has no rows to assess."))
        elif not summary["assessed"]:
            native.info(translate("No applicable controls are enabled. Disabled checks have not assessed this file."))

        def draw(figure, key):
            native.plotly_chart(figure, width="stretch", theme=None, config=CONFIG,
                                key=f"qo_{dataset_key}_{key}",
                                alt=figure.layout.meta["accessible_title"])

        left, right = native.columns(2, gap="medium")
        with left, native.container(key="qo_panel_rows"):
            draw(build_row_coverage(summary, translate), "rows")
        with right, native.container(key="qo_panel_controls"):
            draw(build_control_findings(summary, translate), "controls")
        if not summary["rows"] or not summary["assessed"]:
            return
        window_size = 10
        page_count = max(1, ceil(len(summary["columns"]) / window_size))
        page = 0
        if page_count > 1:
            page = native.selectbox(
                translate("Column window"), range(page_count),
                format_func=lambda p: translate("Columns {0}–{1} of {2}").format(
                    p * window_size + 1, min((p + 1) * window_size, len(summary["columns"])),
                    len(summary["columns"])),
                key=f"qo_columns_{dataset_key}_{page_count}",
            )
        indices = list(range(page * window_size, min((page + 1) * window_size, len(summary["columns"]))))
        left, right = native.columns(2, gap="medium")
        with left, native.container(key="qo_panel_columns"):
            draw(build_column_findings(summary, indices, translate), "columns")
        with right, native.container(key="qo_panel_heatmap"):
            draw(build_type_heatmap(summary, indices, translate), "heatmap")
        left, right = native.columns(2, gap="medium")
        with left, native.container(key="qo_panel_multiplicity"):
            draw(build_multiplicity(summary, translate), "multiplicity")
        with right, native.container(key="qo_panel_ranges"):
            draw(build_row_ranges(summary, translate), "ranges")
