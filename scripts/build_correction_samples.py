"""Reproducible synthetic financial-services examples for the sample workspace.

Known source defects demonstrate existing corrections; no scan results are mocked.
This script does not connect to a database or replace saved requests.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1] / "sample_data"


def examples():
    rows = range(600)
    customers = pd.DataFrame({
        "customer_id": [10001+i for i in rows],
        "name": [f"Synthetic Customer {i+1:04}" for i in rows],
        "email": [f"customer{i+1:04}@example.test" for i in rows],
        "signup_date": ["2026-01-15" for i in rows],
        "age": [25+i%40 for i in rows],
        "annual_spend": [12000+(i%60)*200 for i in rows],
        "region": [["Abu Dhabi", "Dubai", "Sharjah"][i%3] for i in rows],
        "loyalty_tier": [["Standard", "Silver", "Gold"][i%3] for i in rows],
    })
    products = pd.DataFrame({
        "product_id": [20001+i for i in rows],
        "product_name": [["Savings account", "Current account", "Term deposit"][i%3] for i in rows],
        "category": ["Retail banking" for i in rows],
        "service_fee": [10+i%20 for i in rows],
        "effective_date": ["2026-01-15" for i in rows],
    })
    orders = pd.DataFrame({
        "order_id": [30001+i for i in rows],
        "customer_id": [10001+i for i in rows],
        "product_id": [20001+i for i in rows],
        "transaction_date": ["2026-01-15" for i in rows],
        "amount": [500+(i%50)*20 for i in rows],
        "currency": ["AED" for i in rows],
        "status": ["Completed" for i in rows],
    })
    tickets = pd.DataFrame({
        "ticket_id": [40001+i for i in rows],
        "customer_id": [10001+i for i in rows],
        "opened_date": ["2026-01-15" for i in rows],
        "category": [["Account enquiry", "Statement request", "Card service"][i%3] for i in rows],
        "response_minutes": [20+i%30 for i in rows],
        "status": ["Resolved" for i in rows],
    })
    events = pd.DataFrame({
        "event_id": [50001+i for i in rows],
        "customer_id": [10001+i for i in rows],
        "event_date": ["2026-01-15" for i in rows],
        "channel": [["Mobile banking", "Online banking"][i%2] for i in rows],
        "duration_seconds": [60+i%60 for i in rows],
        "result": ["Successful" for i in rows],
    })
    for filename, frame, date_col, numeric_col, text_col in (
        ("customers.csv", customers, "signup_date", "annual_spend", "region"),
        ("products.csv", products, "effective_date", "service_fee", "product_name"),
        ("orders.xlsx", orders, "transaction_date", "amount", "currency"),
        ("support_tickets.xlsx", tickets, "opened_date", "response_minutes", "category"),
        ("web_events.csv", events, "event_date", "duration_seconds", "channel"),
    ):
        # 40 numeric gaps, 60 unambiguous alternate dates, 50 padded strings.
        frame[numeric_col] = frame[numeric_col].astype(float)
        frame.loc[range(0, 600, 15), numeric_col] = float("nan")
        frame.loc[range(0, 600, 10), date_col] = "15/01/2026"
        frame.loc[range(0, 600, 12), text_col] = frame.loc[range(0, 600, 12), text_col].map(lambda v: f"  {v}  ")
        yield filename, pd.concat([frame, frame.iloc[1:21]], ignore_index=True)


if __name__ == "__main__":
    for filename, frame in examples():
        path = ROOT / filename
        if path.suffix == ".xlsx":
            frame.to_excel(path, index=False)
        else:
            frame.to_csv(path, index=False)
        print(f"{filename}: {len(frame)} synthetic rows")
