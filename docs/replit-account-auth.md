# Verified Replit accounts

## What changed

“Continue with SSO” opens the Replit account sign-in flow. The application
validates the authorization code, PKCE verifier, state, nonce, issuer, audience,
signature and ID-token expiry. It displays the verified first/last name, falling
back to the account username. Request ownership uses the stable `sub`, never
the name or request headers.

This is **Replit account authentication**, not organisation/employee SSO or a
proof of a user's department or authority to approve production changes.
Request review, service-desk tickets, CAB and implementation remain explicit
simulations. There is no real production write.

## Configuration and schema

- Run the existing development/post-merge setup. Its development schema includes
  `dq_auth_records`. Do not run schema DDL at application startup.
- The normal Replit Publish schema step carries this table/index to production.
  No production migration script is provided.
- `REPL_ID` supplies the public OIDC client ID. `REPLIT_AUTH_CLIENT_ID` can
  explicitly override it when running with a separately registered Replit client.
- `REPLIT_DEV_DOMAIN` supplies the allowlisted preview host automatically.
- `AUTH_PUBLIC_ORIGIN` must be the exact HTTPS origin of the published app,
  without a path or trailing slash. It is configured in `.replit` for this
  project's current published origin. Update it if the published domain changes.
- Callback paths are `/auth/callback` on those two origins. They must be accepted
  by the Replit Auth client. For another hosting server/domain, obtain a supported
  Replit client/redirect registration first; do not assume this project's client
  accepts arbitrary domains.
- The issuer is pinned to `https://replit.com/oidc`. No test-issuer switch or
  production login bypass is included. This public client uses PKCE and token
  endpoint authentication `none`; no client secret is requested or embedded.
- Retain HTTPS, Streamlit XSRF protection, and the normal WebSocket reverse proxy.
  The proxy must preserve the public Host header. Forwarded-host/redirect query
  parameters do not establish trusted callback origins.

## Sessions and data

- Browser cookies are opaque, Secure, HttpOnly, SameSite=Lax and host-only.
  Database session keys are SHA-256 hashes; no provider access/refresh/ID tokens
  are persisted. Login transactions are one-use and expire after ten minutes.
- Sessions last at most one hour, capped by ID-token expiry. There is no silent
  refresh or “remember me”. Sign in again when they expire.
- Logout revokes the app session in PostgreSQL and clears the workspace. It does
  not sign the user out of their Replit account globally. Starting another login
  revokes the prior app session, including other tabs using it.
- A 30-second heartbeat clears expired/revoked workspaces; protected workflow
  actions and download preparation recheck the session. The Streamlit media and
  upload endpoints reject absent, expired and revoked account sessions.
- WebSocket reconnects must match the account session that owns the Streamlit
  workspace before any widget callback can run. Every incoming authenticated
  message rechecks revocation/expiry. A middleware-generated runtime identity
  also protects Streamlit's native session matching; caller-supplied identity
  headers are stripped. Keep the configured `trustedUserHeaders` mapping and
  authentication middleware together.
- Private uploads, corrections, evidence, rules and assistant state stay in
  Streamlit memory and are cleared on account change/logout/expiry. They are not
  resurrected from database history. Approved files already downloaded cannot
  be withdrawn from a user's computer.
- Canonical public-data requests may be persisted, with account subject ownership.
  Original shared sample records are separate read-only examples. A matching
  display name never gives a new account ownership of historical records.
- Expired auth records are removed on the next successful login/session insert.
  Operators should retain normal database access controls and backup policies.

## Verification and remaining live check

Focused checks exercise signed OIDC responses, replay/state/nonce/issuer/audience/
expiry rejection, matching-name isolation, profile fallback, account changes,
revocation, approval order and masking/snapshot safeguards.
The real-runtime WebSocket regression also attempts cross-account and anonymous
session resumption with a pending callback, and revokes an active connection.
Run it in a fresh process with
`PYTHONPATH=.:tests python -m unittest tests.test_account_websocket_runtime`.

The preview authorization route was checked against the live Replit discovery
and authorization endpoints. No real person's interactive login was completed
by the agent, and the authenticated screen was not visually verified with a live
account. Production was not changed or tested from this task.

Before enabling this version for users, complete one interactive login on each
configured origin and verify:

1. The sidebar shows the actual account's verified name/username.
2. Two distinct Replit accounts cannot open, edit, approve or download each
   other's personal requests, including accounts with matching display names.
3. Public examples appear only in the explicitly labelled read-only view.
4. Logout clears a private upload and evidence; refresh/back or another open tab
   cannot restore them. Repeat after session expiry and account switching.
5. Approved download still requires the exact reviewed revision and ticket/CAB
   steps; masked data stays masked.

If callback registration fails, keep sign-in closed and correct client/origin
setup. Never restore the pretend fixed-user login as a fallback.
