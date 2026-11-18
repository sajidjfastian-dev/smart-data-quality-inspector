import unittest
from copy import deepcopy
from unittest.mock import patch
from test_request_workflow import payload
import request_workflow as flow


class ImplementationTests(unittest.TestCase):
    def ready(self):
        state = {"demo_user": "Sajid", "demo_role": "Submitter"}
        ref = flow.new_request(state)
        flow.save_draft(state, ref, payload())
        flow.submit(state, ref)
        for action in ("approve", "ticket", "cab"):
            flow.demo_review_action(state, ref, 1, action)
        return state, ref

    def test_explicit_confirmation_and_repeat(self):
        state, ref = self.ready()
        with self.assertRaises(flow.WorkflowError):
            flow.record_delivery_step(state, ref, 1, True)
        flow.record_delivery_step(state, ref, 1)
        self.assertEqual(flow.current(state, ref)["status"], "CAB approved")
        self.assertNotIn("implementation", flow.current(state, ref))
        flow.record_delivery_step(state, ref, 1, True)
        n = len(flow.current(state, ref)["timeline"])
        flow.record_delivery_step(state, ref, 1)
        flow.record_delivery_step(state, ref, 1, True)
        self.assertEqual(len(flow.current(state, ref)["timeline"]), n)
        self.assertTrue(flow.current(state, ref)["implementation"]["simulated"])

    def test_stale_rejected_and_tampered(self):
        state, ref = self.ready()
        flow.record_delivery_step(state, ref, 1)
        for status in ("Rejected", "Submitted", "Draft", "Approved"):
            other = deepcopy(state)
            flow.current(other, ref)["status"] = status
            with self.assertRaises(flow.WorkflowError):
                flow.record_delivery_step(other, ref, 1, True)
        other = deepcopy(state)
        flow.current(other, ref)["snapshot"]["selected"].iloc[0, 1] = 999
        with self.assertRaises(flow.WorkflowError):
            flow.record_delivery_step(other, ref, 1, True)
        flow.revise(state, ref)
        with self.assertRaises(flow.WorkflowError):
            flow.record_delivery_step(state, ref, 1, True)
        self.assertNotIn("download_requested", flow.current(state, ref))

    def test_stored_transaction_revalidates(self):
        state, ref = self.ready()
        state["demo_requests"][ref]["_db_version"] = 1
        def transaction(s, r, operation):
            local = deepcopy(s)
            local["_db_transaction"] = True
            result = operation(local)
            s["demo_requests"] = local["demo_requests"]
            return result
        with patch("persistent_demo.transaction", side_effect=transaction) as write:
            flow.record_delivery_step(state, ref, 1)
            flow.record_delivery_step(state, ref, 1, True)
            self.assertEqual(write.call_count, 2)
        self.assertTrue(flow.current(state, ref)["implementation"]["simulated"])
