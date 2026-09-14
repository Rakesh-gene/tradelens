CREATE TABLE IF NOT EXISTS user_watchlist (
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    isin TEXT NOT NULL REFERENCES nse_equities (isin) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, isin)
);

CREATE INDEX IF NOT EXISTS user_watchlist_user_added_idx
    ON user_watchlist (user_id, added_at DESC, isin);
