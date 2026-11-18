"""Simulate a fresh post-Publish database in a disposable development schema.

No production connection is used. Create the test schema, apply the same schema
that Publish introspects, then exercise only the startup's data-only seed.
"""
import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from psycopg import sql
import demo_store
import persistent_demo
import request_workflow as flow
import sample_endpoint
from scripts.seed_demo import seed
from scripts.seed_public_sample import seed_public


class FreshDemoDatabaseTests(unittest.TestCase):
    def test_empty_database_seed_endpoint_workflow_and_idempotency(self):
        schema = "dq_test_" + uuid4().hex
        original_connection = demo_store.connection
        with original_connection() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

        @contextmanager
        def isolated():
            with original_connection() as conn:
                conn.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
                yield conn

        try:
            # This represents Publish's schema application, not runtime DDL.
            with isolated() as conn:
                conn.execute((Path(__file__).resolve().parents[1]/"scripts/demo_schema.sql").read_text())
            with patch("demo_store.connection", isolated), \
                 patch("scripts.seed_demo.connection", isolated), \
                 patch("scripts.seed_public_sample.connection", isolated), \
                 patch("sample_endpoint.connection", isolated):
                # The data-only initializer must not read the schema migration.
                # Quality compilation may read app.py, but never a SQL migration.
                real_read = Path.read_text
                def no_schema_read(path, *args, **kwargs):
                    if path.suffix == ".sql":
                        raise AssertionError("Startup attempted to read a schema migration")
                    return real_read(path, *args, **kwargs)
                with patch.object(Path, "read_text", no_schema_read):
                    seed_public()
                self.assertEqual(len(demo_store.list_requests()), 4)
                self.assertTrue(all(r["source_id"].startswith("ecb-fx-") for r in demo_store.list_requests().values()))
                result = sample_endpoint.sample_rows(None)
                self.assertEqual(result.status_code, 200)
                self.assertEqual(json.loads(result.body)["count"], 620)
                state = {"demo_user":"Sajid", "demo_role":"Submitter"}
                persistent_demo.initialize(state)
                payload = state["demo_catalog"]["variants"]["fix-1111"]
                persistent_demo.register_source(state, payload["original"])
                reference = flow.new_request(state)
                flow.save_draft(state, reference, payload)
                flow.submit(state, reference)
                for action in ("approve","ticket","cab","simulate"):
                    flow.demo_review_action(state, reference, 1, action)
                before = demo_store.list_requests()[reference]
                seed_public()
                after = demo_store.list_requests()[reference]
                self.assertEqual(after["_db_version"], before["_db_version"])
                self.assertEqual(after["revisions"][-1]["status"], "Simulated")
                self.assertEqual(len(demo_store.list_requests()), 5)
                flow.valid_snapshot(after["revisions"][-1])
        finally:
            with original_connection() as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    unittest.main()
