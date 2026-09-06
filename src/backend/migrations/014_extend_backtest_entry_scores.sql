ALTER TABLE backtest_entries
    ADD COLUMN IF NOT EXISTS quality_score NUMERIC,
    ADD COLUMN IF NOT EXISTS maturity_score NUMERIC,
    ADD COLUMN IF NOT EXISTS context_score NUMERIC;
