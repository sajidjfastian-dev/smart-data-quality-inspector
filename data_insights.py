"""Interactive, dataset-driven analysis views for the active workspace file."""
from datetime import date, datetime
from html import escape

import numpy as np
import pandas as pd
from security_guardrails import mask_dataframe
import plotly.express as px
import plotly.graph_objects as go
from localization import st, translate, display_profile


SAMPLE_LIMIT = 100_000
CHART_COLOR = "#61A9BD"
CHART_CONFIG = {"displayModeBar": False, "responsive": True}


def _plot_label(value):
    """Keep dataset labels literal, including Plotly HTML and template syntax."""
    return escape(str(value), quote=True).replace("%", "&#37;")


def _short_label(value, limit=38):
    text = str(value)
    return _plot_label(text if len(text) <= limit else text[:limit - 1] + "…")


def insight_sample(data, limit=SAMPLE_LIMIT):
    """Select evenly spaced rows for expensive exploratory views."""
    if len(data) <= limit:
        return data, False
    positions = np.linspace(0, len(data) - 1, num=limit, dtype=np.int64)
    return data.iloc[positions], True


def category_counts(series, limit=10):
    values = series.astype("string").str.strip()
    values = values[values.notna() & values.ne("")]
    counts = values.value_counts().head(limit)
    return pd.DataFrame({"Value": counts.index.astype(str), "Rows": counts.to_numpy()})


def date_counts(series):
    """Count parseable text/datetime values by UTC month, never treating numbers as dates."""
    date_like = series.map(lambda value: isinstance(value, (str, date, datetime, np.datetime64)))
    parsed = pd.to_datetime(series[date_like], errors="coerce", format="mixed", utc=True).dropna()
    if parsed.empty:
        return pd.DataFrame(columns=["Month", "Rows"]), 0
    months = parsed.dt.strftime("%Y-%m").value_counts().sort_index()
    counts = pd.DataFrame({
        "Month": pd.to_datetime(months.index, format="%Y-%m"),
        "Rows": months.to_numpy(),
    })
    return counts, len(parsed)


def numeric_summary(series, parser):
    numeric = parser(series).dropna()
    numeric = numeric[np.isfinite(numeric.to_numpy(dtype=float))]
    if numeric.empty:
        return {"count": 0}
    values = numeric.to_numpy(dtype=float)
    counts, edges = np.histogram(values, bins=40)
    return {
        "count": len(values),
        "mean": float(numeric.mean()),
        "median": float(numeric.median()),
        "minimum": float(numeric.min()),
        "maximum": float(numeric.max()),
        "counts": counts,
        "edges": edges,
    }


def numeric_relationship(data, x_column, y_column, parser, point_limit=2_000):
    """Calculate a correlation on the analysis sample and limit rendered points."""
    sampled = len(data) > SAMPLE_LIMIT
    if sampled:
        positions = np.linspace(0, len(data) - 1, num=SAMPLE_LIMIT, dtype=np.int64)
        x_values = data[x_column].iloc[positions]
        y_values = data[y_column].iloc[positions]
    else:
        x_values, y_values = data[x_column], data[y_column]
    x = parser(x_values).to_numpy(dtype=float, na_value=np.nan)
    y = parser(y_values).to_numpy(dtype=float, na_value=np.nan)
    finite = np.isfinite(x) & np.isfinite(y)
    pairs = pd.DataFrame({"X": x[finite], "Y": y[finite]})
    correlation = pairs["X"].corr(pairs["Y"]) if len(pairs) >= 2 else np.nan
    points, points_sampled = insight_sample(pairs, limit=point_limit)
    return {
        "pairs": len(pairs),
        "correlation": correlation,
        "points": points,
        "sampled": sampled,
        "points_sampled": points_sampled,
    }


def _chart_style(figure, x_title, y_title, height=390):
    figure.update_layout(
        template="plotly_white",
        xaxis_title=x_title,
        yaxis_title=y_title,
        height=height,
        margin=dict(l=16, r=64, t=24, b=54),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Tahoma, sans-serif", size=12, color="#526c68"),
        hoverlabel=dict(bgcolor="#F3F7F6", font=dict(size=13, color="#264C50")),
        hovermode="closest",
        bargap=0.24,
        showlegend=False,
    )
    figure.update_xaxes(
        automargin=True, zeroline=False, showline=True, linecolor="#D4E1DF",
        showgrid=False, ticks="outside", tickcolor="#D4E1DF",
        title_standoff=18, tickfont=dict(size=11),
    )
    figure.update_yaxes(
        automargin=True, zeroline=False, showline=False,
        gridcolor="#E1EAE8", gridwidth=1, title_standoff=16,
        tickfont=dict(size=11),
    )
    return figure


def _completeness_chart(data, profile, sensitive_columns):
    """Rank field coverage without reading or exposing protected values."""
    protected_names = {str(column) for column in sensitive_columns}
    safe_names = {
        str(column) for column in data.columns
        if column not in sensitive_columns and str(column) not in protected_names
    }
    fields = profile.loc[profile["Column"].isin(safe_names)].copy()
    st.subheader("Completeness by field")
    st.caption("Filled means not missing, not necessarily valid. Protected fields are excluded from this chart.")
    if not len(data) or fields.empty:
        st.info("No unprotected fields with rows are available for a completeness chart.")
        return
    fields = fields.sort_values("Missing", ascending=False, kind="stable")
    total = len(fields)
    fields = fields.head(20)
    filled = len(data) - fields["Missing"].to_numpy()
    percentages = 100 * filled / len(data)
    positions = list(range(len(fields)))
    figure = go.Figure(go.Bar(
        x=percentages, y=positions, orientation="h",
        marker_color=CHART_COLOR, width=0.62,
        text=[f"{value:.1f}%" for value in percentages],
        textposition="outside", cliponaxis=False,
        customdata=list(zip(fields["Column"].map(_plot_label), filled, fields["Missing"])),
        hovertemplate="%{customdata[0]}<br>"
            + _plot_label(translate("Filled cells")) + ": %{customdata[1]:,} (%{x:.2f}%)<br>"
            + _plot_label(translate("Missing")) + ": %{customdata[2]:,}<extra></extra>",
    ))
    _chart_style(figure, translate("Filled cells (%)"), "", height=max(290, 100 + 32 * len(fields)))
    figure.update_yaxes(
        tickmode="array", tickvals=positions,
        ticktext=fields["Column"].map(_short_label).tolist(),
        autorange="reversed", showgrid=False,
    )
    figure.update_xaxes(range=[0, 112], tickvals=[0, 25, 50, 75, 100], ticksuffix="%", showgrid=True, gridcolor="#E1EAE8")
    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)
    st.caption(translate("Showing {0} of {1} unprotected fields, least complete first. Full-file counts; exact missing counts are in the field table below.").format(len(fields), total))


def render_data_insights(data, column_profile, numeric_columns, date_columns,
                         active_dataset, column_signature, parser, sensitive_columns=()):
    st.markdown(
        '<div class="dashboard-intro"><strong>See the bigger picture</strong>'
        '<span>Explore the shape, distributions, common values, and timeline of your active file.</span></div>',
        unsafe_allow_html=True,
    )
    sampled = len(data) > SAMPLE_LIMIT
    sample_count = min(len(data), SAMPLE_LIMIT)
    scope = (
        translate("Based on {0} evenly spaced rows from {1}; exploratory sample, not a random sample.").format(f"{sample_count:,}", f"{len(data):,}")
        if sampled else translate("Based on all {0} rows.").format(f"{len(data):,}")
    )
    st.caption(translate("Snapshot and numeric views use the complete file.") + " "
        + (translate("Categories and dates use an evenly spaced sample of up to 100,000 rows.") + " " if sampled else "")
        + translate("Quality checks still inspect the complete file."))
    snapshot, numbers, categories, dates, relationships = st.tabs(
        ["Snapshot", "Numeric", "Categories", "Dates", "Relationships"],
        key=f"insight_views_{column_signature}", on_change="rerun",
    )
    cache = st.session_state.setdefault("data_insights_cache", {})
    columns = list(data.columns)

    with snapshot:
        if snapshot.open:
            total_cells = len(data) * len(columns)
            missing_cells = int(column_profile["Missing"].sum())
            complete = 100 * (1 - missing_cells / max(total_cells, 1))
            metrics = st.columns(4)
            metrics[0].metric("Rows", f"{len(data):,}")
            metrics[1].metric("Columns", f"{len(columns):,}")
            metrics[2].metric("Filled cells", f"{complete:.1f}%")
            metrics[3].metric("Numeric columns", f"{len(numeric_columns):,}")
            _completeness_chart(data, column_profile, sensitive_columns)
            st.subheader("Your fields at a glance")
            st.caption("Detected types are suggestions. Change them in inspection settings if needed.")
            st.dataframe(display_profile(column_profile), width="stretch", hide_index=True)
            st.subheader("A look at the data")
            st.caption("The first 10 rows of the active file.")
            st.dataframe(mask_dataframe(data.head(10), sensitive_columns), width="stretch", hide_index=True)

    with numbers:
        if numbers.open:
            options = [column for column in columns if column in numeric_columns and column not in sensitive_columns]
            if not options:
                st.info("No numeric columns were detected. You can select numeric columns in settings.")
            else:
                selected = st.selectbox("Numeric column", options, key=f"insight_numeric_{column_signature}")
                key = (active_dataset, column_signature, "numeric", repr(selected))
                if key not in cache:
                    with st.spinner("Calculating the numeric summary across the complete file..."):
                        cache[key] = numeric_summary(data[selected], parser)
                summary = cache[key]
                if not summary["count"]:
                    st.info("This column has no finite numeric values to analyze.")
                else:
                    st.caption(f"Based on all {summary['count']:,} finite numeric values; missing and nonnumeric values are excluded.")
                    metrics = st.columns(4)
                    metrics[0].metric("Mean", f"{summary['mean']:,.2f}")
                    metrics[1].metric("Median", f"{summary['median']:,.2f}")
                    metrics[2].metric("Minimum", f"{summary['minimum']:,.2f}")
                    metrics[3].metric("Maximum", f"{summary['maximum']:,.2f}")
                    st.subheader("Distribution")
                    edges, counts = summary["edges"], summary["counts"]
                    figure = go.Figure(go.Bar(
                        x=(edges[:-1] + edges[1:]) / 2, y=counts, width=np.diff(edges),
                        customdata=np.column_stack((edges[:-1], edges[1:])),
                        marker_color=CHART_COLOR,
                        hovertemplate=translate("Range") + ": %{customdata[0]:,.2f} – %{customdata[1]:,.2f}<br>" + translate("Rows") + ": %{y:,}<extra></extra>",
                    ))
                    _chart_style(figure, _plot_label(selected), translate("Rows"))
                    figure.update_layout(bargap=0.04)
                    figure.update_traces(marker_line=dict(color="#3C7686", width=0.5))
                    figure.update_xaxes(tickformat="~s")
                    figure.update_yaxes(rangemode="tozero", tickformat="~s")
                    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)
                    st.caption("Values are grouped into 40 ranges.")

    with categories:
        if categories.open:
            safe_columns = [column for column in columns if column not in sensitive_columns]
            if not safe_columns:
                st.info("There are no unprotected columns to explore.")
            else:
                selected = st.selectbox("Column to explore", safe_columns, key=f"insight_category_{column_signature}")
                key = (active_dataset, column_signature, "category", repr(selected))
                if key not in cache:
                    with st.spinner("Finding the most common values..."):
                        sample, _ = insight_sample(data[selected])
                        cache[key] = category_counts(sample)
                counts = cache[key]
                if counts.empty:
                    st.info("This column has no non-empty values in the rows analyzed.")
                else:
                    st.subheader("Most common values")
                    st.caption(translate("Top 10 non-empty values.") + " " + scope)
                    chart_data = counts.copy()
                    # Numeric positions keep distinct values distinct even when labels truncate.
                    chart_data["Position"] = np.arange(len(chart_data))
                    chart_data["Safe value"] = chart_data["Value"].map(_plot_label)
                    figure = px.bar(
                        chart_data, x="Rows", y="Position", orientation="h", text="Rows",
                        custom_data=["Safe value"], color_discrete_sequence=[CHART_COLOR],
                    )
                    figure.update_traces(
                        textposition="outside", texttemplate="%{x:,}", cliponaxis=False, width=0.62,
                        hovertemplate="%{customdata[0]}<br>%{x:,} " + translate("rows") + "<extra></extra>",
                    )
                    _chart_style(figure, translate("Rows"), "", height=max(310, 110 + 34 * len(chart_data)))
                    figure.update_yaxes(
                        autorange="reversed", showgrid=False, tickmode="array",
                        tickvals=chart_data["Position"].tolist(),
                        ticktext=chart_data["Value"].map(_short_label).tolist(),
                    )
                    figure.update_xaxes(range=[0, counts["Rows"].max() * 1.2], tickformat="~s", showgrid=True, gridcolor="#E1EAE8")
                    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)
                    st.caption("Bar lengths show row counts, not percentages. Long labels are shortened; hover or open exact values for the full text.")
                    with st.expander("See exact values"):
                        st.dataframe(counts.rename(columns=translate), width="stretch", hide_index=True)

    with dates:
        if dates.open:
            options = [column for column in columns if column in date_columns and column not in sensitive_columns]
            if not options:
                st.info("No date columns were detected. You can select date columns in settings.")
            else:
                selected = st.selectbox("Date column", options, key=f"insight_date_{column_signature}")
                key = (active_dataset, column_signature, "date", repr(selected))
                if key not in cache:
                    with st.spinner("Preparing the timeline..."):
                        sample, _ = insight_sample(data[selected])
                        cache[key] = date_counts(sample)
                counts, valid = cache[key]
                if counts.empty:
                    st.info("No parseable dates were found in the rows analyzed.")
                else:
                    st.subheader("Records over time")
                    st.caption(translate("{0} parseable values grouped by UTC month; invalid and missing dates are excluded.").format(f"{valid:,}")
                        + " " + translate("Ambiguous dates are interpreted month-first.") + " " + scope)
                    figure = px.bar(counts, x="Month", y="Rows", color_discrete_sequence=[CHART_COLOR])
                    figure.update_traces(hovertemplate="%{x|%Y-%m}<br>%{y:,} " + translate("rows") + "<extra></extra>")
                    _chart_style(figure, translate("Month"), translate("Rows"))
                    # Set calendar-aware widths so sparse observations never look continuous.
                    month_widths = counts["Month"].dt.days_in_month.astype("float64") * 86_400_000 * 0.76
                    figure.update_traces(width=month_widths)
                    figure.update_xaxes(type="date", tickformat="%b\n%Y", nticks=8)
                    figure.update_yaxes(rangemode="tozero", tickformat="~s")
                    st.plotly_chart(figure, width="stretch", config=CHART_CONFIG)
                    st.caption("Only months with parseable records are shown. Gaps are not interpolated.")

    with relationships:
        if relationships.open:
            options = [column for column in columns if column in numeric_columns and column not in sensitive_columns]
            if len(options) < 2:
                st.info("Choose at least two numeric columns in settings to explore a relationship.")
            else:
                first_col, second_col = st.columns(2)
                with first_col:
                    first = st.selectbox("First numeric column", options, key=f"insight_x_{column_signature}")
                available = [column for column in options if column != first]
                with second_col:
                    second = st.selectbox("Second numeric column", available, key=f"insight_y_{column_signature}")
                key = (active_dataset, column_signature, "relationship", repr(first), repr(second))
                if key not in cache:
                    with st.spinner("Comparing numeric columns..."):
                        cache[key] = numeric_relationship(data, first, second, parser)
                result = cache[key]
                if result["pairs"] < 2:
                    st.info("At least two rows with valid values in both columns are needed.")
                else:
                    st.subheader("How these columns move together")
                    correlation = result["correlation"]
                    if pd.isna(correlation):
                        st.info("Correlation is unavailable when either column has no variation.")
                    else:
                        st.metric("Pearson correlation", f"{correlation:.2f}")
                        st.caption("Correlation describes association, not causation.")
                    st.caption(translate("{0} valid pairs.").format(f"{result['pairs']:,}") + " " + scope + " "
                        + (translate("The chart shows {0} evenly spaced pairs.").format(f"{len(result['points']):,}") if result["points_sampled"] else translate("The chart shows all valid pairs.")))
                    figure = px.scatter(
                        result["points"], x="X", y="Y", color_discrete_sequence=[CHART_COLOR],
                    )
                    figure.update_traces(
                        marker=dict(size=6, opacity=0.65, line=dict(width=0.4, color="#3C7686")),
                        hovertemplate=f"{_plot_label(first)}: %{{x:,.6g}}<br>{_plot_label(second)}: %{{y:,.6g}}<extra></extra>",
                    )
                    st.plotly_chart(
                        _chart_style(figure, _plot_label(first), _plot_label(second)),
                        width="stretch", config=CHART_CONFIG,
                    )
