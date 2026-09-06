ALTER TABLE nse_daily_bars_raw
    ADD COLUMN IF NOT EXISTS source_isin TEXT;

ALTER TABLE nse_corporate_actions
    ADD COLUMN IF NOT EXISTS source_isin TEXT;

CREATE INDEX IF NOT EXISTS nse_daily_bars_raw_source_isin_idx
    ON nse_daily_bars_raw (source_isin);
