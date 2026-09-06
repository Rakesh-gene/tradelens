CREATE INDEX IF NOT EXISTS pattern_instances_overview_active_idx
    ON pattern_instances (state, last_updated_date DESC, setup_score DESC, isin)
    WHERE terminal_date IS NULL;

CREATE INDEX IF NOT EXISTS technical_features_latest_version_idx
    ON technical_features (isin, feature_version, trading_date DESC, generated_at DESC);

CREATE INDEX IF NOT EXISTS market_import_runs_job_started_idx
    ON market_import_runs (job_type, started_at DESC);
