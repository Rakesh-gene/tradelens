CREATE TABLE IF NOT EXISTS backtest_runs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),
    requested_from_date DATE NOT NULL,
    requested_to_date DATE NOT NULL,
    universe JSONB NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    engine_version TEXT NOT NULL,
    configuration_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    adjustment_version TEXT NOT NULL,
    point_in_time_policy JSONB NOT NULL,
    minimum_sample_size INTEGER NOT NULL DEFAULT 30 CHECK (minimum_sample_size > 0),
    sessions_processed INTEGER NOT NULL DEFAULT 0 CHECK (sessions_processed >= 0),
    securities_evaluated INTEGER NOT NULL DEFAULT 0 CHECK (securities_evaluated >= 0),
    entries_recorded INTEGER NOT NULL DEFAULT 0 CHECK (entries_recorded >= 0),
    error_message TEXT,
    requested_by UUID REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (requested_from_date <= requested_to_date)
);

CREATE INDEX IF NOT EXISTS backtest_runs_created_idx
    ON backtest_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS backtest_entries (
    id UUID PRIMARY KEY,
    backtest_run_id UUID NOT NULL REFERENCES backtest_runs (id) ON DELETE CASCADE,
    fingerprint_key TEXT NOT NULL,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    pattern_class TEXT NOT NULL,
    pattern_type TEXT NOT NULL,
    variant TEXT,
    state TEXT NOT NULL,
    entry_date DATE NOT NULL,
    entry_price NUMERIC NOT NULL CHECK (entry_price > 0),
    setup_score NUMERIC,
    relative_strength_6m NUMERIC,
    market_regime_score NUMERIC,
    sector_code TEXT,
    candidate_fingerprint JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (backtest_run_id, fingerprint_key)
);

CREATE INDEX IF NOT EXISTS backtest_entries_run_date_idx
    ON backtest_entries (backtest_run_id, entry_date, pattern_type);

CREATE TABLE IF NOT EXISTS backtest_outcomes (
    backtest_entry_id UUID PRIMARY KEY REFERENCES backtest_entries (id) ON DELETE CASCADE,
    returns_by_horizon JSONB NOT NULL,
    mfe_by_horizon JSONB NOT NULL,
    mae_by_horizon JSONB NOT NULL,
    days_to_threshold JSONB NOT NULL,
    hit_before_loss JSONB NOT NULL,
    completeness JSONB NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
