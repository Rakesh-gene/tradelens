CREATE TABLE IF NOT EXISTS watchlist_quadrant_state (
    user_id UUID NOT NULL,
    isin TEXT NOT NULL,
    zone TEXT NOT NULL CHECK (zone IN ('LEADING', 'WEAKENING', 'IMPROVING', 'LAGGING', 'UNAVAILABLE')),
    strength NUMERIC,
    momentum NUMERIC,
    data_as_of DATE,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, isin),
    FOREIGN KEY (user_id, isin) REFERENCES user_watchlist (user_id, isin) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS watchlist_quadrant_events (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    isin TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('QUADRANT_ENTERED', 'QUADRANT_CHANGED', 'QUADRANT_LEFT')),
    previous_zone TEXT,
    new_zone TEXT,
    strength NUMERIC,
    momentum NUMERIC,
    effective_date DATE NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    methodology_version TEXT NOT NULL DEFAULT 'sector-rotation-v1',
    FOREIGN KEY (user_id, isin) REFERENCES user_watchlist (user_id, isin) ON DELETE CASCADE,
    UNIQUE (user_id, isin, effective_date)
);

CREATE INDEX IF NOT EXISTS watchlist_quadrant_events_user_date_idx
    ON watchlist_quadrant_events (user_id, effective_date DESC, recorded_at DESC);
