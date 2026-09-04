CREATE TABLE IF NOT EXISTS technical_features (
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    trading_date DATE NOT NULL,
    feature_version TEXT NOT NULL,
    data_version TEXT NOT NULL,
    true_range NUMERIC, atr_5 NUMERIC, atr_10 NUMERIC, atr_14 NUMERIC, atr_20 NUMERIC, atr_50 NUMERIC, natr_14 NUMERIC,
    ema_10 NUMERIC, ema_20 NUMERIC, sma_50 NUMERIC, sma_100 NUMERIC, sma_200 NUMERIC,
    ema_20_slope NUMERIC, sma_50_slope NUMERIC, sma_200_slope NUMERIC,
    range_5 NUMERIC, range_10 NUMERIC, range_20 NUMERIC, range_50 NUMERIC,
    median_volume_5 NUMERIC, median_volume_10 NUMERIC, median_volume_20 NUMERIC, median_volume_50 NUMERIC,
    volume_ratio_5_to_50 NUMERIC, volume_contraction_ratio NUMERIC,
    close_location_value NUMERIC,
    high_52_week NUMERIC, low_52_week NUMERIC, range_position_52_week NUMERIC, distance_to_52_week_high_pct NUMERIC,
    all_time_high NUMERIC, distance_to_all_time_high_pct NUMERIC,
    return_1_month NUMERIC, return_3_month NUMERIC, return_6_month NUMERIC, return_12_month NUMERIC,
    relative_strength_1m NUMERIC, relative_strength_3m NUMERIC, relative_strength_6m NUMERIC, relative_strength_12m NUMERIC,
    relative_strength_percentile NUMERIC, relative_strength_composite NUMERIC,
    delivery_percentage NUMERIC, median_delivery_percentage_5 NUMERIC, median_delivery_percentage_20 NUMERIC,
    delivery_expansion_ratio NUMERIC,
    input_checksum TEXT NOT NULL,
    secondary_metrics JSONB NOT NULL DEFAULT '{}'::JSONB,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (isin, trading_date, feature_version)
);

CREATE INDEX IF NOT EXISTS technical_features_isin_date_desc_idx
    ON technical_features (isin, trading_date DESC);
CREATE INDEX IF NOT EXISTS technical_features_date_version_idx
    ON technical_features (trading_date, feature_version);
