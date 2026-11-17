"""Focused simulated ticket lifecycle checks; no external services."""
import json
import unittest

import pandas as pd

from demo_change_ticket import generate_ticket
from review_approval import (
    ApprovalRequired, approve, change_index, invalidate, return_for_revision, sync_context,
)


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.original = pd.DataFrame({"private": [" Secret ", " Secret ", "Other"]})
        self.fixed = pd.DataFrame({"private": ["Secret", "Other"]})
        self.changes = change_index(self.original, self.fixed, True)
        self.sync()

    def sync(self, dataset="a", rules=(), protected=("private",)):
        sync_context(self.state, dataset, self.original, self.fixed, rules, protected, True)

    def accept(self, dataset="a"):
        approve(self.state, dataset, self.fixed, "Fixed copy", 2)

    def generate(self, dataset="a"):
        return generate_ticket(self.state, dataset, self.original, self.fixed, "Fixed copy", self.changes)

    def test_gate_reuse_summary_and_privacy(self):
        with self.assertRaises(ApprovalRequired):
            self.generate()
        self.accept()
        ticket = self.generate()
        self.assertIs(ticket, self.generate())
        self.assertEqual(ticket["affected_rows"], 2)
        self.assertEqual(ticket["changed_cells"], 1)
        self.assertEqual(ticket["removed_rows"], 1)
        self.assertEqual(ticket["remaining_findings"], 2)
        self.assertNotIn("Secret", json.dumps(ticket))
        self.assertNotIn("private", json.dumps(ticket))

    def test_each_invalidation_marks_ticket_and_blocks_generation(self):
        mutations = [
            lambda: self.sync(rules=("new rule",)),
            lambda: self.sync(protected=()),
            lambda: invalidate(self.state, "a"),
            lambda: return_for_revision(self.state, "a"),
            self.change_data,
        ]
        for mutate in mutations:
            self.setUp()
            self.accept()
            ticket = self.generate()
            mutate()
            self.assertTrue(ticket["outdated"])
            with self.assertRaises(ApprovalRequired):
                self.generate()
            self.sync()
            self.accept()
            self.assertNotEqual(ticket["reference"], self.generate()["reference"])

    def change_data(self):
        self.fixed.loc[0, "private"] = "Changed"
        self.sync()

    def test_file_isolation_and_new_approval(self):
        self.accept()
        a = self.generate()
        self.sync("b")
        with self.assertRaises(ApprovalRequired):
            self.generate("b")
        self.accept("b")
        b = self.generate("b")
        self.assertNotEqual(a["reference"], b["reference"])
        self.assertIs(a, self.generate())
        self.accept()
        self.assertTrue(a["outdated"])
        self.assertNotEqual(a["reference"], self.generate()["reference"])

    def test_changed_frame_blocked_without_sync(self):
        self.accept()
        self.fixed.iloc[0, 0] = "Changed"
        with self.assertRaises(ApprovalRequired):
            self.generate()

    def test_original_has_no_proposed_fixes(self):
        approve(self.state, "a", self.original, "Original data", 5)
        ticket = generate_ticket(self.state, "a", self.original, self.original,
                                 "Original data", self.changes)
        self.assertEqual(ticket["fixes"], {})
        self.assertEqual(ticket["affected_rows"], 0)


if __name__ == "__main__":
    unittest.main()
