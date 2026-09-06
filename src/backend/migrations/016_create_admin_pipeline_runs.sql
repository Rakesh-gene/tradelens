CREATE TABLE IF NOT EXISTS admin_pipeline_runs (
    id UUID PRIMARY KEY,
    requested_by UUID NOT NULL REFERENCES users (id),
    requested_from_date DATE NOT NULL,
    requested_to_date DATE NOT NULL,
    versions JSONB NOT NULL DEFAULT '{}'::JSONB,
    force_refresh BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL,
    securities_total INTEGER NOT NULL DEFAULT 0 CHECK (securities_total >= 0),
    securities_completed INTEGER NOT NULL DEFAULT 0 CHECK (securities_completed >= 0),
    securities_failed INTEGER NOT NULL DEFAULT 0 CHECK (securities_failed >= 0),
    error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    CHECK (requested_from_date <= requested_to_date)
);

CREATE INDEX IF NOT EXISTS admin_pipeline_runs_created_at_idx
    ON admin_pipeline_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS admin_pipeline_run_items (
    run_id UUID NOT NULL REFERENCES admin_pipeline_runs (id) ON DELETE CASCADE,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    current_stage TEXT NOT NULL,
    history_run_id UUID REFERENCES market_import_runs (id) ON DELETE SET NULL,
    pattern_run_id UUID REFERENCES market_import_runs (id) ON DELETE SET NULL,
    rows_downloaded BIGINT NOT NULL DEFAULT 0 CHECK (rows_downloaded >= 0),
    candidates_detected INTEGER NOT NULL DEFAULT 0 CHECK (candidates_detected >= 0),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (run_id, isin)
);

CREATE INDEX IF NOT EXISTS admin_pipeline_run_items_status_idx
    ON admin_pipeline_run_items (status, updated_at DESC);
