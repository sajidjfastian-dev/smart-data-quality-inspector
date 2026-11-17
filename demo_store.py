"""Isolated PostgreSQL synthetic demo storage. No schema writes at runtime."""
import os
from contextlib import contextmanager
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from demo_codec import encode, decode


class DemoStoreError(ValueError):
    pass


class DemoConflict(DemoStoreError):
    pass


@contextmanager
def connection():
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5,
                             options="-c statement_timeout=10000", row_factory=dict_row) as conn:
            yield conn
    except (psycopg.Error, KeyError):
        raise DemoStoreError("Demo database unavailable. Private uploads remain session-only; please retry.") from None


def create_session():
    identifier = "DEMO-" + uuid4().hex[:12].upper()
    with connection() as conn:
        conn.execute("INSERT INTO dq_demo_sessions (id, synthetic_history) VALUES (%s,false)", (identifier,))
    return identifier


def load_catalog():
    with connection() as conn:
        row = conn.execute("SELECT payload FROM dq_demo_catalog WHERE id = %s", ("quality-v1",)).fetchone()
    if not row:
        raise DemoStoreError("Synthetic demo data has not been seeded. Run the development setup.")
    return decode(row["payload"])


def list_requests():
    with connection() as conn:
        rows = conn.execute("SELECT reference, payload, version FROM dq_demo_requests ORDER BY created_at DESC").fetchall()
    result = {}
    for row in rows:
        record = decode(row["payload"])
        record["_db_version"] = row["version"]
        result[row["reference"]] = record
    return result


def insert_request(record):
    with connection() as conn:
        conn.execute("""INSERT INTO dq_demo_requests(reference, session_id, payload)
                     VALUES (%s,%s,%s)""",
                     (record["reference"], record["session_id"], Jsonb(encode(record))))
    record["_db_version"] = 1


def update_request(record, expected_version):
    with connection() as conn:
        row = conn.execute("""UPDATE dq_demo_requests
            SET payload=%s,version=version+1,updated_at=now()
            WHERE reference=%s AND version=%s RETURNING version""",
            (Jsonb(encode(record)), record["reference"], expected_version)).fetchone()
        if not row:
            raise DemoConflict("This shared demo request changed in another session. Reopen it and review the latest version.")
    record["_db_version"] = row["version"]
