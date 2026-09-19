"""Persistence and read models for the NSE index-analysis universe."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from uuid import uuid4

from pattern_engine.sector_rotation import zone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None


class PostgresIndexRepository:
    def __init__(self, dsn: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn

    def _connect(self):
        return psycopg.connect(self._dsn)

    def list_enabled(self) -> list[dict[str, object]]:
        return self._fetch_all(
            """SELECT code, name, category, engine_isin
               FROM market_indices
               WHERE is_enabled AND engine_isin IS NOT NULL
               ORDER BY CASE category WHEN 'BROAD_MARKET' THEN 1 WHEN 'SECTORAL' THEN 2 ELSE 3 END,
                        name, code""", ()
        )

    def index_by_code(self, code: str) -> dict[str, object] | None:
        rows = self._fetch_all(
            """SELECT code, name, engine_isin
               FROM market_indices
               WHERE code = %s AND is_enabled AND engine_isin IS NOT NULL""",
            (code,),
        )
        return rows[0] if rows else None

    def sync_bars_to_engine(self, index_code: str, engine_isin: str, from_date: date, to_date: date) -> int:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO nse_daily_bars_raw
                   (isin, trading_date, open_price, high_price, low_price, close_price,
                    volume, nse_series, source_name, source_checksum)
                   SELECT %s, trading_date, open_price, high_price, low_price, close_price,
                          COALESCE(volume, 0), 'INDEX', source_name, source_checksum
                   FROM index_daily_bars
                   WHERE index_code = %s AND trading_date BETWEEN %s AND %s
                   ON CONFLICT (isin, trading_date) DO UPDATE SET
                     open_price = EXCLUDED.open_price, high_price = EXCLUDED.high_price,
                     low_price = EXCLUDED.low_price, close_price = EXCLUDED.close_price,
                     volume = EXCLUDED.volume, source_name = EXCLUDED.source_name,
                     source_checksum = EXCLUDED.source_checksum,
                     raw_revision = CASE WHEN nse_daily_bars_raw.source_checksum IS DISTINCT FROM EXCLUDED.source_checksum
                                         THEN nse_daily_bars_raw.raw_revision + 1 ELSE nse_daily_bars_raw.raw_revision END,
                     imported_at = NOW()
                   WHERE nse_daily_bars_raw.source_checksum IS DISTINCT FROM EXCLUDED.source_checksum""",
                (engine_isin, index_code, from_date, to_date),
            )
            return cursor.rowcount

    def overview_rows(self) -> list[dict[str, object]]:
        return self._fetch_all(
            """SELECT index.code, index.name, index.category, index.engine_isin,
                      bar.trading_date AS data_as_of, bar.close_price AS last_close,
                      bar.previous_close, feature.ema_20, feature.sma_50, feature.sma_200,
                      feature.distance_to_52_week_high_pct,
                      feature.relative_strength_1m, feature.relative_strength_3m,
                      feature.relative_strength_6m, feature.relative_strength_12m,
                      pattern.id AS pattern_id, pattern.pattern_type, pattern.variant,
                      pattern.state, pattern.setup_score, pattern.pivot_price,
                      pattern.support_price, pattern.invalidation_price,
                      rotation_history.points AS rotation_history
               FROM market_indices index
               LEFT JOIN LATERAL (
                 SELECT current.trading_date, current.close_price,
                        (SELECT previous.close_price FROM index_daily_bars previous
                         WHERE previous.index_code = current.index_code
                           AND previous.trading_date < current.trading_date
                         ORDER BY previous.trading_date DESC LIMIT 1) AS previous_close
                 FROM index_daily_bars current WHERE current.index_code = index.code
                 ORDER BY current.trading_date DESC LIMIT 1
               ) bar ON TRUE
               LEFT JOIN LATERAL (
                 SELECT * FROM technical_features
                 WHERE isin = index.engine_isin
                 ORDER BY trading_date DESC, generated_at DESC LIMIT 1
               ) feature ON TRUE
               LEFT JOIN LATERAL (
                 SELECT jsonb_agg(
                            jsonb_build_object(
                                'date', historical.trading_date,
                                'strength', historical.relative_strength_3m,
                                'momentum', historical.relative_strength_1m - historical.relative_strength_3m / 3.0
                            ) ORDER BY historical.trading_date
                        ) AS points
                 FROM (
                   SELECT DISTINCT ON (features.trading_date)
                          features.trading_date, features.relative_strength_1m,
                          features.relative_strength_3m
                   FROM technical_features features
                   WHERE features.isin = index.engine_isin
                   ORDER BY features.trading_date DESC, features.generated_at DESC, features.feature_version DESC
                   LIMIT 5
                 ) historical
                 WHERE historical.relative_strength_1m IS NOT NULL
                   AND historical.relative_strength_3m IS NOT NULL
               ) rotation_history ON TRUE
               LEFT JOIN LATERAL (
                 SELECT id, pattern_type, variant, state, setup_score,
                        pivot_price, support_price, invalidation_price, engine_version
                 FROM pattern_instances
                 WHERE isin = index.engine_isin AND terminal_date IS NULL
                   AND pattern_group = 'SETUP' AND timeframe = '1D'
                   AND pattern_class IN ('BASE', 'BREAKOUT', 'PULLBACK')
                 ORDER BY CASE state WHEN 'CONFIRMED' THEN 1 WHEN 'TRIGGERED' THEN 2
                            WHEN 'READY' THEN 3 WHEN 'MATURE' THEN 4 ELSE 5 END,
                          setup_score DESC NULLS LAST, detected_date DESC, id
                 LIMIT 1
               ) pattern ON TRUE
               WHERE index.is_enabled AND index.engine_isin IS NOT NULL
               ORDER BY CASE index.category WHEN 'BROAD_MARKET' THEN 1 WHEN 'SECTORAL' THEN 2 ELSE 3 END,
                        index.name, index.code""", ()
        )

    def list_recent_events(self, limit: int) -> list[dict[str, object]]:
        return self._fetch_all(
            """SELECT * FROM (
                 SELECT 'PATTERN' AS activity_type, event.id AS event_id,
                        event.pattern_instance_id, event.event_type, event.effective_date,
                        event.previous_state, event.new_state, pattern.pattern_type, pattern.variant,
                        index.code AS index_code, index.name AS index_name,
                        index.engine_isin, NULL::NUMERIC AS strength, NULL::NUMERIC AS momentum,
                        NULL::TEXT AS methodology_version, event.recorded_at
                 FROM market_indices index
                 JOIN pattern_instances pattern ON pattern.isin = index.engine_isin
                   AND pattern.pattern_group = 'SETUP' AND pattern.timeframe = '1D'
                 JOIN pattern_events event ON event.pattern_instance_id = pattern.id
                 WHERE index.is_enabled
                   AND event.event_type IN ('PATTERN_DETECTED', 'STATE_CHANGED', 'TRIGGERED',
                                            'CONFIRMED', 'FAILED', 'INVALIDATED', 'EXPIRED')
                 UNION ALL
                 SELECT 'QUADRANT' AS activity_type, event.id AS event_id,
                        NULL::UUID AS pattern_instance_id, event.event_type, event.effective_date,
                        event.previous_zone AS previous_state, event.new_zone AS new_state,
                        NULL::TEXT AS pattern_type, NULL::TEXT AS variant,
                        index.code AS index_code, index.name AS index_name,
                        index.engine_isin, event.strength, event.momentum,
                        event.methodology_version, event.recorded_at
                 FROM index_quadrant_events event
                 JOIN market_indices index ON index.code = event.index_code
                 WHERE index.is_enabled
               ) activity
               ORDER BY effective_date DESC, recorded_at DESC, event_id
               LIMIT %s""",
            (limit,),
        )

    def reconcile_quadrants(self, as_of: date | None = None) -> int:
        """Persist notification-ready events when an enabled index changes quadrant."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('index-quadrants', 0))")
            cursor.execute(
                """SELECT index.code AS index_code, feature.trading_date AS data_as_of,
                          feature.relative_strength_3m AS strength,
                          feature.relative_strength_1m - feature.relative_strength_3m / 3 AS momentum,
                          state.zone AS previous_zone, state.data_as_of AS previous_data_as_of
                   FROM market_indices index
                   LEFT JOIN LATERAL (
                     SELECT trading_date, relative_strength_1m, relative_strength_3m
                     FROM technical_features
                     WHERE isin = index.engine_isin
                       AND (%s::DATE IS NULL OR trading_date <= %s::DATE)
                     ORDER BY trading_date DESC, generated_at DESC LIMIT 1
                   ) feature ON TRUE
                   LEFT JOIN index_quadrant_state state ON state.index_code = index.code
                   WHERE index.is_enabled AND index.engine_isin IS NOT NULL
                   ORDER BY index.code""",
                (as_of, as_of),
            )
            columns = [column.name for column in cursor.description]
            rows = [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in cursor.fetchall()]
            created = 0
            for row in rows:
                effective_date = row.get("data_as_of")
                if (row.get("previous_data_as_of") is not None and effective_date is not None
                        and effective_date < row["previous_data_as_of"]):
                    continue
                current_zone = zone(row.get("strength"), row.get("momentum"))
                previous_zone = row.get("previous_zone")
                event_type = _quadrant_event_type(previous_zone, current_zone)
                if event_type and effective_date is not None:
                    cursor.execute(
                        """INSERT INTO index_quadrant_events
                           (id, index_code, event_type, previous_zone, new_zone,
                            strength, momentum, effective_date)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (index_code, effective_date) DO NOTHING""",
                        (str(uuid4()), row["index_code"], event_type, previous_zone,
                         current_zone, row.get("strength"), row.get("momentum"), effective_date),
                    )
                    created += cursor.rowcount
                cursor.execute(
                    """INSERT INTO index_quadrant_state
                       (index_code, zone, strength, momentum, data_as_of, observed_at)
                       VALUES (%s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (index_code) DO UPDATE SET
                         zone = EXCLUDED.zone, strength = EXCLUDED.strength,
                         momentum = EXCLUDED.momentum, data_as_of = EXCLUDED.data_as_of,
                         observed_at = NOW()""",
                    (row["index_code"], current_zone, row.get("strength"),
                     row.get("momentum"), effective_date),
                )
        return created

    def _fetch_all(self, statement, parameters):
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]


class InMemoryIndexRepository:
    def __init__(self, rows=(), events=()):
        self.rows = [dict(row) for row in rows]
        self.events = [dict(row) for row in events]
        self.quadrant_state = {}

    def list_enabled(self): return [dict(row) for row in self.rows]
    def index_by_code(self, code):
        row = next((item for item in self.rows if item.get("code") == code and item.get("engine_isin")), None)
        return None if row is None else dict(row)
    def overview_rows(self): return [dict(row) for row in self.rows]
    def sync_bars_to_engine(self, index_code, engine_isin, from_date, to_date): return 0
    def list_recent_events(self, limit): return [dict(row) for row in self.events[:limit]]
    def reconcile_quadrants(self, as_of=None):
        created = 0
        for row in self.rows:
            effective_date = row.get("data_as_of")
            if as_of is not None and effective_date is not None and effective_date > as_of:
                continue
            strength, short = row.get("relative_strength_3m"), row.get("relative_strength_1m")
            momentum = None if strength is None or short is None else float(short) - float(strength) / 3
            current_zone = zone(strength, momentum)
            previous = self.quadrant_state.get(row["code"])
            previous_zone = previous.get("zone") if previous else None
            event_type = _quadrant_event_type(previous_zone, current_zone)
            if event_type and effective_date is not None:
                self.events.insert(0, {
                    "activity_type": "QUADRANT", "event_id": str(uuid4()),
                    "event_type": event_type, "effective_date": effective_date,
                    "previous_state": previous_zone, "new_state": current_zone,
                    "index_code": row["code"], "index_name": row.get("name"),
                    "engine_isin": row.get("engine_isin"), "strength": strength,
                    "momentum": momentum, "methodology_version": "sector-rotation-v1",
                })
                created += 1
            self.quadrant_state[row["code"]] = {"zone": current_zone, "data_as_of": effective_date}
        return created


def _quadrant_event_type(previous_zone, current_zone):
    if previous_zone is None:
        return "QUADRANT_ENTERED" if current_zone != "UNAVAILABLE" else None
    if previous_zone == current_zone:
        return None
    if previous_zone == "UNAVAILABLE":
        return "QUADRANT_ENTERED" if current_zone != "UNAVAILABLE" else None
    if current_zone == "UNAVAILABLE":
        return "QUADRANT_LEFT"
    return "QUADRANT_CHANGED"
