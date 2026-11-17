"""Small deterministic dataset used by regression tests, not exposed in the app."""

from datetime import date

import numpy as np
import pandas as pd


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


def load_test_fixture(app):
    """Install a deterministic file directly in an AppTest session."""
    label = "Sample messy dataset"
    app.session_state["inspector_datasets"] = {label: make_sample_data()}
    app.session_state["inspector_upload_signature"] = ()
    app.session_state["active_dataset"] = label
    app.session_state["fixed_datasets"] = {}
    app.session_state["quality_scan_cache"] = {}
    app.session_state["review_scan_cache"] = {}
    app.session_state["batch_export_cache"] = None
    app.session_state["distribution_cache"] = {}
    app.session_state["data_insights_cache"] = {}
    app.session_state["fixed_export_cache"] = {}
    app.run()
