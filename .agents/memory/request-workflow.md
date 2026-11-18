---
name: Department request workflow
description: User-defined request lifecycle and explicit demo-only scope.
---
Users from any department should log in and see a Request list in the left menu. The list needs DQ-current-year-six-random-digit references, submitter, submission date, status, rejected-by information, View actions, filters and status totals.

The workflow is configurable quality checks → 360-degree inspection → suggested fixes and AI assistance → submit for review → data-owner review → service-desk ticket → ticket/workflow and CAB approvals → explicit production application.

**Why:** The user described this as the actual application workflow and requested minimum changes to the existing application.

**How to apply:** Reuse existing inspection, rules, assistant, comparisons and tickets. Do not confuse owner approval with CAB approval or permit execution before all required gates.

For the judges' presentation, process actual uploaded data through the real inspection, correction, review and approved-file download flow. Keep SSO, reviewer identity and ticket generation as demos; keep real uploads session-only and do not write to production systems.

**Why:** The user subsequently requested an end-to-end functional flow with real data and explicitly chose “Download approved file” and “Session-only for today.”

**How to apply:** Gate the final download on request, ticket and CAB approval of the same revision. Label demo identity and tickets honestly; do not claim session-only history survives logout or that the demo is production-authorized.

Use only two demo roles: Submitter and Approver.

**Why:** The user explicitly requested “only two roles. submitter/approver.”

**How to apply:** Keep ticket and CAB approvals as separate workflow steps handled by the Approver, not separate role choices.

The user approved database-backed synthetic demo data: at least 500 sample rows with correctable issues and about 20 requests across both statuses and demo sessions.

**Why:** The user explicitly selected “Synthetic records stored in database” and “Both statuses and sessions.”

**How to apply:** This changes the session-only rule for known synthetic demo records, not private uploads. Label synthetic provenance honestly; preserve the real-history SSO gate.
