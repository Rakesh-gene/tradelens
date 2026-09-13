-- Unconfirmed breakouts are observable for five sessions. Older detector
-- versions continued refreshing the first matching close indefinitely.
WITH stale AS (
    SELECT id, state, state_version, last_updated_date, measurements,
           pivot_price, support_price, invalidation_price,
           quality_score, maturity_score, context_score, setup_score,
           terminal_date, variant
    FROM pattern_instances
    WHERE terminal_date IS NULL
      AND pattern_class = 'BREAKOUT'
      AND state = 'TRIGGERED'
      AND COALESCE((measurements ->> 'sessions_since_trigger')::INTEGER, 0) > 5
), inserted_events AS (
    INSERT INTO pattern_events (
        id, pattern_instance_id, event_type, state_version, previous_state,
        new_state, previous_values, new_values, effective_date
    )
    SELECT
        md5('031-stale-triggered-breakout|' || id::TEXT)::UUID,
        id,
        'EXPIRED',
        state_version + 1,
        state,
        'EXPIRED',
        jsonb_build_object(
            'state', state,
            'variant', variant,
            'pivot_price', pivot_price,
            'support_price', support_price,
            'invalidation_price', invalidation_price,
            'quality_score', quality_score,
            'maturity_score', maturity_score,
            'context_score', context_score,
            'setup_score', setup_score,
            'terminal_date', terminal_date
        ),
        jsonb_build_object(
            'state', 'EXPIRED',
            'variant', variant,
            'pivot_price', pivot_price,
            'support_price', support_price,
            'invalidation_price', invalidation_price,
            'quality_score', quality_score,
            'maturity_score', maturity_score,
            'context_score', context_score,
            'setup_score', setup_score,
            'terminal_date', last_updated_date,
            'expiration_reason', 'BREAKOUT_OBSERVATION_WINDOW_ELAPSED'
        ),
        last_updated_date
    FROM stale
    ON CONFLICT DO NOTHING
)
UPDATE pattern_instances
SET state = 'EXPIRED',
    state_version = state_version + 1,
    terminal_date = last_updated_date,
    measurements = measurements || jsonb_build_object(
        'expiration_reason', 'BREAKOUT_OBSERVATION_WINDOW_ELAPSED'
    ),
    updated_at = NOW()
WHERE id IN (SELECT id FROM stale);
