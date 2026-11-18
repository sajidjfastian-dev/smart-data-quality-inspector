---
name: Streamlit authentication boundary
description: Authenticate WebSocket reconnection before Streamlit can execute retained callbacks.
---
Enforce account ownership at the WebSocket connection and message boundary, not just at the top of the Streamlit application script.

**Why:** Streamlit runs preserved widget callbacks before the script. A reconnect that reuses another workspace can otherwise execute those callbacks with the old session's credentials before script-level synchronization clears them.

**How to apply:** Keep connection-verified runtime identity, reconnect ownership and per-message revocation checks together. Strip caller-supplied trusted identity headers. Exercise a real Streamlit runtime with an outstanding widget callback when changing these boundaries.
