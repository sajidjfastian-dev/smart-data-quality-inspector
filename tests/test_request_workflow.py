import unittest
from unittest.mock import Mock
from copy import deepcopy
import pandas as pd
import request_workflow as flow
from review_approval import change_index, guarded_push, ApprovalRequired


def payload():
    original = pd.DataFrame({"name": [" Alice ", " Alice ", "Bob"], "age": [1, 1, 2]})
    selected = pd.DataFrame({"name": ["Alice", "Bob"], "age": [1, 2]})
    findings = pd.DataFrame(columns=["Row Number", "Column Name", "Issue Type", "Current Value", "Suggested Fix"])
    return dict(file="data.csv", original=original, selected=selected, choice="Fixed copy",
                issues=findings, remaining=findings.copy(), changes=change_index(original, selected, True),
                protected={"name"}, privacy_reviewed=True,
                rules={"enabled": ["missing"], "email": [], "date": [], "numeric": ["age"], "iqr": 1.5, "custom": []})


class RequestWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.state = {"demo_user": "Sajid", "demo_role": "Submitter"}
        self.ref = flow.new_request(self.state)
        self.data = payload()
        flow.save_draft(self.state, self.ref, self.data)

    def submitted(self):
        flow.submit(self.state, self.ref)
        self.state["demo_role"] = "Data owner"

    def approved(self):
        self.submitted()
        return flow.owner_decision(self.state, self.ref, True)

    def test_reference_collision_retries(self):
        draw = Mock(side_effect=[123456, 123456, 987654])
        a = flow.new_request(self.state, draw)
        b = flow.new_request(self.state, draw)
        self.assertTrue(a.endswith("-123456"))
        self.assertTrue(b.endswith("-987654"))

    def test_empty_draft_reopening_clears_upload_signature(self):
        empty = flow.new_request(self.state)
        self.state["inspector_upload_signature"] = ("stale",)
        self.state["data_upload"] = ["previous file"]
        flow.open_draft(self.state, empty)
        self.assertNotIn("inspector_upload_signature", self.state)
        self.assertNotIn("data_upload", self.state)

    def test_bind_is_idempotent_and_same_filename_separate(self):
        data = self.data["original"]
        one = flow.bind_draft(self.state, "data.csv", data)
        self.assertEqual(one, flow.bind_draft(self.state, "data.csv", data))
        self.assertNotEqual(one, flow.bind_draft(self.state, "data.csv", data.copy()))

    def test_frozen_snapshot_and_approval_order(self):
        self.submitted()
        snap = flow.current(self.state, self.ref)["snapshot"]
        self.data["selected"].iloc[0, 1] = 90
        self.data["rules"]["enabled"].clear()
        self.assertEqual(snap["selected"].iloc[0, 1], 1)
        self.assertEqual(snap["rules"]["enabled"], ["missing"])
        flow.owner_decision(self.state, self.ref, True)
        self.state["demo_role"] = "CAB"
        with self.assertRaises(flow.WorkflowError):
            flow.advance(self.state, self.ref, "simulate")
        self.state["demo_role"] = "Service desk"
        flow.advance(self.state, self.ref, "ticket")
        self.state["demo_role"] = "CAB"
        flow.advance(self.state, self.ref, "cab")
        flow.advance(self.state, self.ref, "simulate")
        n = len(flow.current(self.state, self.ref)["timeline"])
        flow.advance(self.state, self.ref, "simulate")
        self.assertEqual(n, len(flow.current(self.state, self.ref)["timeline"]))

    def test_submitter_cannot_self_approve(self):
        flow.submit(self.state, self.ref)
        with self.assertRaises(flow.WorkflowError):
            flow.owner_decision(self.state, self.ref, True)

    def test_ticket_created_once_and_contains_no_values(self):
        rev = self.approved()
        first = deepcopy(rev["ticket"])
        flow.owner_decision(self.state, self.ref, True)
        self.assertEqual(first, rev["ticket"])
        self.assertNotIn("Alice", repr(first))
        self.assertNotIn("data.csv", repr(first))

    def test_reject_requires_reason_and_revision_has_no_old_approval(self):
        self.submitted()
        with self.assertRaises(flow.WorkflowError):
            flow.owner_decision(self.state, self.ref, False, " ")
        flow.owner_decision(self.state, self.ref, False, "Check source")
        self.state["demo_role"] = "Submitter"
        new = flow.revise(self.state, self.ref)
        self.assertEqual(new["number"], 2)
        self.assertEqual(new["approval_state"], {})
        self.assertEqual(new["status"], "Draft")
        flow.submit(self.state, self.ref)
        self.assertEqual(flow.current(self.state, self.ref)["status"], "Submitted")
        self.assertEqual(flow.requests(self.state)[self.ref]["revisions"][0]["rejected_by"], "Demo Data Owner")

    def test_tampered_rules_or_mask_block_approvals(self):
        self.submitted()
        snap = flow.current(self.state, self.ref)["snapshot"]
        snap["protected"].clear()
        with self.assertRaises(flow.WorkflowError):
            flow.owner_decision(self.state, self.ref, True)

    def test_privacy_unreviewed_and_resubmit_blocked(self):
        self.data["privacy_reviewed"] = False
        with self.assertRaises(flow.WorkflowError):
            flow.submit(self.state, self.ref)
        self.data["privacy_reviewed"] = True
        flow.submit(self.state, self.ref)
        with self.assertRaises(flow.WorkflowError):
            flow.submit(self.state, self.ref)

    def test_changed_snapshot_cannot_execute(self):
        rev = self.approved()
        rev["snapshot"]["selected"].iloc[0, 1] = 999
        self.state["demo_role"] = "Service desk"
        with self.assertRaises(flow.WorkflowError):
            flow.advance(self.state, self.ref, "ticket")

    def test_same_filename_revision_isolation(self):
        first = self.approved()
        self.state["demo_role"] = "Submitter"
        other = flow.new_request(self.state)
        flow.save_draft(self.state, other, payload())
        flow.submit(self.state, other)
        self.assertEqual(first["status"], "Approved")
        self.assertEqual(flow.current(self.state, other)["approval_state"]["final_approvals"], {})

    def test_live_sender_never_called(self):
        self.approved()
        sender = Mock()
        with self.assertRaises(ApprovalRequired):
            guarded_push(self.state, self.ref, self.data["original"], self.data["selected"],
                         "Fixed copy", {"name"}, True, True, sender)
        sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
