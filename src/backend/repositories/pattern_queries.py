"""Read-only, bounded queries for pattern product APIs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from repositories.migrations import MigrationRunner
from repositories.sector_rotation import SectorRotationQueries, MemorySectorRotationQueries


_SORT_COLUMNS = {
    "bestFit": "p.best_fit_score",
    "setupScore": "p.setup_score",
    "qualityScore": "p.quality_score",
    "maturityScore": "p.maturity_score",
    "detectedDate": "p.detected_date",
    "distanceToPivotPct": "distance_to_pivot_pct",
}


class PostgresPatternQueryRepository(SectorRotationQueries):
    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            MigrationRunner(self._connect, Path(__file__).resolve().parents[1] / "migrations").apply()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def search_securities(self, query, limit):
        text = str(query).strip()
        prefix = f"{text}%"
        return self._fetch_all(
            """
            SELECT equity.isin, equity.symbol, equity.company_name,
                   sector.sector_code, sector.sector_name,
                   sector.basic_industry_name
            FROM nse_equities equity
            LEFT JOIN LATERAL (
                SELECT membership.sector_code, sectors.name AS sector_name,
                       basic.name AS basic_industry_name
                FROM security_sector_memberships membership
                JOIN market_sectors sectors ON sectors.code = membership.sector_code
                LEFT JOIN security_industry_memberships sim ON sim.isin = membership.isin
                  AND sim.effective_to IS NULL
                LEFT JOIN market_basic_industries basic ON basic.code = sim.basic_industry_code
                WHERE membership.isin = equity.isin AND membership.effective_to IS NULL
                ORDER BY membership.effective_from DESC LIMIT 1
            ) sector ON TRUE
            WHERE equity.series = 'EQ'
              AND (equity.symbol ILIKE %s OR equity.company_name ILIKE %s)
            ORDER BY CASE
                       WHEN UPPER(symbol) = UPPER(%s) THEN 0
                       WHEN symbol ILIKE %s THEN 1
                       WHEN company_name ILIKE %s THEN 2
                       ELSE 3
                     END,
                     equity.symbol, equity.isin
            LIMIT %s
            """,
            (prefix, prefix, text, prefix, prefix, limit),
        )

    def list_setups(self, filters, limit, offset):
        clauses = ["p.last_updated_date <= %(as_of)s"]
        parameters = {"as_of": filters["as_of"], "limit": limit + 1, "offset": offset}
        if filters.get("pattern_class"):
            clauses.append("p.pattern_class = %(pattern_class)s")
            parameters["pattern_class"] = filters["pattern_class"]
        for key, column in (("pattern_type", "p.pattern_type"), ("variant", "p.variant"), ("sector", "sector.sector_code")):
            if filters.get(key):
                clauses.append(f"{column} = %({key})s")
                parameters[key] = filters[key]
        clauses.append('p.timeframe = %(timeframe)s')
        parameters['timeframe'] = filters.get('timeframe') or '1D'
        if filters.get('pattern_group'):
            clauses.append('p.pattern_group = %(pattern_group)s')
            parameters['pattern_group'] = filters['pattern_group']
        if filters.get('pattern_direction'):
            clauses.append('p.direction = %(pattern_direction)s')
            parameters['pattern_direction'] = filters['pattern_direction']
        if filters.get("states"):
            clauses.append("p.state = ANY(%(states)s)")
            parameters["states"] = list(filters["states"])
            if set(filters["states"]).issubset({
                "DETECTED", "FORMING", "MATURE", "READY", "TRIGGERED", "CONFIRMED",
            }):
                clauses.append("p.terminal_date IS NULL")
        for key, column, operator in (
            ("min_setup_score", "p.setup_score", ">="), ("max_setup_score", "p.setup_score", "<="),
            ("min_rs6m", "feature.relative_strength_6m", ">="),
            ("min_liquidity_score", "NULLIF(p.measurements #>> '{scoring,context_inputs,liquidity}', '')::numeric", ">="),
        ):
            if filters.get(key) is not None:
                clauses.append(f"{column} {operator} %({key})s")
                parameters[key] = filters[key]
        sort_column = _SORT_COLUMNS[filters["sort"]].replace("p.", "")
        direction = "ASC" if filters["direction"] == "asc" else "DESC"
        if (
            not filters.get("sector")
            and filters.get("min_rs6m") is None
            and filters.get("min_liquidity_score") is None
            and filters["sort"] != "distanceToPivotPct"
        ):
            return self._list_setups_pattern_ranked(
                clauses, parameters, sort_column, direction
            )
        statement = f"""
            WITH ranked_setups AS (
            SELECT p.*, equity.symbol, equity.company_name,
                   sector.sector_code, sector.sector_name,
                   feature.close_price AS last_close,
                   feature.relative_strength_6m, feature.relative_strength_percentile,
                   feature.median_traded_value_20,
                   CASE WHEN p.pivot_price IS NULL OR feature.close_price IS NULL OR p.pivot_price = 0
                        THEN NULL ELSE (feature.close_price - p.pivot_price) / p.pivot_price * 100 END AS distance_to_pivot_pct,
                   COUNT(*) OVER (PARTITION BY p.isin) AS evidence_count,
                   ROW_NUMBER() OVER (
                     PARTITION BY p.isin
                     ORDER BY CASE p.state WHEN 'CONFIRMED' THEN 1 WHEN 'TRIGGERED' THEN 2 WHEN 'READY' THEN 3 ELSE 4 END,
                              CASE p.pattern_class WHEN 'BREAKOUT' THEN 1 WHEN 'BASE' THEN 2 WHEN 'PULLBACK' THEN 3 ELSE 4 END,
                              p.setup_score DESC NULLS LAST, p.detected_date DESC, p.id
                   ) AS security_rank
            FROM pattern_instances AS p
            JOIN nse_equities AS equity ON equity.isin = p.isin
            LEFT JOIN LATERAL (
                SELECT membership.sector_code, sectors.name AS sector_name
                FROM security_sector_memberships AS membership
                JOIN market_sectors AS sectors ON sectors.code = membership.sector_code
                WHERE membership.isin = p.isin AND membership.effective_from <= %(as_of)s
                  AND (membership.effective_to IS NULL OR membership.effective_to >= %(as_of)s)
                ORDER BY membership.effective_from DESC LIMIT 1
            ) AS sector ON TRUE
            LEFT JOIN LATERAL (
                SELECT features.*, bars.close_price
                FROM technical_features AS features
                LEFT JOIN adjusted_daily_bars AS bars
                  ON bars.isin = features.isin AND bars.trading_date = features.trading_date
                 AND bars.adjustment_version = p.adjustment_version
                WHERE features.isin = p.isin AND features.trading_date <= %(as_of)s
                  AND features.feature_version = p.feature_version
                ORDER BY features.trading_date DESC LIMIT 1
            ) AS feature ON TRUE
            WHERE {' AND '.join(clauses)}
            ), best_fit_pool AS (
                SELECT p.*,
                       ROUND(
                           COALESCE(p.setup_score, 0) * 0.75
                           + COALESCE(p.context_score, 0) * 0.10
                           + COALESCE(NULLIF(p.measurements #>> '{{scoring,context_inputs,liquidity}}', '')::numeric, 0) * 0.15,
                           2
                       ) AS best_fit_score
                FROM ranked_setups p WHERE security_rank = 1
            ), ranked_best_fit AS (
                SELECT p.*,
                       DENSE_RANK() OVER (
                           PARTITION BY p.state
                           ORDER BY p.best_fit_score DESC, p.setup_score DESC NULLS LAST, p.id
                       ) AS best_fit_rank,
                       ROUND((PERCENT_RANK() OVER (
                           PARTITION BY p.state ORDER BY p.best_fit_score ASC
                       ) * 100)::numeric, 1) AS best_fit_percentile,
                       COUNT(*) OVER (PARTITION BY p.state) AS state_candidate_count,
                       COUNT(*) OVER () AS total_count
                FROM best_fit_pool p
            )
            SELECT * FROM ranked_best_fit
            ORDER BY {sort_column} {direction} NULLS LAST, id {direction}
            LIMIT %(limit)s OFFSET %(offset)s
        """
        return self._fetch_all(statement, parameters)

    def _list_setups_pattern_ranked(
        self, clauses, parameters, sort_column, direction
    ):
        """Rank patterns before expensive per-security feature/sector lookups."""

        statement = f"""
            WITH ranked_setups AS (
                SELECT p.*,
                       COUNT(*) OVER (PARTITION BY p.isin) AS evidence_count,
                       ROW_NUMBER() OVER (
                         PARTITION BY p.isin
                         ORDER BY CASE p.state WHEN 'CONFIRMED' THEN 1 WHEN 'TRIGGERED' THEN 2 WHEN 'READY' THEN 3 ELSE 4 END,
                                  CASE p.pattern_class WHEN 'BREAKOUT' THEN 1 WHEN 'BASE' THEN 2 WHEN 'PULLBACK' THEN 3 ELSE 4 END,
                                  p.setup_score DESC NULLS LAST, p.detected_date DESC, p.id
                       ) AS security_rank
                FROM pattern_instances AS p
                WHERE {' AND '.join(clauses)}
            ), best_fit_pool AS (
                SELECT p.*,
                       ROUND(
                           COALESCE(p.setup_score, 0) * 0.75
                           + COALESCE(p.context_score, 0) * 0.10
                           + COALESCE(NULLIF(p.measurements #>> '{{scoring,context_inputs,liquidity}}', '')::numeric, 0) * 0.15,
                           2
                       ) AS best_fit_score
                FROM ranked_setups p WHERE security_rank = 1
            ), ranked_best_fit AS (
                SELECT p.*,
                       DENSE_RANK() OVER (
                           PARTITION BY p.state
                           ORDER BY p.best_fit_score DESC, p.setup_score DESC NULLS LAST, p.id
                       ) AS best_fit_rank,
                       ROUND((PERCENT_RANK() OVER (
                           PARTITION BY p.state ORDER BY p.best_fit_score ASC
                       ) * 100)::numeric, 1) AS best_fit_percentile,
                       COUNT(*) OVER (PARTITION BY p.state) AS state_candidate_count,
                       COUNT(*) OVER () AS total_count
                FROM best_fit_pool p
            ), selected_setups AS (
                SELECT * FROM ranked_best_fit
                ORDER BY {sort_column} {direction} NULLS LAST, id {direction}
                LIMIT %(limit)s OFFSET %(offset)s
            )
            SELECT p.*, equity.symbol, equity.company_name,
                   sector.sector_code, sector.sector_name,
                   feature.close_price AS last_close,
                   feature.relative_strength_6m, feature.relative_strength_percentile,
                   feature.median_traded_value_20,
                   CASE WHEN p.pivot_price IS NULL OR feature.close_price IS NULL OR p.pivot_price = 0
                        THEN NULL ELSE (feature.close_price - p.pivot_price) / p.pivot_price * 100 END AS distance_to_pivot_pct
            FROM selected_setups AS p
            JOIN nse_equities AS equity ON equity.isin = p.isin
            LEFT JOIN LATERAL (
                SELECT membership.sector_code, sectors.name AS sector_name
                FROM security_sector_memberships AS membership
                JOIN market_sectors AS sectors ON sectors.code = membership.sector_code
                WHERE membership.isin = p.isin AND membership.effective_from <= %(as_of)s
                  AND (membership.effective_to IS NULL OR membership.effective_to >= %(as_of)s)
                ORDER BY membership.effective_from DESC LIMIT 1
            ) AS sector ON TRUE
            LEFT JOIN LATERAL (
                SELECT features.*, bars.close_price
                FROM technical_features AS features
                LEFT JOIN adjusted_daily_bars AS bars
                  ON bars.isin = features.isin AND bars.trading_date = features.trading_date
                 AND bars.adjustment_version = p.adjustment_version
                WHERE features.isin = p.isin AND features.trading_date <= %(as_of)s
                  AND features.feature_version = p.feature_version
                ORDER BY features.trading_date DESC LIMIT 1
            ) AS feature ON TRUE
            ORDER BY p.{sort_column} {direction} NULLS LAST, p.id {direction}
        """
        return self._fetch_all(statement, parameters)

    def setup_facets(self, as_of):
        return {
            "states": self._facet("p.state", as_of),
            "patternTypes": self._facet("p.pattern_type", as_of),
            "patternGroups": self._facet("p.pattern_group", as_of),
            "directions": self._facet("p.direction", as_of),
            "timeframes": self._facet("p.timeframe", as_of),
            "sectors": self._fetch_all(
                """
                SELECT membership.sector_code AS value, sectors.name AS label, COUNT(*) AS count
                FROM pattern_instances AS p
                JOIN security_sector_memberships AS membership ON membership.isin = p.isin
                  AND membership.effective_from <= %s
                  AND (membership.effective_to IS NULL OR membership.effective_to >= %s)
                JOIN market_sectors AS sectors ON sectors.code = membership.sector_code
                WHERE p.last_updated_date <= %s AND p.terminal_date IS NULL
                GROUP BY membership.sector_code, sectors.name ORDER BY count DESC, value
                """, (as_of, as_of, as_of),
            ),
        }

    def overview_summary(self, as_of):
        return self._fetch_one(
            """
            WITH requested_date AS (
                SELECT COALESCE(%s, MAX(last_updated_date)) AS value FROM pattern_instances
            ), latest_features AS (
                SELECT DISTINCT ON (isin) *
                FROM technical_features
                WHERE trading_date = COALESCE(
                    (SELECT MAX(trading_date) FROM technical_features
                     WHERE trading_date <= (SELECT value FROM requested_date)),
                    (SELECT value FROM requested_date)
                )
                ORDER BY isin, generated_at DESC
            ), selected_date AS (
                SELECT COALESCE(
                    (SELECT MAX(trading_date) FROM latest_features),
                    (SELECT value FROM requested_date)
                ) AS value
            ), benchmark_history AS (
                SELECT trading_date, close_price,
                       ROW_NUMBER() OVER (ORDER BY trading_date DESC) AS recency
                FROM index_daily_bars
                WHERE index_code = 'NIFTY 500'
                  AND trading_date <= (SELECT value FROM selected_date)
            ), benchmark_stats AS (
                SELECT COUNT(*) FILTER (WHERE recency <= 200) AS history_sessions,
                       MAX(close_price) FILTER (WHERE recency = 1) AS latest_close,
                       AVG(close_price) FILTER (WHERE recency BETWEEN 1 AND 20) AS sma20,
                       AVG(close_price) FILTER (WHERE recency BETWEEN 2 AND 21) AS prior_sma20,
                       AVG(close_price) FILTER (WHERE recency BETWEEN 1 AND 50) AS sma50,
                       AVG(close_price) FILTER (WHERE recency BETWEEN 2 AND 51) AS prior_sma50,
                       AVG(close_price) FILTER (WHERE recency BETWEEN 1 AND 200) AS sma200
                FROM benchmark_history
                WHERE recency <= 200
            )
            SELECT selected_date.value AS data_as_of,
                   COUNT(DISTINCT p.isin) FILTER (WHERE p.state = 'READY') AS ready_count,
                   COUNT(DISTINCT p.isin) FILTER (WHERE p.state = 'TRIGGERED') AS triggered_count,
                   COUNT(DISTINCT p.isin) FILTER (WHERE p.state = 'CONFIRMED') AS confirmed_count,
                   COUNT(DISTINCT failed.isin) AS failed_count,
                   COUNT(DISTINCT p.isin) FILTER (
                       WHERE p.pattern_class = 'BREAKOUT'
                         AND p.state IN ('TRIGGERED','CONFIRMED')
                   ) AS breakouts,
                   COUNT(DISTINCT p.isin) FILTER (WHERE p.pattern_type = 'FAIL-BRK') AS failed_breakouts,
                   CASE WHEN benchmark_stats.history_sessions < 200 THEN 0
                        ELSE (CASE WHEN benchmark_stats.latest_close > benchmark_stats.sma20 THEN 20 ELSE 0 END
                            + CASE WHEN benchmark_stats.latest_close > benchmark_stats.sma50 THEN 20 ELSE 0 END
                            + CASE WHEN benchmark_stats.latest_close > benchmark_stats.sma200 THEN 20 ELSE 0 END
                            + CASE WHEN benchmark_stats.sma20 > benchmark_stats.prior_sma20 THEN 20 ELSE 0 END
                            + CASE WHEN benchmark_stats.sma50 > benchmark_stats.prior_sma50 THEN 20 ELSE 0 END)
                   END AS regime_score,
                   (SELECT AVG(CASE WHEN f.distance_to_ema_20_pct > 0 THEN 100.0 ELSE 0 END) FROM latest_features f) AS above_ema20_pct,
                   (SELECT AVG(CASE WHEN f.distance_to_sma_50_pct > 0 THEN 100.0 ELSE 0 END) FROM latest_features f) AS above_sma50_pct,
                   (SELECT AVG(CASE WHEN f.distance_to_sma_200_pct > 0 THEN 100.0 ELSE 0 END) FROM latest_features f) AS above_sma200_pct,
                   (SELECT COUNT(*) FROM latest_features f WHERE f.distance_to_52_week_high_pct >= 0) AS new_52_week_highs
            FROM selected_date
            CROSS JOIN benchmark_stats
            LEFT JOIN pattern_instances p
              ON p.last_updated_date <= selected_date.value
             AND p.terminal_date IS NULL
             AND p.pattern_group = 'SETUP'
             AND p.timeframe = '1D'
            LEFT JOIN pattern_instances failed
              ON failed.last_updated_date = selected_date.value
             AND failed.state = 'FAILED'
             AND failed.pattern_group = 'SETUP'
             AND failed.timeframe = '1D'
            GROUP BY selected_date.value, benchmark_stats.history_sessions,
                     benchmark_stats.latest_close, benchmark_stats.sma20,
                     benchmark_stats.prior_sma20, benchmark_stats.sma50,
                     benchmark_stats.prior_sma50, benchmark_stats.sma200
            """, (as_of,),
        ) or {}

    def latest_scan_run(self):
        return self._fetch_one(
            """SELECT status, started_at, finished_at, securities_total,
                      securities_completed, securities_failed, metrics
               FROM market_import_runs WHERE job_type = 'PATTERN_SCAN'
               ORDER BY started_at DESC LIMIT 1""", (),
        ) or {}

    def get_pattern(self, pattern_id):
        return self._fetch_one(
            """
            SELECT p.*, equity.symbol, equity.company_name,
                   feature.close_price AS last_close,
                   feature.relative_strength_6m, feature.relative_strength_percentile,
                   CASE WHEN p.pivot_price IS NULL OR feature.close_price IS NULL OR p.pivot_price = 0
                        THEN NULL ELSE (feature.close_price - p.pivot_price) / p.pivot_price * 100 END AS distance_to_pivot_pct
            FROM pattern_instances p JOIN nse_equities equity ON equity.isin = p.isin
            LEFT JOIN LATERAL (
                SELECT features.relative_strength_6m, features.relative_strength_percentile,
                       bars.close_price
                FROM technical_features features
                LEFT JOIN adjusted_daily_bars bars
                  ON bars.isin = features.isin AND bars.trading_date = features.trading_date
                 AND bars.adjustment_version = p.adjustment_version
                WHERE features.isin = p.isin AND features.trading_date <= p.last_updated_date
                  AND features.feature_version = p.feature_version
                ORDER BY features.trading_date DESC LIMIT 1
            ) feature ON TRUE
            WHERE p.id = %s
            """, (pattern_id,),
        )

    def list_events(self, pattern_id, limit, offset):
        return self._fetch_all(
            """SELECT * FROM pattern_events WHERE pattern_instance_id = %s
               ORDER BY effective_date DESC, state_version DESC, recorded_at DESC
               LIMIT %s OFFSET %s""", (pattern_id, limit + 1, offset),
        )

    def list_chart_bars(self, isin, adjustment_version, as_of, start_date):
        date_clause, parameters = ("trading_date BETWEEN %s AND %s", (isin, adjustment_version, start_date, as_of)) if start_date else ("trading_date <= %s", (isin, adjustment_version, as_of))
        return self._fetch_all(
            f"""
            SELECT bars.trading_date, bars.open_price, bars.high_price, bars.low_price,
                   bars.close_price, bars.volume, features.ema_20, features.sma_50,
                   features.sma_200
            FROM adjusted_daily_bars bars
            LEFT JOIN LATERAL (
                SELECT feature.ema_20, feature.sma_50, feature.sma_200
                FROM technical_features feature
                WHERE feature.isin = bars.isin AND feature.trading_date = bars.trading_date
                ORDER BY feature.generated_at DESC LIMIT 1
            ) features ON TRUE
            WHERE bars.isin = %s AND bars.adjustment_version = %s AND {date_clause.replace('trading_date', 'bars.trading_date')}
            ORDER BY bars.trading_date ASC
            """, parameters,
        )

    def get_latest_adjustment_version(self, isin, as_of):
        row = self._fetch_one(
            """SELECT adjustment_version FROM adjusted_daily_bars
               WHERE isin = %s AND trading_date <= %s
               ORDER BY trading_date DESC, generated_at DESC LIMIT 1""",
            (isin, as_of),
        )
        return row.get("adjustment_version") if row else None

    def list_chart_actions(self, isin, as_of, start_date):
        if start_date is None:
            return self._fetch_all(
                """SELECT source_event_key, action_type, ex_date, raw_description
                   FROM nse_corporate_actions WHERE isin = %s AND ex_date <= %s
                   ORDER BY ex_date ASC, source_event_key ASC""", (isin, as_of),
            )
        return self._fetch_all(
            """SELECT source_event_key, action_type, ex_date, raw_description
               FROM nse_corporate_actions WHERE isin = %s AND ex_date BETWEEN %s AND %s
               ORDER BY ex_date ASC, source_event_key ASC""", (isin, start_date, as_of),
        )

    def get_security_identity(self, isin, as_of):
        return self._fetch_one(
            """
            SELECT equity.isin, equity.symbol, equity.company_name,
                   membership.sector_code, sectors.name AS sector_name,
                   macro.code AS macro_sector_code, macro.name AS macro_sector_name,
                   industry.code AS industry_code, industry.name AS industry_name,
                   basic.code AS basic_industry_code, basic.name AS basic_industry_name,
                   COALESCE(refresh.status, 'MISSING') AS classification_status,
                   snapshot.trading_date AS sector_snapshot_date,
                   snapshot.sector_strength_score, snapshot.coverage_pct,
                   snapshot.above_ema20_pct, snapshot.above_sma50_pct,
                   snapshot.above_sma200_pct, snapshot.median_relative_strength
            FROM nse_equities equity
            LEFT JOIN security_sector_memberships membership ON membership.isin = equity.isin
              AND membership.effective_from <= %s
              AND (membership.effective_to IS NULL OR membership.effective_to >= %s)
            LEFT JOIN market_sectors sectors ON sectors.code = membership.sector_code
            LEFT JOIN market_macro_sectors macro ON macro.code = sectors.macro_sector_code
            LEFT JOIN security_industry_memberships sim ON sim.isin = equity.isin
              AND sim.effective_from <= %s
              AND (sim.effective_to IS NULL OR sim.effective_to >= %s)
            LEFT JOIN market_basic_industries basic ON basic.code = sim.basic_industry_code
            LEFT JOIN market_industries industry ON industry.code = basic.industry_code
            LEFT JOIN equity_classification_refresh_state refresh ON refresh.isin = equity.isin
            LEFT JOIN LATERAL (
                SELECT daily.* FROM sector_daily_snapshots daily
                WHERE daily.sector_code = membership.sector_code AND daily.trading_date <= %s
                ORDER BY daily.trading_date DESC, daily.generated_at DESC LIMIT 1
            ) snapshot ON TRUE
            WHERE equity.isin = %s ORDER BY membership.effective_from DESC LIMIT 1
            """, (as_of, as_of, as_of, as_of, as_of, isin),
        )

    def get_latest_feature(self, isin, as_of):
        return self._fetch_one(
            """WITH target AS (
                   SELECT * FROM technical_features
                   WHERE isin = %s AND trading_date <= %s
                   ORDER BY trading_date DESC, generated_at DESC LIMIT 1
               ), raw_ranked AS (
                   SELECT feature.isin,
                          DENSE_RANK() OVER (ORDER BY feature.relative_strength_composite) AS rank_index
                   FROM technical_features feature, target
                   WHERE feature.trading_date = target.trading_date
                     AND feature.feature_version = target.feature_version
                     AND feature.relative_strength_composite IS NOT NULL
               ), ranked AS (
                   SELECT isin,
                          (rank_index - 1) * 100.0 /
                          GREATEST(1, MAX(rank_index) OVER () - 1) AS computed_percentile
                   FROM raw_ranked
               )
               SELECT features.*,
                      COALESCE(features.relative_strength_percentile, ranked.computed_percentile)
                          AS relative_strength_percentile,
                      bars.close_price
               FROM target features
               LEFT JOIN LATERAL (
                   SELECT close_price FROM adjusted_daily_bars
                   WHERE isin = features.isin AND trading_date = features.trading_date
                   ORDER BY generated_at DESC LIMIT 1
               ) bars ON TRUE
               LEFT JOIN ranked ON ranked.isin = features.isin""", (isin, as_of),
        )

    def list_security_patterns(self, isin, as_of, limit=50):
        return self._fetch_all(
            """SELECT * FROM pattern_instances WHERE isin = %s AND detected_date <= %s
               ORDER BY CASE WHEN terminal_date IS NULL THEN 0 ELSE 1 END,
                        setup_score DESC NULLS LAST, last_updated_date DESC LIMIT %s""",
            (isin, as_of, limit),
        )

    def list_chart_patterns(self, isin, as_of, start_date, limit=500):
        return self._fetch_all(
            """SELECT * FROM pattern_instances
               WHERE isin = %s AND detected_date >= %s AND detected_date <= %s
               ORDER BY detected_date, id LIMIT %s""",
            (isin, start_date, as_of, limit),
        )

    def list_security_events(self, isin, as_of, limit=25):
        return self._fetch_all(
            """SELECT event.* FROM pattern_events event
               JOIN pattern_instances pattern ON pattern.id = event.pattern_instance_id
               WHERE pattern.isin = %s AND event.effective_date <= %s
               ORDER BY event.effective_date DESC, event.recorded_at DESC LIMIT %s""",
            (isin, as_of, limit),
        )

    def _facet(self, column, as_of):
        if column not in {
            "p.state", "p.pattern_type", "p.pattern_group", "p.direction", "p.timeframe",
        }:
            raise ValueError("Unsupported facet")
        return self._fetch_all(
            f"SELECT {column} AS value, COUNT(*) AS count FROM pattern_instances p WHERE p.last_updated_date <= %s AND p.terminal_date IS NULL GROUP BY {column} ORDER BY count DESC, value",
            (as_of,),
        )

    def _fetch_one(self, statement, parameters):
        rows = self._fetch_all(statement, parameters)
        return rows[0] if rows else None

    def _fetch_all(self, statement, parameters):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]


class InMemoryPatternQueryRepository(MemorySectorRotationQueries):
    """Small contract-compatible query store for HTTP and service tests."""

    def __init__(self, patterns=(), events=(), securities=(), features=(), bars=(), run=None, actions=()):
        self.patterns = [dict(value) for value in patterns]
        self.events = [dict(value) for value in events]
        self.securities = {str(value["isin"]): dict(value) for value in securities}
        self.features = [dict(value) for value in features]
        self.bars = [dict(value) for value in bars]
        self.actions = [dict(value) for value in actions]
        self.run = dict(run or {})

    def search_securities(self, query, limit):
        text = str(query).strip().casefold()
        rows = [
            row for row in self.securities.values()
            if str(row.get("symbol") or "").casefold().startswith(text)
            or str(row.get("company_name") or "").casefold().startswith(text)
        ]
        rows.sort(key=lambda row: (
            0 if str(row.get("symbol") or "").casefold() == text else
            1 if str(row.get("symbol") or "").casefold().startswith(text) else
            2 if str(row.get("company_name") or "").casefold().startswith(text) else 3,
            str(row.get("symbol") or ""), str(row.get("isin") or ""),
        ))
        return rows[:limit]

    def list_setups(self, filters, limit, offset):
        rows = [self._joined(row, filters["as_of"]) for row in self.patterns if row["last_updated_date"] <= filters["as_of"]]
        checks = {
            "pattern_class": "pattern_class", "pattern_type": "pattern_type",
            "variant": "variant", "sector": "sector_code",
            "timeframe": "timeframe", "pattern_group": "pattern_group",
            "pattern_direction": "direction",
        }
        for key, field in checks.items():
            if filters.get(key): rows = [row for row in rows if row.get(field) == filters[key]]
        if filters.get("states"): rows = [row for row in rows if row.get("state") in filters["states"]]
        if filters.get("min_setup_score") is not None: rows = [row for row in rows if _decimal(row.get("setup_score")) >= filters["min_setup_score"]]
        if filters.get("max_setup_score") is not None: rows = [row for row in rows if _decimal(row.get("setup_score")) <= filters["max_setup_score"]]
        if filters.get("min_rs6m") is not None: rows = [row for row in rows if _decimal(row.get("relative_strength_6m")) >= filters["min_rs6m"]]
        if filters.get("min_liquidity_score") is not None:
            rows = [row for row in rows if _decimal(((row.get("measurements") or {}).get("scoring", {}).get("context_inputs", {}).get("liquidity"))) >= filters["min_liquidity_score"]]
        grouped = {}
        for row in sorted(rows, key=lambda row: (_state_rank(row.get("state")), _class_rank(row.get("pattern_class")), -_decimal(row.get("setup_score")), str(row.get("id")))):
            grouped.setdefault(row.get("isin"), row)
        rows = list(grouped.values())
        for row in rows:
            row["evidence_count"] = sum(candidate.get("isin") == row.get("isin") for candidate in self.patterns)
            liquidity = ((row.get("measurements") or {}).get("scoring", {}).get("context_inputs", {}).get("liquidity"))
            row["best_fit_score"] = (
                _decimal(row.get("setup_score")) * Decimal("0.75")
                + _decimal(row.get("context_score")) * Decimal("0.10")
                + _decimal(liquidity) * Decimal("0.15")
            ).quantize(Decimal("0.01"))
        for state in {row.get("state") for row in rows}:
            peers = sorted(
                (row for row in rows if row.get("state") == state),
                key=lambda row: (-row["best_fit_score"], -_decimal(row.get("setup_score")), str(row.get("id"))),
            )
            previous_score = None
            dense_rank = 0
            for index, row in enumerate(peers):
                if row["best_fit_score"] != previous_score:
                    dense_rank += 1
                    previous_score = row["best_fit_score"]
                row["best_fit_rank"] = dense_rank
                row["best_fit_percentile"] = Decimal("100") if len(peers) == 1 else (
                    Decimal(len(peers) - index - 1) / Decimal(len(peers) - 1) * 100
                ).quantize(Decimal("0.1"))
                row["state_candidate_count"] = len(peers)
        reverse = filters["direction"] == "desc"
        field = {"bestFit": "best_fit_score", "setupScore": "setup_score", "qualityScore": "quality_score", "maturityScore": "maturity_score", "detectedDate": "detected_date", "distanceToPivotPct": "distance_to_pivot_pct"}[filters["sort"]]
        rows.sort(key=lambda row: (row.get(field) is not None, row.get(field), str(row.get("id"))), reverse=reverse)
        for row in rows:
            row["total_count"] = len(rows)
        return rows[offset:offset + limit + 1]

    def setup_facets(self, as_of):
        def counts(field):
            values = {}
            for row in self.patterns: values[row.get(field)] = values.get(row.get(field), 0) + 1
            return [{"value": key, "count": value} for key, value in values.items() if key]
        return {
            "states": counts("state"),
            "patternTypes": counts("pattern_type"),
            "patternGroups": counts("pattern_group"),
            "directions": counts("direction"),
            "timeframes": counts("timeframe"),
            "sectors": [],
        }

    def overview_summary(self, as_of):
        selected = as_of or max((row["last_updated_date"] for row in self.patterns), default=None)
        eligible = [
            self._joined(row, selected)
            for row in self.patterns
            if row.get("last_updated_date") <= selected
            and row.get("terminal_date") is None
            and (row.get("pattern_group") or "SETUP") == "SETUP"
            and (row.get("timeframe") or "1D") == "1D"
        ]
        failures = [
            row for row in self.patterns
            if row.get("last_updated_date") == selected
            and row.get("state") == "FAILED"
            and (row.get("pattern_group") or "SETUP") == "SETUP"
            and (row.get("timeframe") or "1D") == "1D"
        ]
        distinct = lambda rows: len({row.get("isin") for row in rows})
        return {
            "data_as_of": selected,
            **{
                f"{state.lower()}_count": distinct(
                    [row for row in eligible if row.get("state") == state]
                )
                for state in ("READY", "TRIGGERED", "CONFIRMED")
            },
            "failed_count": distinct(failures),
            "breakouts": distinct([
                row for row in eligible
                if row.get("pattern_class") == "BREAKOUT"
                and row.get("state") in {"TRIGGERED", "CONFIRMED"}
            ]),
            "failed_breakouts": distinct([
                row for row in eligible if row.get("pattern_type") == "FAIL-BRK"
            ]),
            "regime_score": None, "above_ema20_pct": None,
            "above_sma50_pct": None, "above_sma200_pct": None,
            "new_52_week_highs": sum(
                feature.get("trading_date") == selected
                and feature.get("distance_to_52_week_high_pct") is not None
                and feature.get("distance_to_52_week_high_pct") >= 0
                for feature in self.features
            ),
        }

    def latest_scan_run(self): return dict(self.run)
    def get_pattern(self, pattern_id):
        row = next((row for row in self.patterns if str(row.get("id")) == pattern_id), None)
        return self._joined(row, row["last_updated_date"]) if row else None
    def list_events(self, pattern_id, limit, offset):
        rows = [row for row in self.events if str(row.get("pattern_instance_id")) == pattern_id]
        return rows[offset:offset + limit + 1]
    def list_chart_bars(self, isin, adjustment_version, as_of, start_date):
        rows = [row for row in self.bars if row.get("isin") == isin and row.get("adjustment_version") == adjustment_version and row.get("trading_date") <= as_of and (start_date is None or row.get("trading_date") >= start_date)]
        return sorted(rows, key=lambda row: row["trading_date"])
    def get_latest_adjustment_version(self, isin, as_of):
        rows = [row for row in self.bars if row.get("isin") == isin and row.get("trading_date") <= as_of and row.get("adjustment_version")]
        rows.sort(key=lambda row: row["trading_date"])
        return rows[-1].get("adjustment_version") if rows else None
    def list_chart_actions(self, isin, as_of, start_date):
        return [row for row in self.actions if row.get("isin") == isin and row.get("ex_date") <= as_of and (start_date is None or row.get("ex_date") >= start_date)]
    def get_security_identity(self, isin, as_of): return self.securities.get(isin)
    def get_latest_feature(self, isin, as_of):
        rows = [row for row in self.features if row.get("isin") == isin and row.get("trading_date") <= as_of]
        return max(rows, key=lambda row: row["trading_date"], default=None)
    def list_security_patterns(self, isin, as_of, limit=50): return [row for row in self.patterns if row.get("isin") == isin and row.get("detected_date") <= as_of][:limit]
    def list_chart_patterns(self, isin, as_of, start_date, limit=500): return sorted([row for row in self.patterns if row.get("isin") == isin and start_date <= row.get("detected_date") <= as_of], key=lambda row: (row.get("detected_date"), str(row.get("id"))))[:limit]
    def list_security_events(self, isin, as_of, limit=25):
        ids = {str(row.get("id")) for row in self.patterns if row.get("isin") == isin}
        return [row for row in self.events if str(row.get("pattern_instance_id")) in ids and row.get("effective_date") <= as_of][:limit]
    def _joined(self, row, as_of):
        result = dict(row)
        result.setdefault("timeframe", "1D")
        result.setdefault("pattern_group", "SETUP")
        result.setdefault("direction", "NEUTRAL")
        result.setdefault("interval_complete", True)
        security = self.securities.get(str(row.get("isin")), {})
        result.update({"symbol": security.get("symbol"), "company_name": security.get("company_name"), "sector_code": security.get("sector_code"), "sector_name": security.get("sector_name")})
        feature = self.get_latest_feature(str(row.get("isin")), as_of) or {}
        result.update({"last_close": feature.get("close_price"), "relative_strength_6m": feature.get("relative_strength_6m"), "relative_strength_percentile": feature.get("relative_strength_percentile"), "median_traded_value_20": feature.get("median_traded_value_20")})
        pivot, close = result.get("pivot_price"), result.get("last_close")
        result["distance_to_pivot_pct"] = None if pivot in (None, 0) or close is None else (_decimal(close) - _decimal(pivot)) / _decimal(pivot) * 100
        return result


def _decimal(value):
    return Decimal("0") if value is None else (value if isinstance(value, Decimal) else Decimal(str(value)))


def _state_rank(value):
    return {"CONFIRMED": 1, "TRIGGERED": 2, "READY": 3}.get(value, 4)


def _class_rank(value):
    return {"BREAKOUT": 1, "BASE": 2, "PULLBACK": 3}.get(value, 4)
