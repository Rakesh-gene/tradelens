CREATE TABLE IF NOT EXISTS swing_points (
    id UUID PRIMARY KEY,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    pivot_date DATE NOT NULL,
    confirmation_date DATE NOT NULL,
    swing_type TEXT NOT NULL CHECK (swing_type IN ('HIGH', 'LOW')),
    price NUMERIC NOT NULL CHECK (price > 0),
    natr_14 NUMERIC,
    move_size_pct NUMERIC,
    is_meaningful BOOLEAN NOT NULL,
    feature_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    input_checksum TEXT NOT NULL,
    UNIQUE (isin, pivot_date, swing_type, feature_version)
);
CREATE INDEX IF NOT EXISTS swing_points_isin_confirmation_idx ON swing_points (isin, confirmation_date DESC);

CREATE TABLE IF NOT EXISTS price_zones (
    id UUID PRIMARY KEY,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    zone_type TEXT NOT NULL CHECK (zone_type IN ('RESISTANCE', 'SUPPORT')),
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    median_price NUMERIC NOT NULL CHECK (median_price > 0),
    tolerance_pct NUMERIC NOT NULL,
    breakout_buffer_pct NUMERIC NOT NULL,
    dispersion_pct NUMERIC NOT NULL,
    source_swing_ids JSONB NOT NULL,
    test_count INTEGER NOT NULL CHECK (test_count > 0),
    feature_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    input_checksum TEXT NOT NULL,
    UNIQUE (isin, zone_type, start_date, end_date, feature_version)
);
CREATE INDEX IF NOT EXISTS price_zones_isin_type_end_idx ON price_zones (isin, zone_type, end_date DESC);
