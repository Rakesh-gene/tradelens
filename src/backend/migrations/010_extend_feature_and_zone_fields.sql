ALTER TABLE technical_features
    ADD COLUMN IF NOT EXISTS volume_ratio_20 NUMERIC,
    ADD COLUMN IF NOT EXISTS distance_to_ema_20_pct NUMERIC,
    ADD COLUMN IF NOT EXISTS distance_to_sma_50_pct NUMERIC,
    ADD COLUMN IF NOT EXISTS distance_to_sma_200_pct NUMERIC,
    ADD COLUMN IF NOT EXISTS deliverable_volume NUMERIC,
    ADD COLUMN IF NOT EXISTS median_traded_value_20 NUMERIC;

ALTER TABLE price_zones
    ADD COLUMN IF NOT EXISTS last_test_date DATE,
    ADD COLUMN IF NOT EXISTS confirmation_date DATE;

UPDATE price_zones
SET last_test_date = COALESCE(last_test_date, end_date),
    confirmation_date = COALESCE(confirmation_date, end_date)
WHERE last_test_date IS NULL OR confirmation_date IS NULL;

ALTER TABLE price_zones
    ALTER COLUMN last_test_date SET NOT NULL,
    ALTER COLUMN confirmation_date SET NOT NULL;

CREATE INDEX IF NOT EXISTS price_zones_isin_confirmation_idx
    ON price_zones (isin, confirmation_date DESC);
