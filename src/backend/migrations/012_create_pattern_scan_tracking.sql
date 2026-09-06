ALTER TABLE market_import_runs
    ADD COLUMN IF NOT EXISTS metrics JSONB NOT NULL DEFAULT '{}'::JSONB;

CREATE TABLE IF NOT EXISTS pattern_scan_failures (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES market_import_runs (id) ON DELETE CASCADE,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    as_of_date DATE NOT NULL,
    stage TEXT NOT NULL,
    error_type TEXT NOT NULL,
    error_message TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS pattern_scan_failures_run_idx
    ON pattern_scan_failures (run_id, isin, as_of_date);
