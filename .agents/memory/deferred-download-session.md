---
name: Deferred download session access
description: Streamlit download workers cannot safely read the session-state proxy.
---
Authorize session-bound downloads on the Streamlit script thread, not inside a deferred download callable.

**Why:** Deferred download callables run on background workers without ScriptRunContext; reading the session-state proxy there yields an empty session and breaks authorization.

**How to apply:** Check the current user, latest revision, immutable snapshot and approvals before supplying approved download bytes. Do not remove authorization to make a deferred callback work or capture credentials in a callback.

Use materialized download bytes with account-scoped Streamlit media authorization.

**Why:** Streamlit 1.67 leaves a deferred download's generated file ID out of its session/coordinate map. The browser receives that URL over WebSocket, not an HTTP redirect, so intercepting redirects cannot bind it to an owner.

**How to apply:** Do not restore callable download payloads without designing and testing ownership for the generated file using the real framework media manager. Keep expiry, revocation and cross-account denial intact.
