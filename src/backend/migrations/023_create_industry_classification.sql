CREATE TABLE IF NOT EXISTS market_macro_sectors (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    taxonomy_source TEXT NOT NULL DEFAULT 'NSE_INDICES',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE market_sectors ADD COLUMN IF NOT EXISTS macro_sector_code TEXT REFERENCES market_macro_sectors (code);

CREATE TABLE IF NOT EXISTS market_industries (
    code TEXT PRIMARY KEY,
    sector_code TEXT NOT NULL REFERENCES market_sectors (code),
    name TEXT NOT NULL,
    taxonomy_source TEXT NOT NULL DEFAULT 'NSE_INDICES',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (sector_code, name)
);

CREATE TABLE IF NOT EXISTS market_basic_industries (
    code TEXT PRIMARY KEY,
    industry_code TEXT NOT NULL REFERENCES market_industries (code),
    name TEXT NOT NULL,
    taxonomy_source TEXT NOT NULL DEFAULT 'NSE_INDICES',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (industry_code, name)
);

CREATE TABLE IF NOT EXISTS security_industry_memberships (
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    basic_industry_code TEXT NOT NULL REFERENCES market_basic_industries (code),
    effective_from DATE NOT NULL,
    effective_to DATE,
    source_name TEXT NOT NULL DEFAULT 'NSE',
    source_checksum TEXT NOT NULL,
    source_payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (isin, basic_industry_code, effective_from),
    CHECK (effective_to IS NULL OR effective_from <= effective_to)
);

CREATE INDEX IF NOT EXISTS security_industry_memberships_effective_idx
    ON security_industry_memberships (isin, effective_from, effective_to);

ALTER TABLE security_sector_memberships ADD COLUMN IF NOT EXISTS source_checksum TEXT;
ALTER TABLE security_sector_memberships ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TABLE IF NOT EXISTS equity_classification_refresh_state (
    isin TEXT PRIMARY KEY REFERENCES nse_equities (isin),
    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'MISSING', 'STALE', 'FAILED')),
    last_attempted_at TIMESTAMPTZ,
    last_succeeded_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS equity_classification_refresh_due_idx
    ON equity_classification_refresh_state (status, last_succeeded_at);

CREATE TABLE IF NOT EXISTS sector_daily_snapshots (
    sector_code TEXT NOT NULL REFERENCES market_sectors (code),
    trading_date DATE NOT NULL,
    eligible_members INTEGER NOT NULL CHECK (eligible_members >= 0),
    covered_members INTEGER NOT NULL CHECK (covered_members >= 0),
    coverage_pct NUMERIC NOT NULL CHECK (coverage_pct >= 0 AND coverage_pct <= 100),
    above_ema20_pct NUMERIC,
    above_sma50_pct NUMERIC,
    above_sma200_pct NUMERIC,
    median_relative_strength NUMERIC,
    sector_strength_score NUMERIC CHECK (sector_strength_score >= 0 AND sector_strength_score <= 100),
    methodology_version TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (sector_code, trading_date, methodology_version)
);

CREATE INDEX IF NOT EXISTS sector_daily_snapshots_date_idx
    ON sector_daily_snapshots (trading_date, sector_code);
