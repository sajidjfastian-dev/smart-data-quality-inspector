---
name: Reusable business rules
description: Configure business rules before loading data and reuse them across datasets.
---
Business rules are defined first in Settings after login, independently of any uploaded file, and reused across data sources rather than being limited to the public sample or a single dataset.

**Why:** The user clarified: “Business rule will be applied on any type of data. So first rules will be defined as part of setting”.

**How to apply:** Keep configuration available before upload. Evaluate applicability for each incoming dataset; show missing fields and incompatible types instead of silently ignoring them or forcing unsafe corrections. Review & fix should display all configured rules, including disabled and non-applicable ones. Preserve the existing session-only scope unless the user explicitly requests durable rule storage.

The user considers inspection checks and business rules one combined "Business rules" experience, with the same set visible in Review & fix.

**Why:** The user wants to define controls such as duplicate removal and format checks in one place, rather than distinguish inspection checks from business rules.

**How to apply:** Present built-in controls and custom rules together while keeping their actual check and correction capabilities clear; do not imply that check-only findings can be automatically corrected.

All business rules are selected by default. Users can deselect rules for the current file in Review & fix and reapply corrections without changing the shared rule definitions.

**Why:** The user wants Settings to define rules and Review & fix to provide a simple, file-specific choice.

**How to apply:** Show the full rule list there, keep selections independent per file, and invalidate the previous corrected preview and approval when choices change.
