import unittest
from copy import deepcopy
from io import BytesIO
from unittest.mock import patch
import pandas as pd
from pandas.testing import assert_frame_equal
from PIL import Image
import request_workflow as flow
from review_approval import frame_digest
from correction_workbench import save_copy
from row_rejections import restore_rows, reject_row, choices
from approval_evidence import validate_file, approve_with_evidence, binding, MAX_FILE
from test_request_workflow import payload


class RowRejectionTests(unittest.TestCase):
    def setUp(self):
        self.p = payload()
        self.state = flow.sample_seed_state("Sajid")
        self.ref = flow.new_request(self.state)
        flow.save_draft(self.state, self.ref, self.p)
        save_copy(self.state, "data.csv", self.p["original"], self.p["selected"], self.p["changes"])

    def reject(self, row):
        current = self.state["fixed_datasets"]["data.csv"]
        changes = self.state["fix_change_indexes"]["data.csv"]["changes"]
        reject_row(self.state, self.ref, "data.csv", self.p["original"], current, changes, row)

    def test_removed_row_cannot_be_rejected_and_remains_removed(self):
        with self.assertRaises(flow.WorkflowError):
            self.reject(2)
        self.reject(1)
        result = self.state["fixed_datasets"]["data.csv"]
        self.assertEqual(result["name"].tolist(), [" Alice ", "Bob"])
        changes = self.state["fix_change_indexes"]["data.csv"]["changes"]
        self.assertEqual(list(changes["Original row"]), [2])
        # Reapplication retains both the rejected row and all other fixes.
        reapplied, _ = restore_rows(self.p["original"], self.p["selected"], self.p["changes"],
                                   choices(self.state, self.ref, self.p["original"]))
        assert_frame_equal(result, reapplied)

    def test_restore_cell_only_and_frozen_protection(self):
        self.state["submit_ack_old"] = True
        self.reject(1)
        self.assertEqual(self.state["fixed_datasets"]["data.csv"]["name"].tolist(), [" Alice ", "Bob"])
        self.assertNotIn("submit_ack_old", self.state)
        self.assertEqual(self.p["original"]["name"].tolist(), [" Alice ", " Alice ", "Bob"])
        with self.assertRaises(flow.WorkflowError):
            flow.submit(self.state, self.ref)
        flow.save_draft(self.state, self.ref, flow.current(self.state, self.ref)["working"])
        flow.submit(self.state, self.ref)
        with self.assertRaises(flow.WorkflowError):
            self.reject(2)

    def test_all_rejections_restore_original_with_duplicate_indexes(self):
        original = self.p["original"].copy()
        original.index = [8, 8, 2]
        result, changes = restore_rows(original, self.p["selected"], self.p["changes"], [1, 2])
        assert_frame_equal(result, original.iloc[[0, 2]].reset_index(drop=True))
        self.assertEqual(list(changes["Original row"]), [2])
        with self.assertRaises(flow.WorkflowError):
            restore_rows(original, self.p["selected"], self.p["changes"], [0])

    def test_private_fork_does_not_change_shared_source(self):
        self.state["demo_requests"][self.ref]["synthetic"] = True
        before = deepcopy(self.state["demo_requests"][self.ref])
        self.reject(1)
        new_ref = self.state["active_request_ref"]
        self.assertNotEqual(new_ref, self.ref)
        self.assertTrue(self.state["demo_requests"][new_ref]["_private"])
        self.assertNotIn("row_rejections", self.state["demo_requests"][self.ref]["revisions"][-1])
        assert_frame_equal(before["revisions"][-1]["working"]["selected"],
                           self.state["demo_requests"][self.ref]["revisions"][-1]["working"]["selected"])
        flow.open_draft(self.state, new_ref)
        self.assertEqual(choices(self.state, new_ref, self.p["original"]), [1])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.state = flow.sample_seed_state("Sajid")
        self.ref = flow.new_request(self.state)
        flow.save_draft(self.state, self.ref, payload())
        flow.submit(self.state, self.ref)
        flow.demo_review_action(self.state, self.ref, 1, "approve")

    def test_validation_and_limits(self):
        image = BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        self.assertEqual(validate_file("../proof.png", image.getvalue())["name"], "proof.png")
        for name, data in [("proof.png", b"fake"), ("run.exe", b"MZ"), ("x.txt", b"\xff"),
                           ("x.txt", b""), ("x.txt", b"a" * (MAX_FILE + 1))]:
            with self.assertRaises(flow.WorkflowError):
                validate_file(name, data)

    def test_binding_audit_private_storage_and_export(self):
        proof = {"name": "cab-private.txt", "data": b"Confidential ticket evidence"}
        seal = binding(self.state, self.ref, 1)
        approve_with_evidence(self.state, self.ref, 1, "ticket", proof, expected_seal=seal)
        approve_with_evidence(self.state, self.ref, 1, "cab", proof)
        entries = self.state["private_approval_evidence"]
        self.assertEqual(len(entries), 2)
        approve_with_evidence(self.state, self.ref, 1, "cab", proof)
        self.assertEqual(len(entries), 2)
        with self.assertRaises(flow.WorkflowError):
            approve_with_evidence(self.state, self.ref, 1, "cab", {"name": "new.txt", "data": b"changed"})
        self.assertTrue(all(x["actor"] == "Sajid" and x["timestamp"] and x["seal"] == seal for x in entries.values()))
        self.assertNotIn("cab-private", repr(self.state["demo_requests"]))
        self.assertNotIn(b"Confidential", flow.approved_download(self.state, self.ref, 1))
        flow.revise(self.state, self.ref)
        with self.assertRaises(flow.WorkflowError):
            approve_with_evidence(self.state, self.ref, 1, "cab", proof)
        self.assertEqual(len(entries), 2)

    def test_failure_does_not_approve_or_store_evidence(self):
        with self.assertRaises(flow.WorkflowError):
            approve_with_evidence(self.state, self.ref, 1, "cab", {"name": "x.txt", "data": b"proof"})
        self.assertNotIn("private_approval_evidence", self.state)
        with self.assertRaises(flow.WorkflowError):
            approve_with_evidence(self.state, self.ref, 1, "ticket", expected_seal="stale")
        self.assertEqual(flow.current(self.state, self.ref)["status"], "Approved")

    def test_logout_erases_private_evidence(self):
        from demo_session import sign_out
        approve_with_evidence(self.state, self.ref, 1, "ticket", {"name": "x.txt", "data": b"proof"})
        with patch("demo_session.native.session_state", self.state):
            sign_out()
        self.assertNotIn("private_approval_evidence", self.state)
