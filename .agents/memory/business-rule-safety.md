---
name: Business-rule correction boundaries
description: Why session-wide business rules use exact columns and conservative correction proposals.
---
Pre-upload business rules match exact column names, not inferred or similar names.

**Why:** The user wants rules immediately after login, before there is a schema to inspect. Fuzzy matches could apply business policy to the wrong field in another file.

**How to apply:** Show missing-column/type conflicts instead of silently guessing a target. Clear in-memory rules on logout without deleting the account's saved definitions.

Keep check-only constraints separate from automatic corrections. An explicit mapping or normalization must not violate another constraint on the same column; conflicting proposals remain unchanged.

**Why:** A numeric limit describes acceptable data, not permission to invent a business value or clamp facts merely to pass inspection.

**How to apply:** Re-scan the corrected copy and preserve the source. Custom rule parameters can contain protected values, so redact them in assistant output and model context for protected columns. Custom rules outside a shared sample's contract require a private copy.
