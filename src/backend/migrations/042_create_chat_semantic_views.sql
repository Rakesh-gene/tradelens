-- Read-only semantic projections. Financial calculations remain in the engine.
CREATE OR REPLACE VIEW chat_security_context AS
SELECT e.isin, e.symbol, e.company_name,
       f.feature_date, p.pattern_date,
       GREATEST(f.feature_date, p.pattern_date) AS data_as_of
FROM nse_equities e
LEFT JOIN LATERAL (
    SELECT MAX(trading_date) AS feature_date FROM technical_features
    WHERE isin = e.isin AND trading_date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
) f ON TRUE
LEFT JOIN LATERAL (
    SELECT MAX(last_updated_date) AS pattern_date FROM pattern_instances
    WHERE isin = e.isin AND last_updated_date <= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date
) p ON TRUE
WHERE e.series = 'EQ';

CREATE OR REPLACE VIEW chat_current_setups AS
SELECT p.id::text AS pattern_id,
       p.id::text || ':' || p.state_version::text || ':' || p.last_updated_date::text AS snapshot_id,
       p.isin, p.pattern_class, p.pattern_type, p.variant, p.state,
       p.last_updated_date AS data_as_of, p.detected_date, p.timeframe,
       p.quality_score, p.maturity_score, p.context_score, p.setup_score,
       p.pivot_price, p.support_price, p.invalidation_price,
       p.engine_version, p.configuration_version, p.feature_version, p.adjustment_version
FROM pattern_instances p
JOIN chat_security_context c ON c.isin = p.isin AND c.data_as_of = p.last_updated_date
WHERE p.terminal_date IS NULL
  AND p.state IN ('DETECTED', 'FORMING', 'MATURE', 'READY', 'TRIGGERED', 'CONFIRMED')
  AND p.pattern_group = 'SETUP' AND p.timeframe = '1D'
  AND p.pattern_class IN ('BASE', 'BREAKOUT', 'PULLBACK');

CREATE OR REPLACE VIEW chat_setup_scores AS
SELECT s.snapshot_id, v.score_kind, v.score_value
FROM chat_current_setups s
CROSS JOIN LATERAL (VALUES
    ('QualityScore', s.quality_score), ('MaturityScore', s.maturity_score),
    ('ContextScore', s.context_score), ('SetupScore', s.setup_score)
) v(score_kind, score_value)
WHERE v.score_value IS NOT NULL;
