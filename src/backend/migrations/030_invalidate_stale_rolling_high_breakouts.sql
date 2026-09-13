-- Versions before this correction calculated the current rolling-high pivot and
-- then searched the complete price history for a trigger.  That could attach an
-- unrelated years-old close to a current BRK-52WH or BRK-MULTIY instance.
WITH stale AS (
    SELECT id, state, state_version, last_updated_date, measurements,
           pivot_price, support_price, invalidation_price,
           quality_score, maturity_score, context_score, setup_score,
           terminal_date, variant
    FROM pattern_instances
    WHERE terminal_date IS NULL
      AND pattern_type IN ('BRK-52WH', 'BRK-ATH', 'BRK-MULTIY')
      AND COALESCE((measurements ->> 'sessions_since_trigger')::INTEGER, 0) > 5
), inserted_events AS (
    INSERT INTO pattern_events (
        id, pattern_instance_id, event_type, state_version, previous_state,
        new_state, previous_values, new_values, effective_date
    )
    SELECT
        md5('030-stale-rolling-high|' || id::TEXT)::UUID,
        id,
        'INVALIDATED',
        state_version + 1,
        state,
        'INVALIDATED',
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
            'state', 'INVALIDATED',
            'variant', variant,
            'pivot_price', pivot_price,
            'support_price', support_price,
            'invalidation_price', invalidation_price,
            'quality_score', quality_score,
            'maturity_score', maturity_score,
            'context_score', context_score,
            'setup_score', setup_score,
            'terminal_date', last_updated_date,
            'invalidation_reason', 'ROLLING_HIGH_TRIGGER_CORRECTED'
        ),
        last_updated_date
    FROM stale
    ON CONFLICT DO NOTHING
)
UPDATE pattern_instances
SET state = 'INVALIDATED',
    state_version = state_version + 1,
    terminal_date = last_updated_date,
    measurements = measurements || jsonb_build_object(
        'invalidation_reason', 'ROLLING_HIGH_TRIGGER_CORRECTED'
    ),
    updated_at = NOW()
WHERE id IN (SELECT id FROM stale);
