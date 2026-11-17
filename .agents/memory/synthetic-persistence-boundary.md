---
name: Synthetic persistence boundary
description: Why demo persistence is restricted to trusted examples and how to preserve that boundary.
---
Shared persistence must require server-issued sample provenance. A matching filename, user-editable flag, or byte-identical uploaded dataset is not proof that an import is safe to persist.

**Why:** The user approved stored synthetic examples, not storage of arbitrary uploads. A private import can imitate any sample label or contain personal text in custom rules and rejection reasons.

**How to apply:** Reconstruct shared payloads from the server-owned catalog and allowlisted metadata. Custom free text belongs in an explicitly session-only copy. Keep unsupported changes visible rather than silently claiming they were saved.

Use canonical ordering when sealing structured snapshot metadata that passes through JSONB.

**Why:** PostgreSQL JSONB can reorder dictionary keys; hashing Python dictionary representations can incorrectly invalidate an unchanged stored snapshot.

**How to apply:** Serialize mappings deterministically before hashing and test the actual database round trip, not just in-memory copies.
