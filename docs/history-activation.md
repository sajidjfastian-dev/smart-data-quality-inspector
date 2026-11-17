# Inspection history activation checklist

Status: prepared, not active. No history is saved while SSO setup is pending.

## Scope approved by the user

- Inspection summaries only, retained for 30 days.
- Organisation SSO; provider connection deferred.
- No uploaded files or raw values retained.

## Identity and access

1. Obtain the approved organisation IdP, protocol (OIDC or SAML), issuer and tenant/access policy from IT.
2. Use a supported, server-verified authentication integration. Configure credentials through secrets management, not code or chat.
3. Implement `current_history_owner()` using verified issuer + immutable subject. Use `owner_key_for_verified_identity()` only after verification. Do not trust user-entered identity, browser state, or arbitrary proxy headers.
4. Verify restricted tenant/group access, login, logout, session expiry and two-user isolation before activation. Keep history access denied on any verification/configuration failure.

## Storage and retention

- Development schema: `db/inspection_history.sql`. Production uses managed Publish schema synchronization; no startup or deploy-command DDL.
- All reads/writes/deletes are scoped to a verified owner. No user-supplied record labels are stored. Summary contents are fixed aggregate numeric fields and allowlisted checks.
- Every saved record expires after 30 days; repeat saves of the same scan do not extend its retention.
- Schedule `python scripts/purge_inspection_history.py` through an approved scheduler before activation. Verify it runs without application traffic, reports failures, and removes expired rows. A daily schedule can leave expired physical rows for up to one additional day; choose a tighter interval if policy demands it. Expired summaries must never be returned to users.
- Review physical deletion requirements, infrastructure backup retention and legal holds with the security owner. Do not claim exact physical deletion at the expiry instant or regulatory certification.

## Validation

Run `python -m unittest discover -s tests -p 'test_inspection_history.py' -v`.
Database tests use a temporary table and roll back test data; they do not persist inspection records.

Before enabling SSO, add real provider login/logout/session-expiry tests and verify the deployed retention job. UI setup-state tests and repository tests do not certify the provider integration.
