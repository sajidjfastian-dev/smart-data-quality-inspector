import hashlib
import re
from datetime import date, datetime
from io import BytesIO, StringIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


st.set_page_config(
    page_title="Smart Data Quality Inspector",
    page_icon="📊",
    layout="wide",
)

EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)
DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%b %d, %Y",
    "%B %d, %Y",
)
DATE_SHAPES = (
    (re.compile(r"^\d{4}-\d{1,2}-\d{1,2}(?:\s+.*)?$"), "YYYY-MM-DD"),
    (re.compile(r"^\d{4}/\d{1,2}/\d{1,2}(?:\s+.*)?$"), "YYYY/MM/DD"),
    (re.compile(r"^\d{1,2}/\d{1,2}/\d{4}(?:\s+.*)?$"), "slash date"),
    (re.compile(r"^\d{1,2}-\d{1,2}-\d{4}(?:\s+.*)?$"), "hyphen date"),
    (re.compile(r"^[A-Za-z]+\s+\d{1,2},\s*\d{4}$"), "month name"),
)
ISSUE_COLUMNS = [
    "Row Number",
    "Column Name",
    "Issue Type",
    "Current Value",
    "Suggested Fix",
]
CHART_COLORS = ["#087e83", "#41a69b", "#94c9ae", "#f0b565", "#eb8b71", "#917ac6"]
SAMPLE_DATA_DIR = Path(__file__).resolve().parent / "sample_data"
CONNECTED_SAMPLE_FILES = (
    "customers.csv",
    "orders.xlsx",
    "products.csv",
    "support_tickets.xlsx",
    "web_events.csv",
)
SAMPLE_RELATIONSHIPS = pd.DataFrame(
    [
        ("customers.csv", "customer_id", "orders.xlsx", "customer_id"),
        ("products.csv", "product_id", "orders.xlsx", "product_id"),
        ("customers.csv", "customer_id", "support_tickets.xlsx", "customer_id"),
        ("orders.xlsx", "order_id", "support_tickets.xlsx", "order_id"),
        ("customers.csv", "customer_id", "web_events.csv", "customer_id"),
        ("products.csv", "product_id", "web_events.csv", "product_id"),
    ],
    columns=["Source file", "Source key", "Related file", "Related key"],
)


def make_sample_data():
    rng = np.random.default_rng(42)
    row_count = 50
    data = pd.DataFrame(
        {
            "customer_id": np.arange(1001, 1001 + row_count),
            "name": [f"Customer {number:02d}" for number in range(1, row_count + 1)],
            "email": [f"customer{number:02d}@example.com" for number in range(1, row_count + 1)],
            "signup_date": [
                (date(2024, 1, 1) + pd.Timedelta(days=int(offset))).strftime("%Y-%m-%d")
                for offset in rng.integers(0, 300, size=row_count)
            ],
            "age": rng.integers(19, 71, size=row_count),
            "annual_spend": np.round(rng.normal(2400, 650, size=row_count), 2),
            "region": rng.choice(["North", "South", "East", "West"], size=row_count),
            "is_active": rng.choice([True, False], size=row_count, p=[0.78, 0.22]),
        }
    )
    data.loc[3, "email"] = "not-an-email"
    data.loc[8, "email"] = "missing.domain@"
    data.loc[12, "signup_date"] = "03/18/2024"
    data.loc[19, "signup_date"] = "not-a-date"
    data.loc[7, "name"] = None
    data.loc[15, "annual_spend"] = np.nan
    data.loc[24, "email"] = ""
    data.loc[32, "name"] = "   "
    data.loc[38, "annual_spend"] = 25000
    data.loc[49] = data.loc[4]
    return data


def is_missing(value):
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def display_value(value):
    if is_missing(value):
        return "(empty)"
    return str(value)


def parse_date(value):
    if isinstance(value, (pd.Timestamp, datetime, date, np.datetime64)):
        return True
    if not isinstance(value, str):
        return False
    candidate = value.strip()
    if not candidate:
        return True
    for date_format in DATE_FORMATS:
        try:
            datetime.strptime(candidate, date_format)
            return True
        except ValueError:
            continue
    return False


def date_shape(value):
    for pattern, shape in DATE_SHAPES:
        if pattern.fullmatch(value.strip()):
            return shape
    return "other"


def parse_numeric_series(series):
    cleaned = series.map(
        lambda value: re.sub(r"[$£€¥,\s]", "", value).strip()
        if isinstance(value, str)
        else value
    )
    cleaned = cleaned.map(
        lambda value: f"-{value[1:-1]}"
        if isinstance(value, str) and value.startswith("(") and value.endswith(")")
        else value
    )
    return pd.to_numeric(cleaned, errors="coerce")


def infer_column_rules(data):
    email_columns = set()
    date_columns = set()
    numeric_columns = set()

    for column in data.columns:
        series = data[column]
        name = str(column).lower()
        values = [value for value in series if not is_missing(value)]
        if not values:
            continue

        if "email" in name:
            email_columns.add(column)
        elif (
            len(values) >= 2
            and sum(bool(EMAIL_PATTERN.fullmatch(str(value).strip())) for value in values)
            / len(values)
            >= 0.6
        ):
            email_columns.add(column)

        date_values = [
            value for value in values if isinstance(value, str) and value.strip()
        ]
        valid_dates = [value for value in date_values if parse_date(value)]
        is_date_named = any(token in name for token in ("date", "time", "timestamp"))
        if is_date_named or (
            len(date_values) >= 2 and len(valid_dates) / len(date_values) >= 0.7
        ):
            date_columns.add(column)

        if pd.api.types.is_bool_dtype(series):
            continue
        if pd.api.types.is_numeric_dtype(series):
            numeric_columns.add(column)
            continue
        parsed_numbers = parse_numeric_series(series)
        non_missing_numbers = parsed_numbers.dropna()
        if (
            len(non_missing_numbers) >= 2
            and len(non_missing_numbers) / len(values) >= 0.8
            and column not in date_columns
        ):
            numeric_columns.add(column)

    numeric_columns -= date_columns
    return email_columns, date_columns, numeric_columns


def build_column_profile(data, email_columns, date_columns, numeric_columns):
    profile = []
    for column in data.columns:
        series = data[column]
        missing_count = sum(is_missing(value) for value in series)
        detected_types = []
        if column in numeric_columns:
            detected_types.append("Numeric")
        if column in date_columns:
            detected_types.append("Date")
        if column in email_columns:
            detected_types.append("Email")
        if not detected_types:
            detected_types.append(
                "Boolean"
                if pd.api.types.is_bool_dtype(series)
                else "Text / category"
            )
        profile.append(
            {
                "Column": str(column),
                "Detected type": " · ".join(detected_types),
                "Storage type": str(series.dtype),
                "Missing": missing_count,
                "Missing %": round(missing_count / max(len(data), 1) * 100, 1),
                "Unique": int(series.nunique(dropna=True)),
            }
        )
    return pd.DataFrame(profile)


def scan_data(
    data,
    email_columns=None,
    date_columns=None,
    numeric_columns=None,
    iqr_multiplier=1.5,
):
    issues = []
    duplicate_mask = data.duplicated(keep="first")
    email_columns = (
        set(email_columns)
        if email_columns is not None
        else {column for column in data.columns if "email" in str(column).lower()}
    )
    date_columns = (
        set(date_columns)
        if date_columns is not None
        else {column for column in data.columns if "date" in str(column).lower()}
    )
    numeric_columns = (
        set(numeric_columns)
        if numeric_columns is not None
        else {
            column
            for column in data.columns
            if pd.api.types.is_numeric_dtype(data[column])
            and not pd.api.types.is_bool_dtype(data[column])
        }
    )

    def add_issue(row_number, column, issue_type, value, suggestion):
        issues.append(
            {
                "Row Number": row_number,
                "Column Name": column,
                "Issue Type": issue_type,
                "Current Value": display_value(value),
                "Suggested Fix": suggestion,
            }
        )

    for column in data.columns:
        series = data[column]
        for position, value in enumerate(series):
            if is_missing(value):
                add_issue(
                    position + 1,
                    column,
                    "Missing Value",
                    value,
                    "Provide a value or fill using an appropriate default.",
                )

        if column in email_columns:
            for position, value in enumerate(series):
                if is_missing(value):
                    continue
                if not EMAIL_PATTERN.fullmatch(str(value).strip()):
                    add_issue(
                        position + 1,
                        column,
                        "Invalid Email",
                        value,
                        "Correct the address to a valid name@domain format.",
                    )

        if column in date_columns:
            valid_string_shapes = []
            for value in series:
                if isinstance(value, str) and value.strip() and parse_date(value):
                    valid_string_shapes.append(date_shape(value))
            shape_counts = pd.Series(valid_string_shapes).value_counts()
            common_shape = shape_counts.index[0] if not shape_counts.empty else None

            for position, value in enumerate(series):
                if is_missing(value):
                    continue
                if not parse_date(value):
                    add_issue(
                        position + 1,
                        column,
                        "Invalid Date",
                        value,
                        "Replace with a valid date, such as YYYY-MM-DD.",
                    )
                elif (
                    isinstance(value, str)
                    and value.strip()
                    and common_shape is not None
                    and date_shape(value) != common_shape
                ):
                    add_issue(
                        position + 1,
                        column,
                        "Inconsistent Date Format",
                        value,
                        f"Standardize to the most common format ({common_shape}).",
                    )

        if column in numeric_columns:
            numeric_series = parse_numeric_series(series)
            finite_mask = np.isfinite(numeric_series.to_numpy(dtype=float, na_value=np.nan))
            numeric_values = numeric_series[finite_mask].dropna()
            if not numeric_values.empty:
                first_quartile = numeric_values.quantile(0.25)
                third_quartile = numeric_values.quantile(0.75)
                spread = third_quartile - first_quartile
                lower_bound = first_quartile - iqr_multiplier * spread
                upper_bound = third_quartile + iqr_multiplier * spread
                for position, value in enumerate(numeric_series):
                    if not np.isfinite(value):
                        continue
                    if value < lower_bound or value > upper_bound:
                        add_issue(
                            position + 1,
                            column,
                            "Numeric Outlier",
                            series.iloc[position],
                            "Review this value; confirm it or replace with a validated value.",
                        )

    for position in np.flatnonzero(duplicate_mask.to_numpy()):
        add_issue(
            int(position) + 1,
            "Entire row",
            "Duplicate Row",
            "Exact match to an earlier row",
            "Remove the duplicate row and keep the first occurrence.",
        )

    return pd.DataFrame(issues, columns=ISSUE_COLUMNS), int(duplicate_mask.sum())


def clean_data(
    data,
    numeric_columns=None,
    date_columns=None,
    drop_duplicates=True,
    trim_whitespace=True,
    fill_numeric_missing=True,
    standardize_dates=False,
):
    cleaned = data.copy()
    if drop_duplicates:
        cleaned = cleaned.drop_duplicates().reset_index(drop=True)
    if trim_whitespace:
        for column in cleaned.columns:
            if cleaned[column].dtype == object or pd.api.types.is_string_dtype(cleaned[column]):
                cleaned[column] = cleaned[column].map(
                    lambda value: value.strip() if isinstance(value, str) else value
                )
    if numeric_columns is None:
        numeric_columns = infer_column_rules(cleaned)[2]
    if fill_numeric_missing:
        for column in numeric_columns:
            if column not in cleaned.columns or pd.api.types.is_bool_dtype(cleaned[column]):
                continue
            numeric_values = parse_numeric_series(cleaned[column])
            median = numeric_values.median()
            if pd.isna(median):
                continue
            missing_mask = cleaned[column].map(is_missing)
            if pd.api.types.is_numeric_dtype(cleaned[column]):
                if pd.api.types.is_integer_dtype(cleaned[column]) and median % 1:
                    cleaned[column] = cleaned[column].astype("float64")
                cleaned[column] = cleaned[column].fillna(median)
            elif missing_mask.any():
                cleaned.loc[missing_mask, column] = str(median)
    if date_columns is None:
        date_columns = infer_column_rules(cleaned)[1]
    if standardize_dates:
        for column in date_columns:
            if column not in cleaned.columns:
                continue
            cleaned[column] = cleaned[column].map(standardize_date_value)
    return cleaned


def standardize_date_value(value):
    if not isinstance(value, str) or not value.strip():
        return value
    candidate = value.strip()
    for separator in ("/", "-"):
        ambiguous_date = re.fullmatch(
            rf"(\d{{1,2}}){re.escape(separator)}(\d{{1,2}}){re.escape(separator)}(\d{{4}})",
            candidate,
        )
        if ambiguous_date:
            first, second = int(ambiguous_date.group(1)), int(ambiguous_date.group(2))
            if first <= 12 and second <= 12 and first != second:
                return value
    for date_format in DATE_FORMATS:
        try:
            parsed = datetime.strptime(candidate, date_format)
        except ValueError:
            continue
        if "%H" in date_format:
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        return parsed.strftime("%Y-%m-%d")
    return value


def dataframe_styles(data, issues):
    styles = pd.DataFrame("", index=data.index, columns=data.columns)
    for issue in issues.itertuples(index=False):
        row_index = issue[0] - 1
        if row_index not in data.index:
            continue
        if issue[1] == "Entire row":
            styles.loc[row_index, :] = "background-color: #fff1ed; color: #8b3323;"
        elif issue[1] in styles.columns:
            styles.loc[row_index, issue[1]] = (
                "background-color: #fff0c2; color: #694600; font-weight: 600;"
            )
    return data.style.apply(lambda _: styles, axis=None)


def serialize_data_file(filename, data):
    original_suffix = Path(filename).suffix.lower()
    if original_suffix == ".xlsx":
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            data.to_excel(writer, index=False, sheet_name="Fixed data")
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        )
    return data.to_csv(index=False).encode("utf-8-sig"), "text/csv", ".csv"


def read_uploaded_file(uploaded_file):
    return read_data_file(uploaded_file.name, uploaded_file.getvalue())


def read_data_file(filename, content):
    if filename.lower().endswith(".csv"):
        return pd.read_csv(StringIO(content.decode("utf-8-sig")))
    return pd.read_excel(BytesIO(content), engine="openpyxl")


def upload_signature(uploaded_file):
    content = uploaded_file.getvalue()
    return uploaded_file.name, len(content), hashlib.sha256(content).hexdigest()


def load_sample_data():
    signatures = tuple(
        upload_signature(uploaded_file)
        for uploaded_file in st.session_state.get("data_upload", [])
    )
    st.session_state["inspector_datasets"] = {
        "Sample messy dataset": make_sample_data()
    }
    st.session_state["inspector_upload_signature"] = signatures
    st.session_state["active_dataset"] = "Sample messy dataset"
    st.session_state["fixed_datasets"] = {}


def load_connected_sample_data():
    signatures = tuple(
        upload_signature(uploaded_file)
        for uploaded_file in st.session_state.get("data_upload", [])
    )
    datasets = {}
    for filename in CONNECTED_SAMPLE_FILES:
        file_path = SAMPLE_DATA_DIR / filename
        with file_path.open("rb") as file_handle:
            content = file_handle.read()
        datasets[filename] = read_data_file(filename, content)
    st.session_state["inspector_datasets"] = datasets
    st.session_state["inspector_upload_signature"] = signatures
    st.session_state["active_dataset"] = CONNECTED_SAMPLE_FILES[0]
    st.session_state["fixed_datasets"] = {}


def connected_sample_archive():
    archive = BytesIO()
    with ZipFile(archive, mode="w") as zip_file:
        for filename in CONNECTED_SAMPLE_FILES:
            zip_file.write(SAMPLE_DATA_DIR / filename, arcname=filename)
    return archive.getvalue()


st.markdown(
    """
    <style>
    :root {
        --ink: #172b3a;
        --muted: #647789;
        --line: #e3eaf0;
        --teal: #087e83;
        --teal-dark: #09666d;
        --canvas: #f7f9fa;
        --panel: #ffffff;
    }
    .stApp, [data-testid="stAppViewContainer"] {background: var(--canvas);}
    [data-testid="stHeader"] {background: rgba(247, 249, 250, 0.88);}
    .block-container {padding-top: 2.25rem; padding-bottom: 3.5rem; max-width: 1480px;}
    h1, h2, h3, [data-testid="stMarkdownContainer"] p {color: var(--ink);}
    .brand-header {
        display: flex; align-items: center; gap: 18px; margin-bottom: 1.65rem;
        padding: 22px 26px; border: 1px solid #e6edf0; border-radius: 22px;
        background:
            radial-gradient(ellipse at 92% 10%, rgba(201, 233, 228, .42), transparent 34%),
            linear-gradient(120deg, #fff 0%, #fbfdfd 68%, #f1f8f6 100%);
        box-shadow: 0 8px 28px rgba(27, 57, 70, .045);
    }
    .brand-logo {width: 58px; height: 58px; flex: 0 0 58px;}
    .brand-eyebrow {
        color: var(--teal); font-size: .72rem; font-weight: 750;
        letter-spacing: .16em; text-transform: uppercase; margin-bottom: 5px;
    }
    .brand-title {
        color: var(--ink); font-size: clamp(1.55rem, 3vw, 2rem);
        line-height: 1.15; font-weight: 760; letter-spacing: -.045em;
    }
    .brand-subtitle {color: var(--muted); font-size: .97rem; margin-top: 6px;}
    .sidebar-brand {
        display: flex; align-items: center; gap: 12px;
        padding: 5px 0 18px; margin-bottom: 8px;
        border-bottom: 1px solid var(--line);
    }
    .sidebar-brand .brand-logo {width: 42px; height: 42px; flex-basis: 42px;}
    .sidebar-brand-title {color: var(--ink); font-size: 1.03rem; font-weight: 730;}
    .sidebar-brand-caption {
        color: var(--muted); font-size: .72rem; margin-top: 2px;
        letter-spacing: .045em; text-transform: uppercase;
    }
    section[data-testid="stSidebar"] {
        background: #f1f5f6; border-right: 1px solid var(--line);
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: var(--muted);
    }
    [data-testid="stMetric"] {
        background: var(--panel); border: 1px solid var(--line);
        padding: 19px 21px; border-radius: 17px;
        box-shadow: 0 5px 18px rgba(27, 57, 70, .045);
    }
    [data-testid="stMetricLabel"] {color: var(--muted); font-size: .88rem;}
    [data-testid="stMetricValue"] {color: var(--ink); font-weight: 730;}
    .st-key-metric_cards [data-testid="stButton"] button {
        min-height: 8rem; height: 100%; padding: 18px 20px;
        color: var(--ink); background: var(--panel); border: 1px solid var(--line);
        border-radius: 17px; box-shadow: 0 5px 18px rgba(27, 57, 70, .045);
        text-align: left; white-space: pre-line;
    }
    .st-key-metric_cards [data-testid="stButton"] button p {
        color: var(--ink); text-align: left; line-height: 1.6;
    }
    .st-key-metric_cards [data-testid="stButton"] button:hover {
        color: var(--teal-dark); background: #f5fbfa; border-color: var(--teal);
        box-shadow: 0 8px 24px rgba(8, 126, 131, .11); transform: translateY(-2px);
    }
    .st-key-metric_cards [data-testid="stButton"] button:focus:not(:active) {
        border-color: var(--teal); color: var(--teal-dark);
    }
    .section-heading {
        display: flex; align-items: end; justify-content: space-between;
        gap: 1rem; margin: .4rem 0 1rem;
    }
    .section-heading h2 {margin: 0; font-size: 1.35rem; letter-spacing: -.025em;}
    .section-caption {color: var(--muted); font-size: .88rem; margin-top: .25rem;}
    .workflow-strip {
        display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
        margin: 0 0 1.15rem; padding: 12px 16px;
        background: #f0f7f6; border: 1px solid #dcebe8; border-radius: 14px;
    }
    .workflow-step {
        display: inline-flex; align-items: center; gap: 8px;
        color: #536b75; font-size: .8rem; font-weight: 650;
    }
    .workflow-step strong {
        display: grid; place-items: center; width: 23px; height: 23px;
        border-radius: 50%; background: #dcebe8; color: #355d61;
        font-size: .72rem;
    }
    .workflow-step-active {color: var(--teal-dark);}
    .workflow-step-active strong {background: var(--teal); color: #fff;}
    .workflow-step-complete strong {background: #d3eee2; color: #246548;}
    .workflow-divider {color: #9aadb3; font-size: .82rem;}
    .st-key-active_dataset [data-baseweb="select"] {
        border-radius: 11px; background: #fff;
    }
    [data-testid="stDataFrame"] {background: #fff;}
    [data-testid="stDataFrame"] [role="grid"] {font-variant-numeric: tabular-nums;}
    [data-testid="stAlert"] {border-radius: 12px;}
    .st-key-batch_overview [data-testid="stMetric"] {
        background: linear-gradient(140deg, #fff, #f0f8f6);
    }
    [data-testid="stFileUploaderDropzone"] {
        min-height: 9rem; border: 1.5px dashed #91b9b8 !important;
        border-radius: 17px !important; background: rgba(255,255,255,.82) !important;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: var(--teal) !important; background: #f0faf8 !important;
    }
    [data-testid="stProgressBar"] > div > div {background: var(--teal);}
    [data-testid="stTabs"] [role="tablist"] {
        gap: 7px; border-bottom: 1px solid var(--line);
    }
    [data-testid="stTabs"] button[role="tab"] {
        color: var(--muted); font-weight: 620; border-radius: 10px 10px 0 0;
    }
    [data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: var(--teal-dark); border-bottom-color: var(--teal);
    }
    .stButton > button, .stDownloadButton > button {
        min-height: 2.7rem; border-radius: 11px; font-weight: 650;
        border-color: #cfdddd; transition: all .16s ease;
    }
    .stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
        color: white; background: var(--teal); border-color: var(--teal);
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        color: var(--teal-dark); border-color: var(--teal);
        transform: translateY(-1px);
    }
    [data-testid="stFileUploader"] section {
        border-radius: 13px; border-color: #cfdddd; background: rgba(255,255,255,.72);
    }
    [data-testid="stExpander"] {
        border-color: var(--line); border-radius: 13px; background: rgba(255,255,255,.62);
    }
    [data-testid="stDataFrame"] {
        border: 1px solid var(--line); border-radius: 13px; overflow: hidden;
    }
    @media (max-width: 760px) {
        .block-container {padding: 1.15rem 1rem 2rem;}
        .brand-header {padding: 18px 16px; gap: 12px; border-radius: 17px;}
        .brand-logo {width: 46px; height: 46px; flex-basis: 46px;}
        .brand-subtitle {font-size: .86rem;}
        .st-key-metric_cards [data-testid="stButton"] button {
            min-height: 7rem; padding: 14px 12px;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def brand_logo(variant):
    gradient_id = f"brand-gradient-{variant}"
    return (
        f'<svg class="brand-logo" viewBox="0 0 64 64" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
        f'<defs><linearGradient id="{gradient_id}" x1="7" y1="5" x2="58" y2="59" '
        f'gradientUnits="userSpaceOnUse"><stop stop-color="#16A6A0"/>'
        f'<stop offset="1" stop-color="#075B68"/></linearGradient></defs>'
        f'<rect x="2" y="2" width="60" height="60" rx="19" fill="url(#{gradient_id})"/>'
        f'<path d="M17 43V33.5C17 32.67 17.67 32 18.5 32H23.5C24.33 32 25 32.67 '
        f'25 33.5V43" stroke="white" stroke-width="3.5" stroke-linecap="round"/>'
        f'<path d="M29.5 43V25.5C29.5 24.67 30.17 24 31 24H36C36.83 24 37.5 24.67 '
        f'37.5 25.5V43" stroke="white" stroke-width="3.5" stroke-linecap="round"/>'
        f'<path d="M17 48H37.5" stroke="white" stroke-width="3.5" stroke-linecap="round"/>'
        f'<circle cx="45" cy="42" r="10" fill="#D9F5E9" stroke="white" stroke-width="2.5"/>'
        f'<path d="M40.5 42L43.5 45L49.5 38.5" stroke="#087A69" stroke-width="2.8" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )

st.markdown(
    f'<div class="brand-header">{brand_logo("header")}<div>'
    f'<div class="brand-eyebrow">Data quality workspace</div>'
    f'<div class="brand-title">Smart Data Quality Inspector</div>'
    f'<div class="brand-subtitle">Bring your data. Find the signal. Make every row count.</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)
with st.sidebar:
    st.markdown(
        f'<div class="sidebar-brand">{brand_logo("sidebar")}<div>'
        f'<div class="sidebar-brand-title">Data Inspector</div>'
        f'<div class="sidebar-brand-caption">Quality workspace</div>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.caption("Your data quality command center")
    uploaded_files = st.file_uploader(
        "Drop your data files here",
        type=["csv", "xlsx"],
        accept_multiple_files=True,
        help="Drop or browse multiple CSV and XLSX files. Analyze each file independently.",
        key="data_upload",
    )
    st.button(
        "Explore with 50-row quick sample",
        width="stretch",
        on_click=load_sample_data,
        type="secondary",
    )
    st.button(
        "Load connected big-data sample",
        width="stretch",
        on_click=load_connected_sample_data,
        type="primary",
        help="Load five related CSV/XLSX demo tables with over 50,000 synthetic rows.",
    )
    st.download_button(
        "Download 5-file sample pack",
        data=connected_sample_archive(),
        file_name="smart_data_quality_sample_pack.zip",
        mime="application/zip",
        width="stretch",
    )
    st.caption("Synthetic test data · CSV and Excel · Session-only processing")

uploaded_files = uploaded_files or []
upload_signatures = tuple(upload_signature(file) for file in uploaded_files)
datasets = st.session_state.get("inspector_datasets", {})
if uploaded_files and upload_signatures != st.session_state.get(
    "inspector_upload_signature"
):
    loaded_datasets = {}
    file_errors = []
    filename_counts = {}
    with st.spinner(f"Reading and profiling {len(uploaded_files)} file(s)..."):
        progress = st.progress(0.0, text="Preparing file batch...")
        for index, uploaded_file in enumerate(uploaded_files):
            filename_counts[uploaded_file.name] = filename_counts.get(uploaded_file.name, 0) + 1
            occurrence = filename_counts[uploaded_file.name]
            dataset_label = (
                uploaded_file.name
                if occurrence == 1
                else f"{uploaded_file.name} ({occurrence})"
            )
            progress.progress(
                index / len(uploaded_files),
                text=f"Reading {uploaded_file.name} ({index + 1} of {len(uploaded_files)})...",
            )
            try:
                file_data = read_uploaded_file(uploaded_file)
                if file_data.empty or len(file_data.columns) == 0:
                    file_errors.append(f"{uploaded_file.name}: the file has no rows or columns.")
                    continue
                loaded_datasets[dataset_label] = file_data
            except (
                BadZipFile,
                UnicodeDecodeError,
                pd.errors.EmptyDataError,
                pd.errors.ParserError,
                ValueError,
                OSError,
            ) as error:
                file_errors.append(f"{uploaded_file.name}: {error}")
            except ImportError as error:
                file_errors.append(
                    f"{uploaded_file.name}: a required file-reading dependency is unavailable ({error})."
                )
        progress.progress(1.0, text="File batch ready.")
        progress.empty()

    if loaded_datasets:
        datasets = loaded_datasets
        st.session_state["inspector_datasets"] = datasets
        st.session_state["inspector_upload_signature"] = upload_signatures
        st.session_state["active_dataset"] = next(iter(datasets))
        st.session_state["fixed_datasets"] = {}
    for file_error in file_errors:
        st.warning(file_error)
    if not loaded_datasets:
        st.error("No files could be analyzed. Check the file format and try again.")
        st.stop()

if not datasets:
    st.markdown("### Your data deserves a closer look.")
    st.markdown(
        "Drag and drop **one or more CSV or Excel files** in the sidebar, "
        "or load the sample to explore the inspector."
    )
    st.info(
        "Profile missingness, duplicates, contact and date formats, numeric distributions, "
        "and statistical outliers. Your files stay in this browser session."
    )
    st.stop()

st.markdown(
    '<div class="workflow-strip" aria-label="Workspace workflow">'
    '<span class="workflow-step workflow-step-complete"><strong>✓</strong> Load data</span>'
    '<span class="workflow-divider">›</span>'
    '<span class="workflow-step workflow-step-active"><strong>2</strong> Inspect quality</span>'
    '<span class="workflow-divider">›</span>'
    '<span class="workflow-step"><strong>3</strong> Review &amp; fix</span>'
    '<span class="workflow-divider">›</span>'
    '<span class="workflow-step"><strong>4</strong> Export</span>'
    '</div>',
    unsafe_allow_html=True,
)

with st.container(border=True):
    workspace_file_col, workspace_guidance_col = st.columns([1.1, 2])
    with workspace_file_col:
        st.markdown("**Current workspace**")
        active_dataset = st.selectbox(
            "Active file",
            options=list(datasets),
            key="active_dataset",
            help="Choose a file in the workspace to inspect its data quality.",
        )
    with workspace_guidance_col:
        st.markdown("**Inspect one file at a time**")
        st.caption(
            "Choose a file to refresh its quality score, issue log, row review, "
            "and exports. Workspace files remain available in this list."
        )

data = datasets[active_dataset]
columns = list(data.columns)
column_signature = hashlib.sha256(
    (
        active_dataset
        + "\0"
        + "\0".join(
            f"{column}:{data[column].dtype}" for column in columns
        )
    ).encode("utf-8")
).hexdigest()[:12]
email_defaults, date_defaults, numeric_defaults = infer_column_rules(data)

with st.sidebar:
    with st.expander("Column Rules", expanded=False):
        email_columns = st.multiselect(
            "Treat columns as Email",
            options=columns,
            default=email_defaults,
            key=f"rule_email_columns_{column_signature}",
            help="Selected columns are checked for valid email addresses.",
        )
        date_columns = st.multiselect(
            "Treat columns as Date",
            options=columns,
            default=date_defaults,
            key=f"rule_date_columns_{column_signature}",
            help="Selected columns are checked for valid and consistent date formats.",
        )
        numeric_columns = st.multiselect(
            "Treat columns as Numeric",
            options=columns,
            default=numeric_defaults,
            key=f"rule_numeric_columns_{column_signature}",
            help="Selected columns are checked for outliers; numeric text values are parsed when possible.",
        )
        iqr_multiplier = st.slider(
            "IQR outlier multiplier",
            min_value=1.5,
            max_value=3.0,
            value=1.5,
            step=0.1,
            format="%.1f×",
            help="Values outside Q1 − multiplier × IQR or Q3 + multiplier × IQR are flagged.",
        )
    st.divider()
    st.caption("Checks include missing values, exact duplicates, email/date formats, and numeric outliers.")

issues, duplicate_count = scan_data(
    data,
    email_columns=email_columns,
    date_columns=date_columns,
    numeric_columns=numeric_columns,
    iqr_multiplier=iqr_multiplier,
)
issue_count = len(issues)
health_score = max(0, round(100 * (1 - issue_count / max(data.shape[0] * data.shape[1], 1))))
column_profile = build_column_profile(
    data,
    email_columns,
    date_columns,
    numeric_columns,
)
batch_row_count = sum(len(frame) for frame in datasets.values())
quality_label = (
    "Excellent" if health_score >= 95
    else "Good" if health_score >= 85
    else "Needs attention" if health_score >= 70
    else "Review recommended"
)

st.markdown(
    f'<div class="section-heading"><div><h2>Workspace overview</h2>'
    f'<div class="section-caption">A live snapshot of {len(datasets)} dataset(s) in this batch.</div>'
    f'</div></div>',
    unsafe_allow_html=True,
)
with st.container(key="batch_overview"):
    batch_columns = st.columns(4)
    batch_columns[0].metric("Files in workspace", f"{len(datasets):,}")
    batch_columns[1].metric("Rows across files", f"{batch_row_count:,}")
    batch_columns[2].metric("Active file size", f"{len(data):,} rows · {len(columns):,} columns")
    batch_columns[3].metric("Current data health", quality_label, f"{health_score}%")

st.caption(
    f"Analyzing **{active_dataset}** · {data.shape[0]:,} rows · "
    f"{data.shape[1]:,} columns · {int(data.memory_usage(deep=True).sum() / 1024):,} KB in memory"
)
if set(CONNECTED_SAMPLE_FILES).issubset(datasets):
    with st.expander("How the sample files connect"):
        st.caption(
            "The synthetic tables share customer, product, and order IDs, so you can "
            "test related datasets together or inspect each file independently."
        )
        st.dataframe(SAMPLE_RELATIONSHIPS, width="stretch", hide_index=True)

metric_cards = [
    ("health", "Data Health Score", f"{health_score}%", "How the quality score is calculated"),
    ("rows", "Total Rows", f"{len(data):,}", "Dataset size and duplicate-row summary"),
    ("issues", "Total Issues Found", f"{issue_count:,}", "Breakdown of detected issues"),
    ("duplicates", "Duplicate Rows", f"{duplicate_count:,}", "Exact duplicate row details"),
]
with st.container(key="metric_cards"):
    metric_columns = st.columns(4)
    for metric_column, (metric_key, label, value, description) in zip(
        metric_columns, metric_cards
    ):
        with metric_column:
            if st.button(
                f"**{label}**\n\n**{value}**\n\nClick to explore",
                key=f"metric_card_{metric_key}",
                help=description,
                width="stretch",
            ):
                st.session_state["selected_metric_detail"] = metric_key

selected_metric = st.session_state.get("selected_metric_detail")
if selected_metric:
    selected_label = next(
        label for key, label, _, _ in metric_cards if key == selected_metric
    )
    with st.container(border=True):
        st.subheader(f"{selected_label} details")
        if selected_metric == "health":
            flagged_cells = issue_count
            total_cells = data.shape[0] * data.shape[1]
            st.markdown(
                f"The **{health_score}%** score is calculated as "
                f"`max(0, round(100 × (1 − {flagged_cells} ÷ {total_cells})))`. "
                f"There are **{flagged_cells:,} flagged findings** across "
                f"**{total_cells:,} cells** ({data.shape[0]:,} rows × {data.shape[1]:,} columns)."
            )
            if issues.empty:
                st.success("No quality issues are currently detected.")
            else:
                st.caption("Findings contributing to the score:")
                st.dataframe(
                    issues.groupby("Issue Type", as_index=False)
                    .size()
                    .rename(columns={"size": "Issue Count"})
                    .sort_values("Issue Count", ascending=False),
                    width="stretch",
                    hide_index=True,
                )
        elif selected_metric == "rows":
            unique_rows = len(data) - duplicate_count
            duplicate_percent = duplicate_count / len(data) * 100
            row_col, column_col, unique_col, duplicate_col = st.columns(4)
            row_col.metric("Rows in dataset", f"{len(data):,}")
            column_col.metric("Columns", f"{len(data.columns):,}")
            unique_col.metric("Rows after deduplication", f"{unique_rows:,}")
            duplicate_col.metric("Rows duplicated", f"{duplicate_percent:.1f}%")
            st.caption(
                "Row numbers in the issue log refer to the displayed data order, starting at 1."
            )
        elif selected_metric == "issues":
            if issues.empty:
                st.success("No issues are currently detected.")
            else:
                issue_type_counts = (
                    issues.groupby("Issue Type", as_index=False)
                    .size()
                    .rename(columns={"size": "Issue Count"})
                    .sort_values("Issue Count", ascending=False)
                )
                issue_column_counts = (
                    issues.groupby("Column Name", as_index=False)
                    .size()
                    .rename(columns={"size": "Issue Count"})
                    .sort_values("Issue Count", ascending=False)
                )
                type_column, field_column = st.columns(2)
                with type_column:
                    st.caption("Findings by issue type")
                    st.dataframe(issue_type_counts, width="stretch", hide_index=True)
                with field_column:
                    st.caption("Findings by column")
                    st.dataframe(issue_column_counts, width="stretch", hide_index=True)
                st.caption("Showing every detected issue:")
                st.dataframe(issues, width="stretch", hide_index=True)
        elif selected_metric == "duplicates":
            duplicate_mask = data.duplicated(keep="first").to_numpy()
            duplicate_positions = np.flatnonzero(duplicate_mask)
            if duplicate_count == 0:
                st.success("No exact duplicate rows are currently detected.")
            else:
                duplicate_rows = data.iloc[duplicate_positions].copy()
                duplicate_rows.insert(0, "Row Number", duplicate_positions + 1)
                st.markdown(
                    f"**{duplicate_count:,}** exact duplicate row(s) were found. "
                    "These rows match an earlier row across every column."
                )
                st.dataframe(duplicate_rows, width="stretch", hide_index=True)

overview_tab, issues_tab, review_tab, preview_tab = st.tabs(
    [
        "Overview Dashboard",
        "Issue Logs",
        "Data Quality Review",
        "Data Preview & Export",
    ]
)

with overview_tab:
    chart_col, type_col = st.columns([1.35, 1])
    with chart_col:
        st.subheader("Where should you look first?")
        if issues.empty:
            st.success("This dataset is looking healthy. No issues were found by the active checks.")
        else:
            issue_counts = (
                issues.groupby("Column Name", as_index=False)
                .size()
                .rename(columns={"size": "Issue Count"})
                .sort_values("Issue Count", ascending=False)
            )
            chart = px.bar(
                issue_counts,
                x="Column Name",
                y="Issue Count",
                color="Issue Count",
                color_continuous_scale=["#c5e8df", "#087e83", "#075b68"],
                text="Issue Count",
            )
            chart.update_layout(
                template="plotly_white",
                coloraxis_showscale=False,
                xaxis_title="",
                yaxis_title="Findings",
                margin=dict(l=12, r=12, t=15, b=20),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#344b5a"),
            )
            st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})

    with type_col:
        st.subheader("Quality findings")
        issue_types = set(issues["Issue Type"]) if not issues.empty else set()
        if issues.empty:
            st.caption("Findings will appear here after a check detects an issue.")
        else:
            type_counts = (
                issues.groupby("Issue Type", as_index=False)
                .size()
                .rename(columns={"size": "Findings"})
                .sort_values("Findings", ascending=False)
            )
            type_chart = px.pie(
                type_counts,
                names="Issue Type",
                values="Findings",
                hole=0.66,
                color_discrete_sequence=CHART_COLORS,
            )
            type_chart.update_traces(
                textposition="inside",
                textinfo="percent",
                hovertemplate="%{label}<br>%{value} findings<extra></extra>",
            )
            type_chart.update_layout(
                template="plotly_white",
                showlegend=True,
                legend=dict(orientation="h", y=-0.16, x=0),
                margin=dict(l=8, r=8, t=12, b=38),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#344b5a"),
            )
            st.plotly_chart(type_chart, width="stretch", config={"displayModeBar": False})
            type_counts = type_counts.rename(columns={"Findings": "Issue Count"})
            st.dataframe(type_counts, width="stretch", hide_index=True)

    st.divider()
    missing_col, recommendations_col = st.columns([1.3, 1])
    with missing_col:
        st.subheader("Completeness by column")
        missing_profile = column_profile.sort_values("Missing %", ascending=False)
        if int(missing_profile["Missing"].sum()) == 0:
            st.success("Every column is complete under the current missing-value check.")
        else:
            missing_chart = px.bar(
                missing_profile,
                x="Missing %",
                y="Column",
                orientation="h",
                color="Missing %",
                color_continuous_scale=["#c5e8df", "#e7b565", "#dc755c"],
                text="Missing %",
                hover_data={"Missing": True, "Unique": True},
            )
            missing_chart.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
            missing_chart.update_layout(
                template="plotly_white",
                coloraxis_showscale=False,
                xaxis_title="Missing values (%)",
                yaxis_title="",
                margin=dict(l=8, r=34, t=12, b=18),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#344b5a"),
            )
            st.plotly_chart(missing_chart, width="stretch", config={"displayModeBar": False})

    with recommendations_col:
        st.subheader("Recommended next steps")
        recommendations = []
        if duplicate_count:
            recommendations.append(
                (f"Remove {duplicate_count} exact duplicate row(s).", "Duplicate Row")
            )
        if "Missing Value" in issue_types:
            top_missing = column_profile.sort_values("Missing %", ascending=False).iloc[0]
            recommendations.append(
                (
                    f"Review missing values first in **{top_missing['Column']}** "
                    f"({top_missing['Missing %']:.1f}% missing).",
                    "Missing Value",
                )
            )
        if "Invalid Email" in issue_types:
            recommendations.append(
                ("Validate malformed email addresses before sending communications.", "Invalid Email")
            )
        if {"Invalid Date", "Inconsistent Date Format"} & issue_types:
            recommendations.append(
                ("Standardize mixed date formats and review unparseable values.", "Invalid Date")
            )
        if "Numeric Outlier" in issue_types:
            recommendations.append(
                ("Check statistical outliers against the source before changing values.", "Numeric Outlier")
            )
        if not recommendations:
            st.success("No action needed — your data looks great.")
            st.markdown("Preview the dataset or export a cleaned copy whenever you’re ready.")
        else:
            for recommendation, _ in recommendations:
                st.markdown(f"- {recommendation}")
        with st.expander("How to interpret this report"):
            st.markdown(
                "- Each finding represents a detected value or duplicate row, not a confirmed business error.\n"
                "- Statistical outliers are review candidates, not automatic corrections.\n"
                "- Change the column rules in the sidebar to match your data."
            )

    st.divider()
    st.subheader("Explore a numeric distribution")
    if numeric_columns:
        numeric_col, distribution_col = st.columns([1, 2])
        with numeric_col:
            selected_numeric = st.selectbox(
                "Choose a numeric column",
                options=list(numeric_columns),
                key=f"distribution_column_{column_signature}",
            )
            numeric_values = parse_numeric_series(data[selected_numeric]).dropna()
            st.metric("Valid numeric values", f"{len(numeric_values):,}")
            if not numeric_values.empty:
                distribution_metrics = st.columns(2)
                distribution_metrics[0].metric(
                    "Median", f"{numeric_values.median():,.2f}"
                )
                distribution_metrics[1].metric(
                    "Range", f"{numeric_values.min():,.2f} – {numeric_values.max():,.2f}"
                )
        with distribution_col:
            if numeric_values.empty:
                st.info("There are no numeric values to chart in this column.")
            else:
                distribution = px.histogram(
                    numeric_values.to_frame(name=str(selected_numeric)),
                    x=str(selected_numeric),
                    marginal="box",
                    color_discrete_sequence=[CHART_COLORS[0]],
                    labels={str(selected_numeric): str(selected_numeric)},
                    opacity=0.86,
                )
                distribution.update_layout(
                    template="plotly_white",
                    showlegend=False,
                    xaxis_title=str(selected_numeric),
                    yaxis_title="Rows",
                    margin=dict(l=12, r=12, t=20, b=20),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#344b5a"),
                )
                st.plotly_chart(
                    distribution, width="stretch", config={"displayModeBar": False}
                )
    else:
        st.info("Choose a Numeric column in the sidebar to explore its distribution.")

    with st.expander("Column profile", expanded=False):
        st.caption("Automatically inferred types can be adjusted in Column Rules.")
        st.dataframe(column_profile, width="stretch", hide_index=True)

with issues_tab:
    st.subheader("Issue explorer")
    st.caption(f"Detailed findings for **{active_dataset}**.")
    if issues.empty:
        st.success("No issues found. Your dataset passed all checks enabled by the current rules.")
    else:
        filter_col, summary_col = st.columns([1, 2])
        filter_options = ["All issue types"] + sorted(issues["Issue Type"].unique().tolist())
        with filter_col:
            selected_type = st.selectbox("Filter findings", filter_options)
        filtered_issues = issues if selected_type == "All issue types" else issues[
            issues["Issue Type"] == selected_type
        ]
        with summary_col:
            st.markdown(
                f"**{len(filtered_issues):,}** visible · "
                f"**{issue_count:,}** total findings · "
                f"**{issues['Column Name'].nunique():,}** affected columns"
            )
        search_col, column_filter_col = st.columns([1.5, 1])
        with search_col:
            issue_search = st.text_input(
                "Search findings",
                placeholder="Search values, columns, or suggested fixes",
                key=f"issue_search_{column_signature}",
            )
        with column_filter_col:
            issue_column_options = ["All columns"] + sorted(
                filtered_issues["Column Name"].astype(str).unique().tolist()
            )
            selected_issue_column = st.selectbox(
                "Filter by column",
                issue_column_options,
                key=f"issue_column_filter_{column_signature}",
            )
        if selected_issue_column != "All columns":
            filtered_issues = filtered_issues[
                filtered_issues["Column Name"].astype(str) == selected_issue_column
            ]
        if issue_search.strip():
            search_mask = filtered_issues.astype(str).apply(
                lambda column: column.str.contains(
                    issue_search.strip(),
                    case=False,
                    regex=False,
                    na=False,
                )
            ).any(axis=1)
            filtered_issues = filtered_issues[search_mask]
        st.caption(
            f"Showing {len(filtered_issues):,} of {len(issues):,} detected findings"
        )
        if filtered_issues.empty:
            st.info("No findings match these search and filter choices.")
        else:
            st.dataframe(filtered_issues, width="stretch", hide_index=True)
        st.download_button(
            "Download issue report",
            data=filtered_issues.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{Path(active_dataset).stem}_issue_report.csv",
            mime="text/csv",
            width="content",
            key=f"download_issues_{column_signature}",
            disabled=filtered_issues.empty,
        )

with review_tab:
    st.subheader("Review and fix the active file")
    st.caption(
        f"All rows in **{active_dataset}** are shown below. Highlighted cells match "
        "the current quality findings; exact duplicate rows are highlighted across the row."
    )
    fixed_datasets = st.session_state.setdefault("fixed_datasets", {})
    show_fixed_key = f"show_fixed_preview_{column_signature}"
    with st.expander("Choose safe fixes to apply", expanded=True):
        fix_duplicates = st.checkbox(
            "Remove exact duplicate rows",
            value=True,
            key=f"fix_duplicates_{column_signature}",
        )
        fix_whitespace = st.checkbox(
            "Trim leading and trailing whitespace",
            value=True,
            key=f"fix_whitespace_{column_signature}",
        )
        fix_missing_numeric = st.checkbox(
            "Fill missing values in selected Numeric columns with the median",
            value=True,
            key=f"fix_missing_numeric_{column_signature}",
            disabled=not numeric_columns,
        )
        fix_date_formats = st.checkbox(
            "Standardize valid dates to YYYY-MM-DD",
            value=True,
            key=f"fix_date_formats_{column_signature}",
            disabled=not date_columns,
        )
        st.caption(
            "Invalid emails, invalid dates, and statistical outliers need human review "
            "and are not changed automatically. Ambiguous dates are also left unchanged."
        )
        if st.button(
            "Apply selected fixes",
            type="primary",
            width="stretch",
            key=f"apply_fixes_{column_signature}",
            disabled=not any(
                [
                    fix_duplicates,
                    fix_whitespace,
                    fix_missing_numeric and numeric_columns,
                    fix_date_formats and date_columns,
                ]
            ),
        ):
            fixed_datasets[active_dataset] = clean_data(
                data,
                numeric_columns=numeric_columns,
                date_columns=date_columns,
                drop_duplicates=fix_duplicates,
                trim_whitespace=fix_whitespace,
                fill_numeric_missing=fix_missing_numeric,
                standardize_dates=fix_date_formats,
            )
            st.session_state[show_fixed_key] = True
            st.success(
                f"Applied fixes to a copy of {active_dataset}. The original workspace data is unchanged."
            )

    has_fixed_data = active_dataset in fixed_datasets
    if has_fixed_data:
        show_fixed = st.toggle(
            "Show fixed preview",
            key=show_fixed_key,
            help="Switch between the original file and the copy with selected fixes applied.",
        )
    else:
        show_fixed = False

    review_data = fixed_datasets[active_dataset] if show_fixed else data
    review_issues, _ = scan_data(
        review_data,
        email_columns=email_columns,
        date_columns=date_columns,
        numeric_columns=numeric_columns,
        iqr_multiplier=iqr_multiplier,
    )
    if show_fixed:
        st.info(
            f"Fixed copy: {len(review_data):,} rows · "
            f"{len(review_issues):,} remaining finding(s)."
        )
        result_metrics = st.columns(3)
        result_metrics[0].metric(
            "Rows removed",
            f"{max(len(data) - len(review_data), 0):,}",
        )
        result_metrics[1].metric(
            "Findings resolved",
            f"{max(issue_count - len(review_issues), 0):,}",
        )
        result_metrics[2].metric("Needs manual review", f"{len(review_issues):,}")
        st.caption(
            "The original file remains available in the workspace; only the exported copy is fixed."
        )
    else:
        st.info(
            f"Original data: {len(review_data):,} rows · "
            f"{len(review_issues):,} finding(s) highlighted."
        )

    if review_issues.empty:
        st.success("No issues to highlight in this view.")
    else:
        st.markdown(
            '<span style="display:inline-block;width:12px;height:12px;'
            'background:#fff0c2;border:1px solid #e6c46a;border-radius:3px;'
            'vertical-align:middle"></span> Cell has a finding '
            '&nbsp;&nbsp; '
            '<span style="display:inline-block;width:12px;height:12px;'
            'background:#fff1ed;border:1px solid #e9b5aa;border-radius:3px;'
            'vertical-align:middle"></span> Duplicate row',
            unsafe_allow_html=True,
        )

    review_display = review_data.copy()
    review_display.insert(0, "Row Number", np.arange(1, len(review_display) + 1))
    review_search_col, review_filter_col = st.columns([1.5, 1])
    with review_search_col:
        review_search = st.text_input(
            "Search rows",
            placeholder="Search across values in this file",
            key=f"review_search_{column_signature}_{int(show_fixed)}",
        )
    with review_filter_col:
        issue_rows_only = st.toggle(
            "Show rows with findings only",
            value=False,
            key=f"issue_rows_only_{column_signature}_{int(show_fixed)}",
        )
    if issue_rows_only:
        if review_issues.empty:
            review_display = review_display.iloc[0:0]
        else:
            review_display = review_display[
                review_display["Row Number"].isin(review_issues["Row Number"])
            ]
    if review_search.strip():
        search_mask = review_display.astype(str).apply(
            lambda column: column.str.contains(
                review_search.strip(),
                case=False,
                regex=False,
                na=False,
            )
        ).any(axis=1)
        review_display = review_display[search_mask]
    st.caption(
        f"Showing {len(review_display):,} of {len(review_data):,} rows"
        + (" with findings" if issue_rows_only else "")
    )
    if review_display.empty:
        st.info("No rows match these search and filter choices.")
    else:
        st.dataframe(
            dataframe_styles(review_display, review_issues),
            width="stretch",
            height=650,
            hide_index=True,
        )

    if has_fixed_data and show_fixed:
        fixed_payload, fixed_mime, fixed_extension = serialize_data_file(
            active_dataset,
            review_data,
        )
        output_stem = Path(active_dataset).stem or "data"
        st.download_button(
            f"Download fixed file ({fixed_extension[1:].upper()})",
            data=fixed_payload,
            file_name=f"{output_stem}_fixed{fixed_extension}",
            mime=fixed_mime,
            type="primary",
            width="stretch",
            key=f"download_fixed_{column_signature}",
        )

with preview_tab:
    st.subheader("Your data, ready to explore")
    st.caption(
        f"Previewing **{active_dataset}**. The original data remains unchanged by export cleaning."
    )
    st.dataframe(data.head(100), width="stretch", hide_index=True)
    cleaned_data = clean_data(data, numeric_columns=numeric_columns)
    st.caption(
        f"One-click cleaning removes exact duplicates, trims text whitespace, "
        f"and fills missing numeric values with their column median. "
        f"Preview: {len(cleaned_data):,} rows after cleaning."
    )
    download_col, batch_col = st.columns([1, 1])
    with download_col:
        st.download_button(
            "Download this cleaned CSV",
            data=cleaned_data.to_csv(index=False).encode("utf-8"),
            file_name=f"{active_dataset.rsplit('.', 1)[0]}_cleaned.csv",
            mime="text/csv",
            type="primary",
            width="stretch",
        )
    with batch_col:
        if len(datasets) > 1:
            archive = BytesIO()
            with ZipFile(archive, mode="w") as zip_file:
                for dataset_name, dataset in datasets.items():
                    cleaned = clean_data(dataset)
                    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", dataset_name)
                    if not safe_name.lower().endswith(".csv"):
                        safe_name = f"{safe_name}.csv"
                    zip_file.writestr(
                        f"{safe_name.rsplit('.', 1)[0]}_cleaned.csv",
                        cleaned.to_csv(index=False),
                    )
            st.download_button(
                "Download all cleaned files",
                data=archive.getvalue(),
                file_name="cleaned_data_batch.zip",
                mime="application/zip",
                width="stretch",
            )
        else:
            st.info("Upload multiple files to export the full batch as one ZIP.")
    st.caption(
        "Quality reports are calculated independently for each file. "
        "Uploaded files stay in the current app session and are not saved to a database."
    )
