ALTER TABLE market_import_runs
    ADD COLUMN IF NOT EXISTS duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    ADD COLUMN IF NOT EXISTS source_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS stage_metrics JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE backtest_runs
    ADD COLUMN IF NOT EXISTS duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    ADD COLUMN IF NOT EXISTS last_completed_session DATE,
    ADD COLUMN IF NOT EXISTS resumed_from_run_id UUID REFERENCES backtest_runs (id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS operational_events (
    id UUID PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    level TEXT NOT NULL CHECK (level IN ('INFO', 'WARNING', 'ERROR')),
    event_type TEXT NOT NULL,
    run_id UUID,
    job_type TEXT,
    isin TEXT,
    symbol TEXT,
    requested_from_date DATE,
    requested_to_date DATE,
    attempt INTEGER CHECK (attempt IS NULL OR attempt > 0),
    duration_ms BIGINT CHECK (duration_ms IS NULL OR duration_ms >= 0),
    row_count BIGINT CHECK (row_count IS NULL OR row_count >= 0),
    source_status TEXT,
    error_class TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS operational_events_time_idx
    ON operational_events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS operational_events_run_idx
    ON operational_events (run_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS operational_events_error_idx
    ON operational_events (level, error_class, occurred_at DESC)
    WHERE level = 'ERROR';

CREATE TABLE IF NOT EXISTS data_quality_anomalies (
    id UUID PRIMARY KEY,
    anomaly_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR')),
    isin TEXT,
    trading_date DATE,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    UNIQUE (anomaly_type, isin, trading_date)
);

CREATE INDEX IF NOT EXISTS data_quality_anomalies_open_idx
    ON data_quality_anomalies (severity, detected_at DESC)
    WHERE resolved_at IS NULL;
