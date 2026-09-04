CREATE TABLE IF NOT EXISTS nse_daily_bars_raw (
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    trading_date DATE NOT NULL,
    open_price NUMERIC NOT NULL CHECK (open_price > 0),
    high_price NUMERIC NOT NULL CHECK (high_price > 0),
    low_price NUMERIC NOT NULL CHECK (low_price > 0),
    close_price NUMERIC NOT NULL CHECK (close_price > 0),
    volume BIGINT NOT NULL CHECK (volume >= 0),
    deliverable_quantity BIGINT CHECK (deliverable_quantity >= 0),
    delivery_percentage NUMERIC CHECK (delivery_percentage >= 0 AND delivery_percentage <= 100),
    nse_series TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_checksum TEXT NOT NULL,
    source_published_at TIMESTAMPTZ,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_revision INTEGER NOT NULL DEFAULT 1 CHECK (raw_revision > 0),
    import_run_id UUID REFERENCES market_import_runs (id) ON DELETE SET NULL,
    PRIMARY KEY (isin, trading_date),
    CHECK (high_price >= low_price)
);

CREATE INDEX IF NOT EXISTS nse_daily_bars_raw_trading_date_idx
    ON nse_daily_bars_raw (trading_date);
CREATE INDEX IF NOT EXISTS nse_daily_bars_raw_isin_trading_date_desc_idx
    ON nse_daily_bars_raw (isin, trading_date DESC);
CREATE INDEX IF NOT EXISTS nse_daily_bars_raw_import_run_idx
    ON nse_daily_bars_raw (import_run_id);

CREATE TABLE IF NOT EXISTS nse_corporate_actions (
    source_event_key TEXT PRIMARY KEY,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    symbol TEXT NOT NULL,
    action_type TEXT NOT NULL,
    ex_date DATE NOT NULL,
    record_date DATE,
    announcement_date DATE,
    numerator NUMERIC CHECK (numerator > 0),
    denominator NUMERIC CHECK (denominator > 0),
    cash_value NUMERIC CHECK (cash_value >= 0),
    currency TEXT,
    raw_description TEXT,
    raw_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    source_checksum TEXT NOT NULL,
    import_run_id UUID REFERENCES market_import_runs (id) ON DELETE SET NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nse_corporate_actions_isin_ex_date_idx
    ON nse_corporate_actions (isin, ex_date DESC);
CREATE INDEX IF NOT EXISTS nse_corporate_actions_ex_date_idx
    ON nse_corporate_actions (ex_date);

CREATE TABLE IF NOT EXISTS adjusted_daily_bars (
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    trading_date DATE NOT NULL,
    adjustment_version TEXT NOT NULL,
    open_price NUMERIC NOT NULL CHECK (open_price > 0),
    high_price NUMERIC NOT NULL CHECK (high_price > 0),
    low_price NUMERIC NOT NULL CHECK (low_price > 0),
    close_price NUMERIC NOT NULL CHECK (close_price > 0),
    volume NUMERIC NOT NULL CHECK (volume >= 0),
    price_adjustment_factor NUMERIC NOT NULL CHECK (price_adjustment_factor > 0),
    volume_adjustment_factor NUMERIC NOT NULL CHECK (volume_adjustment_factor > 0),
    adjustment_source TEXT NOT NULL CHECK (adjustment_source IN ('NSE_SOURCE', 'TRADELENS_REBUILT')),
    source_revision INTEGER NOT NULL CHECK (source_revision > 0),
    action_set_checksum TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (isin, trading_date, adjustment_version),
    CHECK (high_price >= low_price)
);

CREATE INDEX IF NOT EXISTS adjusted_daily_bars_isin_date_desc_idx
    ON adjusted_daily_bars (isin, trading_date DESC);
CREATE INDEX IF NOT EXISTS adjusted_daily_bars_date_version_idx
    ON adjusted_daily_bars (trading_date, adjustment_version);
