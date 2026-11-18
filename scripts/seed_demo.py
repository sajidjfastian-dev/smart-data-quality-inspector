"""Idempotent synthetic seed with an explicit development-only schema option.

Compile the application's actual pure inspection functions, like the existing
regression fixtures, to avoid importing/executing its Streamlit UI. The ASGI
lifespan may seed data after Publish has migrated the schema; it never runs DDL.
"""
import argparse
import ast
import json
import re
import sys
from copy import deepcopy
from datetime import date, datetime, timedelta
from itertools import product
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb
from quality_large import scan_large_data
from numeric_quality import parse_numbers
from demo_store import connection
from demo_codec import encode, stable_roundtrip
from review_approval import change_index
import request_workflow as flow


def quality_functions():
    names = {"is_missing", "display_value", "parse_date", "date_shape", "parse_numeric_series",
             "infer_column_rules", "scan_data", "clean_data", "standardize_date_value"}
    constants = {"EMAIL_PATTERN", "DATE_FORMATS", "DATE_SHAPES", "ISSUE_COLUMNS"}
    tree = ast.parse((ROOT / "app.py").read_text())
    nodes = [n for n in tree.body if
             (isinstance(n, ast.FunctionDef) and n.name in names) or
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in n.targets))]
    namespace = dict(np=np, pd=pd, re=re, datetime=datetime, date=date,
                     scan_large_data=scan_large_data, parse_numbers=parse_numbers)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


def synthetic_rows():
    rows = []
    for i in range(500):
        row = dict(customer_id=10001+i, name=f"Demo Customer {i+1:03}",
                   email=f"demo{i+1:03}@example.test", signup_date=f"2026-01-{i%28+1:02}",
                   age=22+i%45, annual_spend=float(1000+(i%100)*20),
                   region=("North", "South", "East", "West")[i%4])
        if i % 50 == 0:
            row["annual_spend"] = None
        if i % 50 == 1:
            row["email"] = f"invalid-demo-{i}"
        if i % 50 == 2:
            row["signup_date"] = "2026/01/20"
        if i % 50 == 3:
            row["signup_date"] = "not-a-date"
        if i % 50 == 4:
            row["name"] = "  " + row["name"] + "  "
        if i % 50 == 5:
            row["annual_spend"] = 90000.0
        if i % 50 == 6:
            row["region"] = None
        rows.append(row)
    return rows + deepcopy(rows[100:120])


def build_catalog(rows, public_source=None):
    f = quality_functions()
    original = pd.DataFrame(rows)
    if public_source:
        original.attrs["public_sample_source"] = public_source
    email, dates, numeric = f["infer_column_rules"](original)
    rules = dict(email=sorted(email), date=sorted(dates), numeric=sorted(numeric),
                 iqr=1.5, enabled=["date", "duplicates", "email", "missing", "outliers"], custom=[])
    if public_source:
        rules["enabled"].append("numeric")
    issues, _ = f["scan_data"](original, email_columns=email, date_columns=dates,
                              numeric_columns=numeric, enabled_checks=rules["enabled"])
    payload = dict(file="Synthetic quality sample", original=original, selected=original,
                   choice="Original data", changes=change_index(original, original, False),
                   issues=issues, remaining=issues, protected={"customer_id","name","email"},
                   privacy_reviewed=True, rules=rules)
    variants = {"original": stable_roundtrip(payload)}
    for flags in product((False, True), repeat=4):
        selected = f["clean_data"](original, numeric_columns=sorted(numeric), date_columns=sorted(dates),
                                   drop_duplicates=flags[0], trim_whitespace=flags[1],
                                   fill_numeric_missing=flags[2], standardize_dates=flags[3])
        remaining, _ = f["scan_data"](selected, email_columns=email, date_columns=dates,
                                     numeric_columns=numeric, enabled_checks=rules["enabled"])
        variant = dict(payload, selected=selected, choice="Fixed copy",
                       changes=change_index(original, selected, flags[0]), remaining=remaining)
        variants["fix-"+"".join(str(int(x)) for x in flags)] = stable_roundtrip(variant)
    return dict(variants=variants, issue_counts=issues["Issue Type"].value_counts().to_dict())


def seed(*, apply_development_schema=False):
    with connection() as conn:
        if apply_development_schema:
            # Never enabled by the runtime entrypoint or deploy build command.
            conn.execute((ROOT / "scripts/demo_schema.sql").read_text())
        conn.execute("SELECT pg_advisory_xact_lock(460046)")
        exists = conn.execute("SELECT 1 FROM dq_demo_catalog WHERE id=%s", ("quality-v1",)).fetchone()
        if exists:
            print("Synthetic seed already exists; existing requests preserved.")
            return
        rows = synthetic_rows()
        catalog = build_catalog(rows)
        for i, row in enumerate(rows, 1):
            conn.execute("INSERT INTO dq_demo_rows VALUES (%s,%s,%s)", ("quality-v1", i, Jsonb(row)))
        conn.execute("INSERT INTO dq_demo_catalog VALUES (%s,%s)", ("quality-v1", Jsonb(encode(catalog))))
        for i in range(5):
            conn.execute("INSERT INTO dq_demo_sessions(id,created_at,synthetic_history) VALUES (%s,%s,true)",
                         (f"DEMO-HISTORY-{i+1:02}", datetime.now(ZoneInfo("Asia/Dubai"))-timedelta(days=10-i, hours=4)))
        for i in range(20):
            state = {"demo_user": "Sajid", "demo_role": "Submitter"}
            ref = flow.new_request(state, lambda: 700001+i)
            record = flow.requests(state)[ref]
            record.update(file="Synthetic quality sample", session_id=f"DEMO-HISTORY-{i%5+1:02}",
                          synthetic=True, source_id="quality-v1")
            variant = "original" if i%3==0 else "fix-1111"
            flow.save_draft(state, ref, deepcopy(catalog["variants"][variant]))
            status = flow.STATUSES[i%len(flow.STATUSES)]
            if status != "Draft":
                flow.submit(state, ref)
                state["demo_role"] = "Approver"
                if status == "Rejected":
                    flow.owner_decision(state, ref, False, "Validate remaining findings")
                elif status != "Submitted":
                    flow.owner_decision(state, ref, True)
                    for step, after in (("ticket","Ticket approved"),("cab","CAB approved"),("simulate","Simulated")):
                        if flow.current(state, ref)["status"] == status:
                            break
                        flow.advance(state, ref, step)
            revision = flow.current(state, ref)
            revision["variant"] = variant
            start = datetime.now(ZoneInfo("Asia/Dubai"))-timedelta(days=10-i%5, hours=i//5)
            record["created_at"] = start.isoformat()
            for j, event in enumerate(revision["timeline"]):
                event["Date (Asia/Dubai)"] = (start+timedelta(minutes=j*5)).isoformat()
            if revision["submitted_at"]:
                revision["submitted_at"] = (start+timedelta(minutes=5)).isoformat()
            for approval in revision["approval_state"].get("final_approvals", {}).values():
                approval["approved_at"] = (start+timedelta(minutes=10)).isoformat()
            conn.execute("INSERT INTO dq_demo_requests(reference,session_id,payload,created_at) VALUES (%s,%s,%s,%s)",
                         (ref,record["session_id"],Jsonb(encode(record)), start))
        print(f"Seeded {len(rows)} synthetic rows and 20 complete demo requests.")
        print("Issue counts:", catalog["issue_counts"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development-schema", action="store_true",
                        help="Apply the schema in development only. Publish owns production schema.")
    args = parser.parse_args()
    # Current setup creates only public examples. The legacy seed function
    # remains available for compatibility tests, never new runtime histories.
    if args.development_schema:
        with connection() as conn:
            conn.execute((ROOT / "scripts/demo_schema.sql").read_text())
    from scripts.seed_public_sample import seed_public
    seed_public()
