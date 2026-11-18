-- Development/post-merge schema only. Publishing manages production schema.
CREATE TABLE IF NOT EXISTS dq_auth_records (
    token_hash text PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('login', 'session')),
    payload jsonb NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS dq_auth_records_expiry ON dq_auth_records(expires_at);
CREATE TABLE IF NOT EXISTS dq_demo_sessions (
    id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    synthetic_history boolean NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS dq_demo_rows (
    source_id text NOT NULL,
    row_number integer NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY(source_id,row_number)
);
CREATE TABLE IF NOT EXISTS dq_demo_catalog (
    id text PRIMARY KEY,
    payload jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS dq_demo_requests (
    reference text PRIMARY KEY,
    session_id text NOT NULL REFERENCES dq_demo_sessions(id),
    payload jsonb NOT NULL,
    version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
