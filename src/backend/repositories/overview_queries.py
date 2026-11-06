"""Bounded Overview query. Qualification happens after peers, before LIMIT."""

OVERVIEW_SETUPS_SQL = """
WITH representatives AS (
    SELECT p.*, ROW_NUMBER() OVER (
        PARTITION BY p.isin
        ORDER BY CASE p.state WHEN 'CONFIRMED' THEN 1 WHEN 'TRIGGERED' THEN 2 ELSE 3 END,
                 CASE p.pattern_class WHEN 'BREAKOUT' THEN 1 WHEN 'BASE' THEN 2 WHEN 'PULLBACK' THEN 3 ELSE 4 END,
                 p.setup_score DESC NULLS LAST, p.detected_date DESC, p.id
    ) AS security_rank, COUNT(*) OVER (PARTITION BY p.isin) AS evidence_count
    FROM pattern_instances p
    JOIN nse_equities eligible ON eligible.isin = p.isin AND eligible.series = 'EQ'
    WHERE p.last_updated_date <= %(as_of)s AND p.terminal_date IS NULL
      AND p.state = ANY(%(states)s) AND p.pattern_group = 'SETUP' AND p.timeframe = '1D'
      AND __LATEST__
), scored AS (
    SELECT p.*, NULLIF(p.measurements #>> '{scoring,context_inputs,liquidity}', '')::numeric AS liquidity_score,
           ROUND(COALESCE(p.setup_score, 0) * 0.75 + COALESCE(p.context_score, 0) * 0.10
           + COALESCE(NULLIF(p.measurements #>> '{scoring,context_inputs,liquidity}', '')::numeric, 0) * 0.15, 2) AS best_fit_score
    FROM representatives p WHERE security_rank = 1
), peers AS (
    SELECT p.*, DENSE_RANK() OVER (PARTITION BY state ORDER BY best_fit_score DESC, setup_score DESC NULLS LAST, id) AS best_fit_rank,
           CASE WHEN COUNT(*) OVER (PARTITION BY state) = 1 THEN 100
                ELSE PERCENT_RANK() OVER (PARTITION BY state ORDER BY best_fit_score ASC) * 100 END AS best_fit_percentile_raw,
           COUNT(*) OVER (PARTITION BY state) AS state_candidate_count
    FROM scored p
), evidence AS (
    SELECT p.*, ROUND(p.best_fit_percentile_raw::numeric, 1) AS best_fit_percentile,
           feature.trading_date AS feature_date, bars.trading_date AS price_date, bars.close_price AS last_close,
           feature.relative_strength_6m, feature.relative_strength_percentile, feature.median_traded_value_20,
           CASE WHEN p.pivot_price > 0 THEN (bars.close_price - p.pivot_price) / p.pivot_price * 100 END AS distance_to_pivot_pct
    FROM peers p
    LEFT JOIN technical_features feature ON feature.isin = p.isin AND feature.trading_date = %(as_of)s
      AND feature.feature_version = p.feature_version AND feature.data_version = p.adjustment_version
    LEFT JOIN adjusted_daily_bars bars ON bars.isin = p.isin AND bars.trading_date = %(as_of)s
      AND bars.adjustment_version = p.adjustment_version
), qualified AS (
    SELECT p.* FROM evidence p
    WHERE p.best_fit_percentile_raw >= %(minimum_peer_percentile)s
      AND p.best_fit_percentile_raw <= 100
      AND p.best_fit_score BETWEEN %(minimum_best_fit)s AND 100
      AND p.quality_score BETWEEN %(minimum_quality)s AND 100
      AND p.context_score BETWEEN %(minimum_context)s AND 100
      AND p.setup_score BETWEEN 0 AND 100
      AND p.liquidity_score = %(required_liquidity)s
      AND p.last_updated_date = %(as_of)s AND p.feature_date = %(as_of)s AND p.price_date = %(as_of)s
      AND NULLIF(p.engine_version, '') IS NOT NULL AND NULLIF(p.configuration_version, '') IS NOT NULL
      AND NULLIF(p.feature_version, '') IS NOT NULL AND NULLIF(p.adjustment_version, '') IS NOT NULL
      AND p.last_close > 0 AND p.last_close < 'Infinity'::numeric
      AND p.pivot_price > 0 AND p.pivot_price < 'Infinity'::numeric
      AND p.invalidation_price > 0 AND p.invalidation_price < 'Infinity'::numeric
      AND p.last_close > p.invalidation_price
), totals AS (
    SELECT (SELECT COUNT(*) FROM peers) AS candidate_count, COUNT(*) AS qualified_count FROM qualified
), page AS (
    SELECT * FROM qualified ORDER BY best_fit_score DESC, id DESC LIMIT %(limit)s OFFSET %(offset)s
)
SELECT p.*, totals.candidate_count, totals.qualified_count, equity.symbol, equity.company_name,
       sector.sector_code, sector.sector_name
FROM totals LEFT JOIN page p ON TRUE
LEFT JOIN nse_equities equity ON equity.isin = p.isin
LEFT JOIN LATERAL (
    SELECT membership.sector_code, sectors.name AS sector_name FROM security_sector_memberships membership
    JOIN market_sectors sectors ON sectors.code = membership.sector_code
    WHERE membership.isin = p.isin AND membership.effective_from <= %(as_of)s
      AND (membership.effective_to IS NULL OR membership.effective_to >= %(as_of)s)
    ORDER BY membership.effective_from DESC LIMIT 1
) sector ON TRUE
ORDER BY p.best_fit_score DESC, p.id DESC
"""
