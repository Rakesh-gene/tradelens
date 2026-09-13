-- Engine v2 introduced complete active-pattern reconciliation. Remove active
-- v1 calculations from the opportunity set while retaining their evidence.
WITH stale AS (
    SELECT id, state, state_version, last_updated_date, measurements,
           pivot_price, support_price, invalidation_price,
           quality_score, maturity_score, context_score, setup_score,
           terminal_date, variant
    FROM pattern_instances
    WHERE terminal_date IS NULL
      AND (
          engine_version <> 'v2'
          OR configuration_version <> 'v2'
          OR feature_version <> 'v2'
      )
), inserted_events AS (
    INSERT INTO pattern_events (
        id, pattern_instance_id, event_type, state_version, previous_state,
        new_state, previous_values, new_values, effective_date
    )
    SELECT
        md5('032-superseded-lineage|' || id::TEXT)::UUID,
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
            'invalidation_reason', 'CALCULATION_LINEAGE_SUPERSEDED'
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
        'invalidation_reason', 'CALCULATION_LINEAGE_SUPERSEDED'
    ),
    updated_at = NOW()
WHERE id IN (SELECT id FROM stale);

-- A confirmed breakout remains actionable through the configured 30-session
-- retest window. Older instances remain available as expired history.
WITH stale AS (
    SELECT p.id, p.state, p.state_version, p.measurements,
           p.pivot_price, p.support_price, p.invalidation_price,
           p.quality_score, p.maturity_score, p.context_score, p.setup_score,
           p.terminal_date, p.variant, latest.as_of_date
    FROM pattern_instances AS p
    CROSS JOIN LATERAL (
        SELECT MAX(bar.trading_date) AS as_of_date
        FROM adjusted_daily_bars AS bar
        WHERE bar.isin = p.isin
          AND bar.adjustment_version = p.adjustment_version
    ) AS latest
    WHERE p.terminal_date IS NULL
      AND p.pattern_class = 'BREAKOUT'
      AND p.state = 'CONFIRMED'
      AND p.trigger_date IS NOT NULL
      AND latest.as_of_date IS NOT NULL
      AND (
          SELECT COUNT(DISTINCT bar.trading_date)
          FROM adjusted_daily_bars AS bar
          WHERE bar.isin = p.isin
            AND bar.adjustment_version = p.adjustment_version
            AND bar.trading_date > p.trigger_date
            AND bar.trading_date <= latest.as_of_date
      ) > 30
), inserted_events AS (
    INSERT INTO pattern_events (
        id, pattern_instance_id, event_type, state_version, previous_state,
        new_state, previous_values, new_values, effective_date
    )
    SELECT
        md5('032-expired-confirmed-breakout|' || id::TEXT)::UUID,
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
            'terminal_date', as_of_date,
            'expiration_reason', 'BREAKOUT_RETEST_WINDOW_ELAPSED'
        ),
        as_of_date
    FROM stale
    ON CONFLICT DO NOTHING
)
UPDATE pattern_instances
SET state = 'EXPIRED',
    state_version = pattern_instances.state_version + 1,
    terminal_date = stale.as_of_date,
    last_updated_date = stale.as_of_date,
    measurements = pattern_instances.measurements || jsonb_build_object(
        'expiration_reason', 'BREAKOUT_RETEST_WINDOW_ELAPSED'
    ),
    updated_at = NOW()
FROM stale
WHERE pattern_instances.id = stale.id;
