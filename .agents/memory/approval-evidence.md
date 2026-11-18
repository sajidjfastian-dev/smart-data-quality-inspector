---
name: Private approval evidence
description: Session-only governance attachments must not leak into public demo history.
---
Ticket and CAB approval evidence is optional and private to the browser session, bound to the exact request revision and snapshot.

**Why:** The user requested evidence for governance, but shared sample requests are publicly persisted and arbitrary attachments may contain confidential information.

**How to apply:** Keep evidence bytes and filenames outside shared records; disclose logout/session-loss deletion and the lack of a durable audit archive. Adding permanent retention requires explicit authorization and protected storage rather than expanding the sample database.
