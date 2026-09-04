CREATE TABLE IF NOT EXISTS nse_equities (
    isin TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    company_name TEXT NOT NULL,
    series TEXT NOT NULL,
    listed_on DATE NOT NULL,
    paid_up_value NUMERIC NOT NULL,
    market_lot INTEGER NOT NULL,
    face_value NUMERIC NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS nse_equities_symbol_idx ON nse_equities (symbol);
