-- Development schema source. Apply to development only.
-- Managed production schema changes are applied through Publish, never at startup.
CREATE TABLE IF NOT EXISTS inspection_history (
    id uuid PRIMARY KEY,
    owner_key char(64) NOT NULL CHECK (owner_key ~ '^[0-9a-f]{64}$'),
    run_key uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL DEFAULT (now() + interval '30 days'),
    row_count bigint NOT NULL CHECK (row_count >= 0),
    column_count integer NOT NULL CHECK (column_count >= 0),
    finding_count bigint NOT NULL CHECK (finding_count >= 0),
    duplicate_count bigint NOT NULL CHECK (duplicate_count >= 0),
    health_score integer NOT NULL CHECK (health_score BETWEEN 0 AND 100),
    missing_count bigint NOT NULL CHECK (missing_count >= 0),
    email_count bigint NOT NULL CHECK (email_count >= 0),
    date_count bigint NOT NULL CHECK (date_count >= 0),
    outlier_count bigint NOT NULL CHECK (outlier_count >= 0),
    custom_count bigint NOT NULL CHECK (custom_count >= 0),
    enabled_checks text[] NOT NULL,
    CHECK (enabled_checks <@ ARRAY['missing','duplicates','email','date','outliers','custom']::text[]),
    CHECK (expires_at = created_at + interval '30 days'),
    UNIQUE (owner_key, run_key)
);
CREATE INDEX IF NOT EXISTS inspection_history_owner_created
    ON inspection_history (owner_key, created_at DESC);
CREATE INDEX IF NOT EXISTS inspection_history_expiry ON inspection_history (expires_at);
