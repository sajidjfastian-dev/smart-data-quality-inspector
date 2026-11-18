"""Focused source consistency, correction and approval checks for the ECB snapshot."""
import unittest
from copy import deepcopy
from io import BytesIO
import json
import pandas as pd
from pandas.testing import assert_frame_equal
from public_sample import original, demo_frame, metadata, SOURCE_ID, ROOT, FILES, LABEL
from scripts.seed_demo import build_catalog
from scripts.seed_public_sample import seed_public
import demo_store
import request_workflow as flow
from persistent_demo import canonical_payload, eligible
from sample_endpoint import sample_rows


class PublicSampleTests(unittest.TestCase):
    def test_formats_share_one_snapshot(self):
        self.assertEqual(len(original()), 600)
        self.assertEqual(len(demo_frame()), 620)
        for filename in FILES:
            actual = pd.read_csv(ROOT / filename) if filename.endswith(".csv") else pd.read_excel(ROOT / filename)
            assert_frame_equal(actual, demo_frame() if "demo_errors" in filename else original())
        self.assertIn("European Central Bank", metadata()["attribution"])

    def test_seed_preserves_all_existing_requests(self):
        before = demo_store.list_requests()
        seed_public()
        after = demo_store.list_requests()
        for ref, record in before.items():
            self.assertEqual(record["_db_version"], after[ref]["_db_version"])
        self.assertTrue(any(r.get("source_id") == SOURCE_ID for r in after.values()))

    def test_api_and_catalog_are_consistent(self):
        payload = json.loads(sample_rows(None).body)
        self.assertEqual(payload["source"], SOURCE_ID)
        self.assertFalse(payload["synthetic"])
        self.assertTrue(payload["demo_errors"])
        self.assertEqual(payload["count"], 620)
        assert_frame_equal(pd.DataFrame(payload["rows"], columns=demo_frame().columns), demo_frame())
        catalog = demo_store.load_catalog(SOURCE_ID)
        self.assertEqual(set(catalog["variants"]["original"]["rules"]["enabled"]),
                         {"date", "duplicates", "email", "missing", "outliers", "numeric"})
        assert_frame_equal(catalog["variants"]["original"]["original"], demo_frame())
        from review_approval import frame_digest
        self.assertEqual(frame_digest(catalog["variants"]["original"]["original"]), frame_digest(demo_frame()))

    def test_fixes_restore_published_values_and_approval_download(self):
        catalog = demo_store.load_catalog(SOURCE_ID)
        fixed = catalog["variants"]["fix-1111"]
        assert_frame_equal(fixed["selected"].reset_index(drop=True), original())
        self.assertNotIn("Duplicate Row", fixed["remaining"]["Issue Type"].tolist())
        self.assertNotIn("Inconsistent Date Format", fixed["remaining"]["Issue Type"].tolist())
        state = {"demo_user":"Sajid", "demo_role":"Submitter"}
        ref = flow.new_request(state)
        flow.save_draft(state, ref, deepcopy(fixed))
        flow.submit(state, ref)
        with self.assertRaises(flow.WorkflowError):
            flow.approved_download(state, ref, 1)
        state["demo_role"] = "Approver"
        flow.owner_decision(state, ref, True)
        flow.advance(state, ref, "ticket")
        flow.advance(state, ref, "cab")
        state["demo_role"] = "Submitter"
        result = pd.read_csv(BytesIO(flow.approved_download(state, ref, 1)))
        assert_frame_equal(result, original())

    def test_private_upload_cannot_gain_shared_provenance(self):
        payload = demo_store.load_catalog(SOURCE_ID)["variants"]["original"]
        state = {"demo_catalog": demo_store.load_catalog(SOURCE_ID), "_synthetic_origins":[]}
        self.assertFalse(eligible(state, {}, payload))
        state["_synthetic_origins"] = [payload["original"]]
        self.assertTrue(eligible(state, {}, payload))
        self.assertFalse(eligible(state, {"_private":True}, payload))
        bad = deepcopy(payload)
        bad["selected"].iloc[0, 2] = 99
        with self.assertRaises(flow.WorkflowError):
            canonical_payload(state, bad)

    def test_legacy_catalog_still_validates_old_requests(self):
        legacy = demo_store.load_catalog("quality-v1")
        state = {"demo_catalog":demo_store.load_catalog(SOURCE_ID)}
        key, _ = canonical_payload(state, legacy["variants"]["original"], "quality-v1")
        self.assertEqual(key, "original")
