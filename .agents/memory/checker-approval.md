---
name: Checker approval scope
description: User-selected demo review before destination pushes.
---
The user wants the checker to review applied fixes with incorrect/original data on the left and corrected data on the right, then give final approval before data can be pushed to a destination.

**Why:** The user explicitly requested final approval as a prerequisite for destination delivery.

**How to apply:** Link delivery to the reviewed version and invalidate approval after changes. Keep masking in the comparison and disclose unresolved findings.

Use demo approval for now, not a separate authenticated checker.

**Why:** The user selected “Demo approval for now.”

**How to apply:** Clearly label the approval as a demo session action; do not claim independent reviewer identity or production separation of duties.

After demo approval, provide a demo service desk ticket to request application of the fixes to production.

**Why:** The user requested this step and selected “Demo ticket for now.”

**How to apply:** Clearly distinguish the simulated ticket from a real submitted service desk request; generating it must not change production data.

Keep demo tickets aggregate-only rather than embedding the detailed correction table.

**Why:** Free-text filenames, column names, custom rules and cell values can contain sensitive information even when known protected columns are masked.

**How to apply:** Use the masked checker view for detailed review; keep the simulated request limited to version references, application-owned fix categories, counts and operational guidance.
