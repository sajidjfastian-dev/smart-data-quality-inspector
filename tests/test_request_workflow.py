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
        self.state = flow.sample_seed_state("Sajid")
        self.ref = flow.new_request(self.state)
        self.data = payload()
        flow.save_draft(self.state, self.ref, self.data)

    def submitted(self):
        flow.submit(self.state, self.ref)
        self.state["demo_role"] = "Approver"

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
        old_key = flow.upload_widget_key(self.state)
        self.state[old_key] = ["previous file"]
        flow.open_draft(self.state, empty)
        self.assertNotIn("inspector_upload_signature", self.state)
        self.assertNotIn("data_upload", self.state)
        self.assertNotIn(old_key, self.state)
        self.assertNotEqual(old_key, flow.upload_widget_key(self.state))

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
        self.state["demo_role"] = "Approver"
        with self.assertRaises(flow.WorkflowError):
            flow.advance(self.state, self.ref, "simulate")
        flow.advance(self.state, self.ref, "ticket")
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
        self.assertEqual(flow.requests(self.state)[self.ref]["revisions"][0]["rejected_by"], "Demo Approver")

    def test_tampered_rules_or_mask_block_approvals(self):
        self.submitted()
        snap = flow.current(self.state, self.ref)["snapshot"]
        snap["protected"].clear()
        with self.assertRaises(flow.WorkflowError):
            flow.owner_decision(self.state, self.ref, True)

    def test_selection_metadata_is_sealed_and_revision_local(self):
        self.data["rule_selections"] = {"choices": {"business_abc": False}, "legacy_rules": []}
        self.submitted()
        old = flow.current(self.state, self.ref)
        self.state["demo_role"] = "Submitter"
        new = flow.revise(self.state, self.ref)
        self.assertEqual(new["working"]["rule_selections"], old["snapshot"]["rule_selections"])
        new["working"]["rule_selections"]["choices"]["business_abc"] = True
        self.assertFalse(old["snapshot"]["rule_selections"]["choices"]["business_abc"])
        flow.valid_snapshot(old)
        old["snapshot"]["rule_selections"]["choices"]["business_abc"] = True
        with self.assertRaises(flow.WorkflowError):
            flow.valid_snapshot(old)

    def test_shared_sample_selection_metadata_is_allowlisted(self):
        from business_rule_review import STANDARD_RULES, selection_key
        from demo_codec import stable_roundtrip
        from persistent_demo import canonical_payload
        sample = payload()
        sample["rules"]["enabled"] = [key for key, *_ in STANDARD_RULES]
        state = {"demo_catalog": {"variants": {"original": deepcopy(sample)}}}
        whitespace = selection_key("", "fix", "whitespace").removeprefix("review_rule__")
        sample["rule_selections"] = {"choices": {whitespace: False}, "legacy_rules": []}
        _, trusted = canonical_payload(state, sample)
        self.assertEqual(trusted["rule_selections"], sample["rule_selections"])
        flow.save_draft(self.state, self.ref, trusted)
        flow.submit(self.state, self.ref)
        flow.valid_snapshot(stable_roundtrip(flow.current(self.state, self.ref)))
        sample["rule_selections"]["choices"]["business_sensitive"] = False
        with self.assertRaises(flow.WorkflowError):
            canonical_payload(state, sample)
        sample["rule_selections"] = {"choices": {}, "legacy_rules": [{"expected": "private"}]}
        with self.assertRaises(flow.WorkflowError):
            canonical_payload(state, sample)

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
        self.state["demo_role"] = "Approver"
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
