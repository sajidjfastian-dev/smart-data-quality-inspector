# External Server Deployment Guide & Runbook

Smart Data Quality Inspector · Prepared 2026-11-18

## 1. Scope and release decision

This guide is for deploying the current repository to a separate Linux server. All commands below are examples for that external server—not commands executed in the Replit workspace. Replace hostnames, account names and paths through your organization's release process.

**Deployment is not production certification.** The current application processes uploaded files and generates approved downloads, but sign-in, reviewer identity and service-desk tickets remain simulated. Do not expose it publicly for sensitive organizational data as if it had real application authentication.

Choose one release mode:

- **Restricted demonstration:** private network or authenticated access proxy; authorized demonstration files only; visibly simulated identity/tickets; session-only private uploads.
- **Organizational production:** blocked until real identity is integrated into application authorization, independent reviewer permissions are enforced, privacy/security owners approve the workflow, and release verification passes. A proxy login alone does not turn the hardcoded application identity into a secure user identity.

The agreed final action is **Download approved file**, following request approval, ticket approval and CAB approval. There are no source-system writes. Downloads retain configured privacy masking. Approval does not mean every finding has been resolved.

## 2. Architecture and session behavior

Browser → HTTPS/Nginx → one Streamlit service on 127.0.0.1:5000 → PostgreSQL over a private connection.

- Start `serve.py`, not `app.py`. The entrypoint includes the read-only sample API and initialization lifecycle.
- Private files, requests and conversations live in process/session memory. Logout clears them; restarts, session expiry or lost sessions can also lose work.
- PostgreSQL stores the synthetic sample catalog and shared synthetic requests, not private uploaded files.
- The sample API `/api/demo/sample` intentionally returns synthetic data and must never expose uploads.
- Begin with one application instance. Multiple instances require session affinity and verification of WebSocket, upload and download routing. They do not solve loss of session-only data.
- Arrange maintenance windows: application restarts interrupt active review sessions. Ask users to download required outputs before the window.

## 3. Prerequisites

- Supported Linux distribution with systemd, Nginx and Python **3.12**.
- A dedicated non-root service account, here `dqi`.
- DNS hostname, TLS certificate and renewal process.
- Supported PostgreSQL service. Validate the chosen server version in staging; no server version was certified by the browser checks.
- Private database connectivity, encrypted transport and organization-approved secret management.
- Release artifact containing all application modules, `assets/`, `.streamlit/`, `scripts/`, `sample_data/`, `demo_media/`, `requirements.txt` and applicable schema files.
- Exclude `.git`, `.pythonlibs`, caches, logs, credentials, uploaded files and `attached_assets` from the deployment artifact. Keep tests in the staging/CI artifact for verification.
- Start staging sizing around 2–4 vCPU and 8 GB RAM, then measure representative concurrency. This is a starting estimate, not a supported capacity claim.

**Memory warning:** configured `maxUploadSize` is 500 MB. Parsing, original/fixed snapshots, findings and downloads can use many times the uploaded size. Do not advertise 500 MB as safe capacity without load testing. Set a smaller approved limit consistently in Streamlit and Nginx if necessary.

**Do not use the existing Dockerfile unchanged:** it references Python 3.15, starts `app.py`, and copies only part of the current application. Container deployment requires a separately updated and verified image. This runbook uses systemd instead.

## 4. Prepare an immutable release

Example layout:

```text
/opt/dqi/releases/2026-11-18-01/   application + release-specific .venv
/opt/dqi/current                 symlink to active release
/etc/dqi/runtime.env             protected environment file
```

Provision the service user and directories through your server administration process. Extract the reviewed release, then on the external server:

```bash
cd /opt/dqi/releases/2026-11-18-01
python3.12 -m venv .venv
.venv/bin/python -m pip install --requirement requirements.txt
.venv/bin/python -m pip check
```

Use the exact pinned requirements. Confirm their availability in the approved package registry; do not silently replace unavailable versions. Record release identifier, dependency manifest and checksums. For reproducible/offline releases, build and retain an approved wheelhouse with integrity checks in CI.

The code relies on Streamlit's `st.App` API. Installing an older Streamlit version is not a valid workaround.

## 5. Secrets and configuration

Provision credentials directly through an approved secret manager or root-managed environment file. Do not place secrets in source control, browser fields, screenshots or shell command history.

| Setting | Requirement |
|---|---|
| `DATABASE_URL` | PostgreSQL connection used by the existing synthetic store; include TLS parameters appropriate to your DB provider. Prefer certificate/hostname verification for remote databases. |
| Database CA certificate | Install and make readable to the service where required by the connection configuration. |
| `STREAMLIT_SERVER_COOKIE_SECRET` | Provision a unique strong secret using the secret manager; use consistently for a deployed service. This is not authentication. |
| Organization SSO settings | Not currently implemented as real identity; no environment variable alone enables secure application SSO. |
| Optional model endpoint | Not needed for local assistant operation. External AI requires separately approved integration, data-sharing controls and testing. |

Protect `/etc/dqi/runtime.env` with root ownership and mode 0600. A system-level systemd service can load that file before switching to the unprivileged service account. The app does not need permission to read the file directly.

Do not treat the workspace's `SESSION_SECRET` as a switch that enables production login.

## 6. PostgreSQL initialization outside Replit

Automatic hosting-platform schema management does not run on an independent server.

Have a DBA review `scripts/demo_schema.sql`. Although its header describes development/platform setup, it contains the four `dq_demo_*` table definitions required by the external deployment. Apply the reviewed schema through the external production migration process using a migration account—not the runtime account.

Example, using DBA-provisioned PostgreSQL service definitions:

```bash
# First installation or reviewed migration window only.
PGSERVICE=dqi_migration psql --set=ON_ERROR_STOP=1 \
  --single-transaction --file=scripts/demo_schema.sql
```

Required tables:

```text
dq_demo_sessions
dq_demo_rows
dq_demo_catalog
dq_demo_requests
```

Grant the runtime role database CONNECT, schema USAGE, and SELECT/INSERT/UPDATE on these four tables. Do not grant superuser or general schema-creation privileges. The current startup seed needs table access even though it does not execute schema changes.

Populate only the synthetic sample using the documented data-only command, with `DATABASE_URL` supplied securely:

```bash
.venv/bin/python scripts/seed_demo.py
```

Expected first-install result: **520 synthetic sample rows and 20 synthetic requests**. The seed is idempotent and preserves an existing catalog. Startup also attempts this data-only seed. Do not run `--development-schema` against production.

`CREATE TABLE IF NOT EXISTS` does not migrate changed columns. Future schema changes require explicit versioned migrations, backups, compatibility review and a rollback plan.

`db/inspection_history.sql` and `docs/history-activation.md` describe a separate history capability. Do not activate it merely to make private uploads persistent; real identity/ownership requirements and retention approval still apply.

## 7. systemd service

Create `/etc/systemd/system/dqi.service`:

```ini
[Unit]
Description=Smart Data Quality Inspector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dqi
Group=dqi
WorkingDirectory=/opt/dqi/current
EnvironmentFile=/etc/dqi/runtime.env
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/opt/dqi/current/.venv/bin/python -m streamlit run serve.py --server.address=127.0.0.1 --server.port=5000 --server.headless=true --server.enableCORS=true --server.enableXsrfProtection=true --server.corsAllowedOrigins=https://quality.example.org
Restart=on-failure
RestartSec=5
TimeoutStopSec=45
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Replace `https://quality.example.org` with the exact approved origin. Keep CORS/XSRF protection enabled. Prefer root-owned, read-only release files with only explicitly needed runtime directories writable by `dqi`. Add further systemd hardening only after staging verification.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dqi
sudo systemctl status dqi --no-pager
curl --fail http://127.0.0.1:5000/_stcore/health
```

## 8. Nginx and TLS

Example Nginx configuration. Put the `map` in the `http` context; install certificates using your organization's process before enabling TLS.

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

server {
    listen 80;
    server_name quality.example.org;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name quality.example.org;
    ssl_certificate     /etc/ssl/dqi/fullchain.pem;
    ssl_certificate_key /etc/ssl/dqi/private.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Allows multipart overhead above Streamlit's configured 500 MB limit.
    # Reduce both limits to your approved, load-tested upload policy.
    client_max_body_size 520m;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_buffering off;
    }
}
```

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Bind application port 5000 to loopback; expose only approved HTTPS access. Use VPN/network restrictions or an access proxy for the demo. Restrict database access to the application and administration networks. Review access-log retention; do not log request bodies, uploaded values, model payloads or credentials.

## 9. Release checklist

### Before deploying

- [ ] Release mode and data classification approved.
- [ ] Production identity and independent authorization implemented, or demonstration access restricted.
- [ ] Correct artifact, Python 3.12 and exact dependencies verified.
- [ ] Secrets provisioned outside the artifact and rotated where needed.
- [ ] Database schema reviewed, backup taken and restore procedure verified.
- [ ] Upload limit and representative concurrent memory usage tested.
- [ ] DNS, certificates, firewall and WebSocket routing configured.
- [ ] Privacy masking, exports, optional AI egress and retention policies approved.
- [ ] Maintenance window, owners, rollback target and stop/go criteria recorded.

### At pre-publish verification

The user's preference is to run unit tests at release time, rather than during routine edits. Run them now in staging/CI—not against a live production database:

```bash
.venv/bin/python -m pip check
.venv/bin/python -m unittest discover -s tests -v
```

Database-dependent cases need a dedicated disposable test database and their documented fixtures. Never point the test environment at production or waive failing checks without recording the reason and risk.

Browser scripts use development-specific environment/executable paths. `scripts/check_judges_flow.py` records the exercised flow, but is not portable unchanged to arbitrary servers; adapt only its base URL and browser executable in the staging test harness. Do not install a test browser on production merely to run it.

### Post-deployment smoke check

- [ ] HTTPS works without warnings; HTTP redirects; direct port 5000 is inaccessible externally.
- [ ] `/_stcore/health` succeeds. This checks the server, not DB/application readiness.
- [ ] `/api/demo/sample` succeeds and declares synthetic data with at least 500 rows.
- [ ] CSV and XLSX upload with permitted test data succeed.
- [ ] Enabled/disabled quality controls and one custom rule affect findings correctly.
- [ ] Overview, Issue log and data views render without errors.
- [ ] Fixes match expectations; corrected cells have explanatory hover text.
- [ ] Side-by-side review masks protected columns.
- [ ] Submission → request review → ticket approval → CAB approval unlocks the final approved download.
- [ ] Download matches the reviewed revision; rejected, unapproved, superseded and historical revisions cannot use the final approved download.
- [ ] Logout clears private uploads and private requests.
- [ ] Local assistant gives dataset-grounded answers without an external model.
- [ ] English/Arabic, projector-sized views, loading indicator and date formatting work.
- [ ] No browser/server exceptions; resource usage stays within agreed limits.

Ordinary review exports are not proof of final approval. Use the request-details **Download approved file** action to demonstrate the approval-gated handoff.

## 10. Operations runbook

**Daily:** check service health, DB/sample readiness, error rate, memory/CPU/disk, certificate expiry and backup outcomes. Set thresholds after load testing. Verify both application and database readiness; startup can keep private inspection available while synthetic DB features are unavailable.

```bash
sudo systemctl status dqi --no-pager
sudo journalctl -u dqi --since "30 minutes ago" --no-pager
curl --fail https://quality.example.org/_stcore/health
curl --fail https://quality.example.org/api/demo/sample --output /dev/null
```

| Symptom | First checks and safe response |
|---|---|
| 502/504 or blank page | Check systemd logs, loopback port, Nginx upstream and certificate. Avoid repeated restarts without diagnosing. |
| Disconnections / stuck processing | Verify WebSocket Upgrade headers, proxy timeouts, memory pressure and single-instance routing. |
| Sample API 503 / shared requests absent | Check private DB connectivity, TLS, permissions, schema and seed. Do not delete/reseed records to hide a failure. |
| Upload 413 | Compare Nginx limit with Streamlit policy; do not raise limits without a memory test. |
| Memory exhaustion | Restrict new uploads, capture non-sensitive diagnostics, reduce concurrency/limits; warn users before restart. |
| Approved download unavailable | Check latest revision, review acknowledgement, privacy status, ticket/CAB approvals and unchanged snapshot. Never bypass these checks. |
| Private request disappeared | Confirm logout/restart/session loss. Private in-memory data is not recoverable from the synthetic database. |
| Bad-origin / XSRF errors | Correct HTTPS origin and proxy headers. Do not disable protections as the fix. |

**Incident response:** restrict access if exposure is suspected; preserve sanitized logs and release details; notify the named security/data owner; rotate affected credentials through the secret manager; restore service only after the incident owner approves. Do not upload sensitive diagnostic files to third-party tools.

## 11. Backup and recovery

Set RPO, RTO, backup retention, encryption and restore-test frequency with the service owner. Back up PostgreSQL and deployment configuration; retain immutable release artifacts. Private session data is intentionally outside DB backups.

```bash
# DBA-provisioned service definition; protected, encrypted backup destination.
PGSERVICE=dqi_backup pg_dump --format=custom \
  --file=/secure-backups/dqi-2026-11-18.dump

# Restore rehearsal ONLY: isolated, newly provisioned empty database.
PGSERVICE=dqi_restore_test pg_restore --exit-on-error --no-owner \
  --dbname=dqi_restore_test /secure-backups/dqi-2026-11-18.dump
```

A backup file existing is not proof of recoverability. Verify restored row counts, catalog loading and a controlled request workflow. Apply correct ownership/grants on the restore target.

## 12. Upgrade and rollback

1. Stage a new release and its own dependencies; run release checks and schema compatibility review.
2. Notify users and drain access. Session-only work will not survive application replacement.
3. Back up DB/configuration and record the currently active release.
4. Apply approved backward-compatible migrations, then atomically switch the release symlink.
5. Restart once, run smoke checks and monitor before reopening access.

Example symlink switch, after the release has passed staging:

```bash
sudo ln -s /opt/dqi/releases/2026-11-18-01 /opt/dqi/current.next
sudo mv -Tf /opt/dqi/current.next /opt/dqi/current
sudo systemctl restart dqi
```

**Rollback trigger:** failed approval/download checks, sustained server errors, corrupted output or unacceptable resource usage.

Stop admitting new sessions; restore the previous compatible release symlink and restart. A code rollback does not roll back schema/data. If schema changed incompatibly, follow the DBA-approved recovery plan rather than blindly restoring over live data. Database restore may lose writes since the backup and requires explicit approval. Private session state cannot be recovered by rollback.

## 13. Go-live handover record

Record: release ID, server/environment, deployment owner, application owner, database owner, security approver, support contact, approved data classes, auth mode, domain/certificate owner, RPO/RTO, backup location, monitoring links, rollback release, test evidence, unresolved exceptions and final approval.

**Current evidence:** the repository's presentation workflow was browser-checked with controlled uploads. The Nginx/systemd examples and external-host deployment have not been executed on your target infrastructure. External production readiness must be demonstrated there before go-live.
