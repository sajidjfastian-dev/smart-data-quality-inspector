---
name: Reusable business rules
description: Configure business rules before loading data and reuse them across datasets.
---
Business rules are defined first in Settings after login, independently of any uploaded file, and reused across data sources rather than being limited to the public sample or a single dataset.

**Why:** The user clarified: “Business rule will be applied on any type of data. So first rules will be defined as part of setting”.

**How to apply:** Keep configuration available before upload. Evaluate applicability for each incoming dataset; show missing fields and incompatible types instead of silently ignoring them or forcing unsafe corrections. Review & fix should display all configured rules, including disabled and non-applicable ones. Preserve the existing session-only scope unless the user explicitly requests durable rule storage.
