ALTER TABLE case_study_runs ADD COLUMN IF NOT EXISTS source_backtest_run_id UUID REFERENCES backtest_runs (id) ON DELETE RESTRICT;
ALTER TABLE case_study_runs ADD COLUMN IF NOT EXISTS trade_policy_inputs JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE case_study_runs ADD COLUMN IF NOT EXISTS selection_policy_inputs JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE case_studies ADD COLUMN IF NOT EXISTS sector_code TEXT;
ALTER TABLE case_studies ADD COLUMN IF NOT EXISTS setup_score NUMERIC;
ALTER TABLE case_studies ADD COLUMN IF NOT EXISTS market_regime TEXT;
ALTER TABLE case_studies ADD COLUMN IF NOT EXISTS sector_context TEXT;

ALTER TABLE case_study_trade_results ADD COLUMN IF NOT EXISTS duration_sessions INTEGER CHECK (duration_sessions >= 0);
ALTER TABLE case_study_trade_results ADD COLUMN IF NOT EXISTS policy_inputs JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS case_studies_filter_idx
    ON case_studies (timeframe, direction, exit_reason, setup_score DESC);
