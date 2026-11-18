---
name: Synthetic persistence boundary
description: Why demo persistence is restricted to trusted examples and how to preserve that boundary.
---
Shared persistence must require server-issued sample provenance. A matching filename, user-editable flag, or byte-identical uploaded dataset is not proof that an import is safe to persist.

**Why:** The user approved stored sample examples (now genuine public data with labelled demo defects), not storage of arbitrary uploads. A private import can imitate any sample label or contain personal text in custom rules and rejection reasons.

**How to apply:** Reconstruct shared payloads from the server-owned catalog and allowlisted metadata. Custom free text belongs in an explicitly session-only copy. Keep unsupported changes visible rather than silently claiming they were saved.

Use canonical ordering when sealing structured snapshot metadata that passes through JSONB.

**Why:** PostgreSQL JSONB can reorder dictionary keys; hashing Python dictionary representations can incorrectly invalidate an unchanged stored snapshot.

**How to apply:** Serialize mappings deterministically before hashing and test the actual database round trip, not just in-memory copies.

Financial sample frames require round-trip-safe decimal parsing while historical snapshot codecs must remain unchanged.

**Why:** Default pandas JSON reading can shift a decimal by one floating-point bit, invalidating the exact-version fingerprint even when the displayed rate is identical. Changing the legacy decoder would invalidate already approved history.

**How to apply:** Version the frame representation for new trusted public samples and verify exact fingerprints after storage, not only approximate dataframe equality.
