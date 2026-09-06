CREATE TABLE IF NOT EXISTS pattern_instances (
    id UUID PRIMARY KEY,
    isin TEXT NOT NULL REFERENCES nse_equities (isin),
    pattern_class TEXT NOT NULL CHECK (pattern_class IN (
        'TREND', 'BASE', 'BREAKOUT', 'PULLBACK', 'COMPRESSION', 'MOMENTUM', 'FAILURE'
    )),
    pattern_type TEXT NOT NULL,
    variant TEXT,
    start_date DATE NOT NULL,
    detected_date DATE NOT NULL,
    trigger_date DATE,
    confirmation_date DATE,
    last_updated_date DATE NOT NULL,
    terminal_date DATE,
    state TEXT NOT NULL CHECK (state IN (
        'DETECTED', 'FORMING', 'MATURE', 'READY', 'TRIGGERED',
        'CONFIRMED', 'FAILED', 'INVALIDATED', 'EXPIRED'
    )),
    state_version INTEGER NOT NULL DEFAULT 1 CHECK (state_version > 0),
    quality_score NUMERIC CHECK (quality_score BETWEEN 0 AND 100),
    maturity_score NUMERIC CHECK (maturity_score BETWEEN 0 AND 100),
    context_score NUMERIC CHECK (context_score BETWEEN 0 AND 100),
    setup_score NUMERIC CHECK (setup_score BETWEEN 0 AND 100),
    pivot_price NUMERIC,
    support_price NUMERIC,
    invalidation_price NUMERIC,
    source_pattern_id UUID REFERENCES pattern_instances (id),
    measurements JSONB NOT NULL DEFAULT '{}'::jsonb,
    supporting_patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
    configuration_version TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    feature_version TEXT NOT NULL,
    adjustment_version TEXT NOT NULL,
    active_deduplication_key TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS pattern_instances_active_dedup_idx
    ON pattern_instances (active_deduplication_key)
    WHERE terminal_date IS NULL;
CREATE INDEX IF NOT EXISTS pattern_instances_security_type_idx
    ON pattern_instances (isin, pattern_type, last_updated_date DESC);
CREATE INDEX IF NOT EXISTS pattern_instances_active_state_idx
    ON pattern_instances (state, setup_score DESC)
    WHERE terminal_date IS NULL;

CREATE TABLE IF NOT EXISTS pattern_events (
    id UUID PRIMARY KEY,
    pattern_instance_id UUID NOT NULL REFERENCES pattern_instances (id),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'PATTERN_DETECTED', 'STATE_CHANGED', 'PIVOT_UPDATED', 'QUALITY_CHANGED',
        'MATURITY_CHANGED', 'TRIGGERED', 'CONFIRMED', 'FAILED', 'INVALIDATED', 'EXPIRED'
    )),
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    previous_state TEXT,
    new_state TEXT NOT NULL,
    previous_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    new_values JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_date DATE NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (pattern_instance_id, state_version, event_type)
);
CREATE INDEX IF NOT EXISTS pattern_events_instance_time_idx
    ON pattern_events (pattern_instance_id, effective_date, recorded_at);

CREATE OR REPLACE FUNCTION reject_pattern_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'pattern_events are immutable';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS pattern_events_immutable ON pattern_events;
CREATE TRIGGER pattern_events_immutable
BEFORE UPDATE OR DELETE ON pattern_events
FOR EACH ROW EXECUTE FUNCTION reject_pattern_event_mutation();
