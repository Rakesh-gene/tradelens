ALTER TABLE nse_daily_bars_raw
    ADD COLUMN IF NOT EXISTS previous_close_price NUMERIC
        CHECK (previous_close_price > 0);

CREATE INDEX IF NOT EXISTS nse_daily_bars_raw_action_reference_idx
    ON nse_daily_bars_raw (isin, trading_date, previous_close_price)
    WHERE previous_close_price IS NOT NULL;
