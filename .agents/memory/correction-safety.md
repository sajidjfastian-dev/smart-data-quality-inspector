---
name: Correction safety
description: Boundaries for automatic fixes, manual corrections and pre-submission review.
---
The user wants findings integrated into Review & fix rather than a standalone Issue log, with maximum useful automatic fixes and a complete change preview before submission. The user subsequently specified: “dont give option to type any things manually for correction ssytem should do all auto whereever applicable.”

**Why:** The user wants a clear path from quality rules to corrected data and confidence before reviewer handoff.

**How to apply:** Do not offer typed replacement values or manual cell editors. Keep automatic corrections limited to deterministic normalization and explicitly selected strategies. Never invent email addresses, guess ambiguous dates, or clamp business values merely to pass a rule. Disclose unresolved findings for source verification. Optional AI advice does not apply changes. Synthetic demonstration files should contain realistic, automatically correctable defects, without mocking scan results.

Preserve manual corrections when offering later automated actions, and keep correction history relative to the original rows through duplicate removal.

**Why:** Rebuilding a copy from the original can silently erase manual work; losing row lineage makes the approval comparison misleading.

**How to apply:** Compose corrections with reliable original-row lineage, or prevent a destructive rerun. Submission acknowledgements and approvals must refer to the exact corrected version. Exports must not silently apply extra fixes beyond the previewed copy.
