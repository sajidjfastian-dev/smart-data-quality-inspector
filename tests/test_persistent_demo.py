"""Focused real-development-DB checks; test-created rows are cleaned up."""
import json
import asyncio
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import demo_store as store
import request_workflow as flow
import persistent_demo as persistence
from demo_codec import stable_roundtrip
from scripts.seed_demo import seed, quality_functions
from sample_endpoint import sample_rows
from starlette.applications import Starlette
from starlette.routing import Route
from pandas.testing import assert_frame_equal


class PersistentDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from public_sample import SOURCE_ID
        cls.catalog = store.load_catalog(SOURCE_ID)

    def setUp(self):
        self.session = store.create_session()
        self.state = dict(demo_user="Sajid", demo_role="Submitter",
                          demo_session_id=self.session, demo_catalog=deepcopy(self.catalog),
                          _persistent_demo_ready=True)

    def tearDown(self):
        with store.connection() as conn:
            conn.execute("DELETE FROM dq_demo_requests WHERE session_id=%s", (self.session,))
            conn.execute("DELETE FROM dq_demo_sessions WHERE id=%s", (self.session,))

    def request(self, trusted=True, variant="original"):
        payload = deepcopy(self.catalog["variants"][variant])
        ref = flow.new_request(self.state)
        if trusted:
            persistence.register_source(self.state, payload["original"])
        flow.save_draft(self.state, ref, payload)
        return ref, payload

    def test_public_endpoint_and_read_only_methods(self):
        app = Starlette(routes=[Route("/api/demo/sample", sample_rows, methods=["GET"])])
        async def request(method):
            messages = []
            async def receive():
                return {"type":"http.request", "body":b"", "more_body":False}
            async def send(message):
                messages.append(message)
            await app({"type":"http","method":method, "path":"/api/demo/sample","root_path":"",
                       "scheme":"http","query_string":b"","headers":[], "http_version":"1.1"}, receive, send)
            return messages[0]["status"], b"".join(m.get("body", b"") for m in messages[1:])
        status, body = asyncio.run(request("GET"))
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["count"], 620)
        self.assertEqual(len(json.loads(body)["rows"]), 620)
        for method in ("POST","PUT","PATCH","DELETE"):
            self.assertEqual(asyncio.run(request(method))[0], 405)

    def test_implementation_survives_database_roundtrip(self):
        ref, _ = self.request()
        flow.submit(self.state, ref)
        for action in ("approve", "ticket", "cab"):
            flow.demo_review_action(self.state, ref, 1, action)
        flow.record_delivery_step(self.state, ref, 1)
        flow.record_delivery_step(self.state, ref, 1, True)
        stored = store.list_requests()[ref]
        rev = stored["revisions"][-1]
        self.assertTrue(rev["implementation"]["simulated"])
        self.assertEqual(rev["implementation"]["digest"], flow.valid_snapshot(rev)["selected_digest"])
        self.assertEqual(rev["timeline"][-1]["Action"], "Implemented on production (simulated)")
        self.state["demo_requests"][ref] = stored
        count = len(rev["timeline"])
        flow.record_delivery_step(self.state, ref, 1, True)
        self.assertEqual(len(store.list_requests()[ref]["revisions"][-1]["timeline"]), count)

    def test_seed_histories_and_all_snapshots(self):
        seeded = [r for r in store.list_requests().values() if r["session_id"].startswith("DEMO-HISTORY-")]
        self.assertEqual(len(seeded), 20)
        self.assertEqual({r["revisions"][-1]["status"] for r in seeded}, set(flow.STATUSES))
        self.assertEqual(len({r["session_id"] for r in seeded}), 5)
        for record in seeded:
            revision = record["revisions"][-1]
            payload = revision.get("snapshot") or revision["working"]
            self.assertEqual(len(payload["original"]), 520)
            self.assertGreater(len(payload["issues"]), 0)
            if revision.get("snapshot"):
                flow.valid_snapshot(revision)
            dates = [e["Date (Asia/Dubai)"] for e in revision["timeline"]]
            self.assertEqual(dates, sorted(dates))

    def test_catalog_uses_actual_inspection_and_fix_logic(self):
        f = quality_functions()
        for payload in self.catalog["variants"].values():
            rules = payload["rules"]
            actual, _ = f["scan_data"](payload["selected"], email_columns=rules["email"],
                                       date_columns=rules["date"], numeric_columns=rules["numeric"])
            assert_frame_equal(actual, payload["remaining"])
        fixed = self.catalog["variants"]["fix-1111"]
        self.assertEqual(len(fixed["selected"]), 600)
        self.assertLess(len(fixed["remaining"]), len(fixed["issues"]))
        self.assertGreater(len(fixed["changes"]), 0)

    def test_persistent_complete_lifecycle_and_new_revision(self):
        ref, _ = self.request(variant="fix-1111")
        flow.submit(self.state, ref)
        flow.demo_review_action(self.state, ref, 1, "approve")
        ticket = deepcopy(flow.current(self.state, ref)["approval_state"]["demo_change_tickets"])
        flow.demo_review_action(self.state, ref, 1, "approve")
        self.assertEqual(ticket, flow.current(self.state, ref)["approval_state"]["demo_change_tickets"])
        for step in ("ticket","cab","simulate"):
            flow.demo_review_action(self.state, ref, 1, step)
        self.assertEqual(store.list_requests()[ref]["revisions"][-1]["status"], "Simulated")
        original = deepcopy(flow.current(self.state, ref)["snapshot"])
        flow.revise(self.state, ref)
        latest = store.list_requests()[ref]["revisions"][-1]
        self.assertEqual(latest["status"], "Draft")
        self.assertEqual(latest["approval_state"], {})
        self.assertEqual(latest["number"], 2)
        self.assertEqual(original["seal"], store.list_requests()[ref]["revisions"][0]["snapshot"]["seal"])

    def test_stale_decision_cannot_overwrite_other_session(self):
        ref, _ = self.request()
        flow.submit(self.state, ref)
        stale = deepcopy(self.state)
        flow.demo_review_action(self.state, ref, 1, "approve")
        with self.assertRaisesRegex(flow.WorkflowError, "another session"):
            flow.demo_review_action(stale, ref, 1, "reject", persistence.REASONS[0])
        self.assertEqual(store.list_requests()[ref]["revisions"][-1]["status"], "Approved")
        self.assertEqual(flow.current(stale, ref)["status"], "Submitted")

    def test_private_and_lookalike_imports_never_persist(self):
        ref, payload = self.request(trusted=False)
        flow.requests(self.state)[ref]["file"] = "Synthetic quality sample"
        flow.requests(self.state)[ref]["synthetic"] = True  # client-style metadata is not provenance
        payload["rules"]["custom"] = [{"column":"name", "kind":"Must contain", "expected":"PRIVATE_SENTINEL_46"}]
        flow.save_draft(self.state, ref, payload)
        self.assertNotIn(ref, store.list_requests())
        with store.connection() as conn:
            count = conn.execute("SELECT count(*) AS n FROM dq_demo_requests WHERE payload::text LIKE %s",
                                 ("%PRIVATE_SENTINEL_46%",)).fetchone()["n"]
        self.assertEqual(count, 0)

    def test_shared_custom_rules_and_free_text_rejection_blocked(self):
        ref, payload = self.request()
        payload["rules"]["custom"] = [{"expected":"PRIVATE_SENTINEL_46"}]
        with self.assertRaises(flow.WorkflowError):
            flow.save_draft(self.state, ref, payload)
        flow.submit(self.state, ref)
        with self.assertRaises(flow.WorkflowError):
            flow.demo_review_action(self.state, ref, 1, "reject", "PRIVATE_SENTINEL_46")
        flow.demo_review_action(self.state, ref, 1, "reject", persistence.REASONS[0])
        self.assertEqual(store.list_requests()[ref]["revisions"][-1]["status"], "Rejected")

    def test_seed_idempotent_after_saved_change(self):
        ref, _ = self.request()
        flow.submit(self.state, ref)
        before = store.list_requests()
        seed()
        after = store.list_requests()
        self.assertEqual(set(before), set(after))
        self.assertEqual(before[ref]["_db_version"], after[ref]["_db_version"])
        flow.valid_snapshot(after[ref]["revisions"][-1])

    def test_reload_retains_only_shared_data(self):
        ref, _ = self.request()
        private, _ = self.request(trusted=False)
        reloaded = {"demo_user":"Sajid", "demo_session_id":self.session}
        persistence.initialize(reloaded)
        self.assertIn(ref, flow.requests(reloaded))
        self.assertNotIn(private, flow.requests(reloaded))

    def test_database_failure_is_explicit_and_rolls_back_session(self):
        ref, _ = self.request()
        with patch.object(store, "update_request", side_effect=store.DemoStoreError("Database unavailable")):
            with self.assertRaisesRegex(flow.WorkflowError, "unavailable"):
                flow.submit(self.state, ref)
        self.assertEqual(flow.current(self.state, ref)["status"], "Draft")


if __name__ == "__main__":
    unittest.main()
