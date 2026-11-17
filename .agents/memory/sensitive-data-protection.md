---
name: Sensitive data protection
description: User-selected scope for protecting sensitive data in the application.
---

Mask sensitive data across screens, downloads, and external API and model requests. Protect names and contact details, IDs and account numbers, payment card numbers, and manually selected columns.

**Why:** The user explicitly selected this scope and these categories.

**How to apply:** Preserve the original data for inspection, acknowledge that automatic detection can miss sensitive information, and do not represent masking alone as regulatory compliance.

The user requested that “I reviewed all columns for sensitive data” be checked by default.

**Why:** The user explicitly requested this default rather than a mandatory manual confirmation.

**How to apply:** Keep automatic and manually selected column masking active. Allow users to uncheck the review checkbox; do not reset their explicit choice on reruns. A default check is not evidence of an actual human review.

For persistent upload history, retain inspection summaries only for 30 days, not original files or masked file copies.

**Why:** The user explicitly chose summaries-only history and a 30-day retention period.

**How to apply:** Keep stored summaries free of raw cell values and do not expand storage scope without asking.

Use organisation SSO for private history; the user chose to set up its connection later. Keep saving and viewing history disabled until that connection is securely configured.

**Why:** The user chose organisation sign-in and explicitly deferred the SSO connection.

**How to apply:** Do not substitute Replit accounts, shared history, anonymous browser identifiers, or self-asserted identities.
