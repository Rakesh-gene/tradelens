CREATE TABLE IF NOT EXISTS market_indices (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'NSE',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS index_daily_bars (
    index_code TEXT NOT NULL REFERENCES market_indices (code),
    trading_date DATE NOT NULL,
    open_price NUMERIC NOT NULL CHECK (open_price > 0),
    high_price NUMERIC NOT NULL CHECK (high_price > 0),
    low_price NUMERIC NOT NULL CHECK (low_price > 0),
    close_price NUMERIC NOT NULL CHECK (close_price > 0),
    volume BIGINT CHECK (volume >= 0),
    source_name TEXT NOT NULL,
    source_checksum TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (index_code, trading_date),
    CHECK (high_price >= low_price)
);

CREATE INDEX IF NOT EXISTS index_daily_bars_trading_date_idx
    ON index_daily_bars (trading_date);

CREATE TABLE IF NOT EXISTS market_sectors (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    taxonomy_source TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS security_sector_memberships (
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    sector_code TEXT NOT NULL REFERENCES market_sectors (code),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_name TEXT NOT NULL,
    PRIMARY KEY (isin, sector_code, effective_from),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE INDEX IF NOT EXISTS security_sector_memberships_effective_idx
    ON security_sector_memberships (isin, effective_from, effective_to);

CREATE TABLE IF NOT EXISTS index_constituent_memberships (
    index_code TEXT NOT NULL REFERENCES market_indices (code),
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_name TEXT NOT NULL,
    PRIMARY KEY (index_code, isin, effective_from),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE INDEX IF NOT EXISTS index_constituent_memberships_effective_idx
    ON index_constituent_memberships (index_code, effective_from, effective_to);
