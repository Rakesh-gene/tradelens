CREATE TABLE IF NOT EXISTS index_quadrant_state (
    index_code TEXT PRIMARY KEY REFERENCES market_indices (code) ON DELETE CASCADE,
    zone TEXT NOT NULL CHECK (zone IN ('LEADING', 'WEAKENING', 'IMPROVING', 'LAGGING', 'UNAVAILABLE')),
    strength NUMERIC,
    momentum NUMERIC,
    data_as_of DATE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS index_quadrant_events (
    id UUID PRIMARY KEY,
    index_code TEXT NOT NULL REFERENCES market_indices (code) ON DELETE CASCADE,
    event_type TEXT NOT NULL CHECK (event_type IN ('QUADRANT_ENTERED', 'QUADRANT_CHANGED', 'QUADRANT_LEFT')),
    previous_zone TEXT,
    new_zone TEXT,
    strength NUMERIC,
    momentum NUMERIC,
    effective_date DATE NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    methodology_version TEXT NOT NULL DEFAULT 'sector-rotation-v1',
    UNIQUE (index_code, effective_date)
);

CREATE INDEX IF NOT EXISTS index_quadrant_events_date_idx
    ON index_quadrant_events (effective_date DESC, recorded_at DESC);
