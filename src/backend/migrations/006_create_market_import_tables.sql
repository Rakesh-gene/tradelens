CREATE TABLE IF NOT EXISTS market_import_runs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    requested_from_date DATE,
    requested_to_date DATE,
    configuration JSONB NOT NULL DEFAULT '{}'::JSONB,
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    securities_total INTEGER NOT NULL DEFAULT 0 CHECK (securities_total >= 0),
    securities_completed INTEGER NOT NULL DEFAULT 0 CHECK (securities_completed >= 0),
    securities_failed INTEGER NOT NULL DEFAULT 0 CHECK (securities_failed >= 0),
    rows_downloaded BIGINT NOT NULL DEFAULT 0 CHECK (rows_downloaded >= 0),
    rows_inserted BIGINT NOT NULL DEFAULT 0 CHECK (rows_inserted >= 0),
    rows_updated BIGINT NOT NULL DEFAULT 0 CHECK (rows_updated >= 0),
    rows_rejected BIGINT NOT NULL DEFAULT 0 CHECK (rows_rejected >= 0),
    error_summary TEXT,
    initiated_by TEXT NOT NULL CHECK (initiated_by IN ('manual', 'scheduler', 'recovery')),
    CHECK (requested_from_date IS NULL OR requested_to_date IS NULL OR requested_from_date <= requested_to_date)
);

CREATE INDEX IF NOT EXISTS market_import_runs_status_started_at_idx
    ON market_import_runs (status, started_at DESC);

CREATE TABLE IF NOT EXISTS security_import_checkpoints (
    job_type TEXT NOT NULL,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    earliest_successful_trading_date DATE,
    latest_successful_trading_date DATE,
    last_attempted_from_date DATE,
    last_attempted_to_date DATE,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    last_error TEXT,
    last_successful_run_id UUID REFERENCES market_import_runs (id) ON DELETE SET NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_type, isin),
    CHECK (
        earliest_successful_trading_date IS NULL
        OR latest_successful_trading_date IS NULL
        OR earliest_successful_trading_date <= latest_successful_trading_date
    ),
    CHECK (
        last_attempted_from_date IS NULL
        OR last_attempted_to_date IS NULL
        OR last_attempted_from_date <= last_attempted_to_date
    )
);

CREATE INDEX IF NOT EXISTS security_import_checkpoints_status_idx
    ON security_import_checkpoints (status, updated_at DESC);
