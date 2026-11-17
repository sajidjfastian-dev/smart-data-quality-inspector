"""Interactive, dataset-driven analysis views for the active workspace file."""
from datetime import date, datetime

import numpy as np
import pandas as pd
from security_guardrails import mask_dataframe
import plotly.express as px
import plotly.graph_objects as go
from localization import st


SAMPLE_LIMIT = 100_000
CHART_COLOR = "#61A9BD"


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


def _chart_style(figure, x_title, y_title):
    figure.update_layout(
        template="plotly_white",
        xaxis_title=x_title,
        yaxis_title=y_title,
        margin=dict(l=12, r=24, t=16, b=28),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#526c68"),
        showlegend=False,
    )
    return figure


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
        f"Based on {sample_count:,} evenly spaced rows from {len(data):,}; exploratory sample, not a random sample."
        if sampled else f"Based on all {len(data):,} rows."
    )
    st.caption(
        "Snapshot and numeric views use the complete file. "
        + ("Categories and dates use an evenly spaced sample of up to 100,000 rows. " if sampled else "")
        + "Quality checks still inspect the complete file."
    )
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
            st.subheader("Your fields at a glance")
            st.caption("Detected types are suggestions. Change them in inspection settings if needed.")
            st.dataframe(column_profile, width="stretch", hide_index=True)
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
                        hovertemplate="Range: %{customdata[0]:,.2f} – %{customdata[1]:,.2f}<br>Rows: %{y:,}<extra></extra>",
                    ))
                    st.plotly_chart(_chart_style(figure, str(selected), "Rows"), width="stretch", config={"displayModeBar": False})
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
                    st.caption("Top 10 non-empty values. " + scope)
                    chart_data = counts.copy()
                    chart_data["Label"] = chart_data["Value"].map(
                        lambda value: value if len(value) <= 45 else value[:42] + "…"
                    )
                    figure = px.bar(
                        chart_data, x="Rows", y="Label", orientation="h", text="Rows",
                        custom_data=["Value"], color_discrete_sequence=[CHART_COLOR],
                    )
                    figure.update_traces(
                        textposition="outside", cliponaxis=False,
                        hovertemplate="%{customdata[0]}<br>%{x:,} rows<extra></extra>",
                    )
                    figure.update_yaxes(autorange="reversed", automargin=True)
                    figure.update_xaxes(rangemode="tozero")
                    st.plotly_chart(_chart_style(figure, "Rows", ""), width="stretch", config={"displayModeBar": False})
                    with st.expander("See exact values"):
                        st.dataframe(counts, width="stretch", hide_index=True)

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
                    st.caption(
                        f"{valid:,} parseable values grouped by UTC month; invalid and missing dates are excluded. "
                        "Ambiguous dates are interpreted month-first. " + scope
                    )
                    figure = px.bar(counts, x="Month", y="Rows", color_discrete_sequence=[CHART_COLOR])
                    figure.update_traces(hovertemplate="%{x|%b %Y}<br>%{y:,} rows<extra></extra>")
                    figure.update_xaxes(type="date")
                    figure.update_yaxes(rangemode="tozero")
                    st.plotly_chart(_chart_style(figure, "Month", "Rows"), width="stretch", config={"displayModeBar": False})

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
                    st.caption(
                        f"{result['pairs']:,} valid pairs. {scope} "
                        + (f"The chart shows {len(result['points']):,} evenly spaced pairs." if result["points_sampled"] else "The chart shows all valid pairs.")
                    )
                    figure = px.scatter(
                        result["points"], x="X", y="Y", color_discrete_sequence=[CHART_COLOR],
                    )
                    figure.update_traces(
                        marker=dict(size=7),
                        hovertemplate=f"{str(first)}: %{{x:,.3g}}<br>{str(second)}: %{{y:,.3g}}<extra></extra>",
                    )
                    st.plotly_chart(
                        _chart_style(figure, str(first), str(second)),
                        width="stretch", config={"displayModeBar": False},
                    )
