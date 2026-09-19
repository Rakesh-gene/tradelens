"""PostgreSQL and in-memory persistence for user watchlists."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from uuid import uuid4

from pattern_engine.sector_rotation import zone

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None


class PostgresWatchlistRepository:
    def __init__(self, dsn: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn

    def _connect(self):
        return psycopg.connect(self._dsn)

    def security_exists(self, isin: str) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT EXISTS (SELECT 1 FROM nse_equities WHERE isin = %s AND series = 'EQ')", (isin,))
            return bool(cursor.fetchone()[0])

    def add_item(self, user_id: str, isin: str, limit: int) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (user_id,))
            cursor.execute("SELECT EXISTS (SELECT 1 FROM user_watchlist WHERE user_id = %s AND isin = %s)", (user_id, isin))
            if cursor.fetchone()[0]:
                return False
            cursor.execute("SELECT COUNT(*) FROM user_watchlist WHERE user_id = %s", (user_id,))
            if int(cursor.fetchone()[0]) >= limit:
                raise ValueError(f"A watchlist can contain at most {limit} stocks")
            cursor.execute("INSERT INTO user_watchlist (user_id, isin) VALUES (%s, %s)", (user_id, isin))
        return True

    def remove_item(self, user_id: str, isin: str) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM user_watchlist WHERE user_id = %s AND isin = %s", (user_id, isin))
            return cursor.rowcount > 0

    def list_items(self, user_id: str) -> list[dict[str, object]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH latest_session AS (
                    SELECT MAX(trading_date) AS trading_date FROM technical_features
                ), latest_features AS (
                    SELECT DISTINCT ON (features.isin)
                           features.isin, features.trading_date, features.feature_version,
                           features.relative_strength_3m, features.relative_strength_composite
                    FROM technical_features features, latest_session
                    WHERE features.trading_date = latest_session.trading_date
                    ORDER BY features.isin, features.generated_at DESC, features.feature_version DESC
                ), raw_ranked AS (
                    SELECT isin, trading_date, feature_version,
                           DENSE_RANK() OVER (PARTITION BY trading_date, feature_version ORDER BY relative_strength_composite) AS rank_index
                    FROM latest_features WHERE relative_strength_composite IS NOT NULL
                ), ranked AS (
                    SELECT isin, trading_date, feature_version,
                           (rank_index - 1) * 100.0 /
                           GREATEST(1, MAX(rank_index) OVER (PARTITION BY trading_date, feature_version) - 1) AS computed_percentile
                    FROM raw_ranked
                ), sector_rs AS (
                    SELECT membership.sector_code, latest_session.trading_date,
                           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_features.relative_strength_3m)
                               AS relative_strength
                    FROM latest_session
                    JOIN security_sector_memberships membership
                      ON membership.effective_from <= latest_session.trading_date
                     AND (membership.effective_to IS NULL OR membership.effective_to >= latest_session.trading_date)
                    JOIN latest_features ON latest_features.isin = membership.isin
                    WHERE latest_features.relative_strength_3m IS NOT NULL
                    GROUP BY membership.sector_code, latest_session.trading_date
                )
                SELECT watch.isin, watch.added_at, equity.symbol, equity.company_name,
                       sector.sector_code, sector.sector_name,
                       feature.trading_date AS data_as_of, feature.close_price AS last_close,
                       feature.previous_close, feature.ema_20, feature.sma_50, feature.sma_200,
                       feature.distance_to_52_week_high_pct, feature.volume_ratio_5_to_50,
                       feature.relative_strength_1m, feature.relative_strength_3m,
                       feature.relative_strength_6m, feature.relative_strength_12m,
                       COALESCE(feature.relative_strength_percentile, ranked.computed_percentile)
                           AS relative_strength_percentile,
                       sector_rs.relative_strength AS sector_relative_strength,
                       snapshot.sector_strength_score,
                       pattern.id AS pattern_id, pattern.pattern_class, pattern.pattern_type,
                       pattern.variant, pattern.state, pattern.setup_score, pattern.pivot_price,
                       pattern.support_price, pattern.invalidation_price,
                       recent_event.new_state AS recent_event_state,
                       rotation_history.points AS rotation_history
                FROM user_watchlist watch
                JOIN nse_equities equity ON equity.isin = watch.isin
                LEFT JOIN LATERAL (
                    SELECT membership.sector_code, sectors.name AS sector_name
                    FROM security_sector_memberships membership
                    JOIN market_sectors sectors ON sectors.code = membership.sector_code
                    WHERE membership.isin = watch.isin AND membership.effective_to IS NULL
                    ORDER BY membership.effective_from DESC LIMIT 1
                ) sector ON TRUE
                LEFT JOIN LATERAL (
                    SELECT features.trading_date, features.ema_20, features.sma_50,
                           features.sma_200, features.distance_to_52_week_high_pct,
                           features.volume_ratio_5_to_50, features.relative_strength_1m,
                           features.relative_strength_3m, features.relative_strength_6m,
                           features.relative_strength_12m, features.relative_strength_percentile,
                           bars.close_price, bars.previous_close
                    FROM technical_features features
                    LEFT JOIN LATERAL (
                        SELECT current_bar.close_price,
                               (SELECT prior.close_price FROM adjusted_daily_bars prior
                                WHERE prior.isin = features.isin
                                  AND prior.adjustment_version = current_bar.adjustment_version
                                  AND prior.trading_date < current_bar.trading_date
                                ORDER BY prior.trading_date DESC, prior.generated_at DESC LIMIT 1) AS previous_close
                        FROM adjusted_daily_bars current_bar
                        WHERE current_bar.isin = features.isin AND current_bar.trading_date = features.trading_date
                        ORDER BY current_bar.generated_at DESC LIMIT 1
                    ) bars ON TRUE
                    WHERE features.isin = watch.isin
                    ORDER BY features.trading_date DESC, features.generated_at DESC LIMIT 1
                ) feature ON TRUE
                LEFT JOIN ranked ON ranked.isin = watch.isin
                  AND ranked.trading_date = feature.trading_date
                LEFT JOIN LATERAL (
                    SELECT daily.median_relative_strength, daily.sector_strength_score
                    FROM sector_daily_snapshots daily
                    WHERE daily.sector_code = sector.sector_code
                      AND (feature.trading_date IS NULL OR daily.trading_date <= feature.trading_date)
                    ORDER BY daily.trading_date DESC, daily.generated_at DESC LIMIT 1
                ) snapshot ON TRUE
                LEFT JOIN sector_rs ON sector_rs.sector_code = sector.sector_code
                  AND sector_rs.trading_date = feature.trading_date
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
                        WHERE features.isin = watch.isin
                        ORDER BY features.trading_date DESC, features.generated_at DESC, features.feature_version DESC
                        LIMIT 5
                    ) historical
                    WHERE historical.relative_strength_1m IS NOT NULL
                      AND historical.relative_strength_3m IS NOT NULL
                ) rotation_history ON TRUE
                LEFT JOIN LATERAL (
                    SELECT id, pattern_class, pattern_type, variant, state, setup_score,
                           pivot_price, support_price, invalidation_price
                    FROM pattern_instances
                    WHERE isin = watch.isin AND terminal_date IS NULL
                      AND pattern_group = 'SETUP' AND timeframe = '1D'
                      AND pattern_class IN ('BASE', 'BREAKOUT', 'PULLBACK')
                    ORDER BY CASE state WHEN 'CONFIRMED' THEN 1 WHEN 'TRIGGERED' THEN 2
                                WHEN 'READY' THEN 3 WHEN 'MATURE' THEN 4 ELSE 5 END,
                             setup_score DESC NULLS LAST, detected_date DESC, id
                    LIMIT 1
                ) pattern ON TRUE
                LEFT JOIN LATERAL (
                    SELECT event.new_state
                    FROM pattern_instances recent_pattern
                    JOIN pattern_events event ON event.pattern_instance_id = recent_pattern.id
                    WHERE recent_pattern.isin = watch.isin
                      AND recent_pattern.pattern_group = 'SETUP' AND recent_pattern.timeframe = '1D'
                    ORDER BY event.effective_date DESC, event.recorded_at DESC LIMIT 1
                ) recent_event ON TRUE
                WHERE watch.user_id = %s
                ORDER BY watch.added_at DESC, watch.isin
                """,
                (user_id,),
            )
            columns = [column.name for column in cursor.description]
            return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_recent_events(self, user_id: str, limit: int) -> list[dict[str, object]]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM (
                SELECT 'PATTERN' AS activity_type, event.id AS event_id,
                       event.pattern_instance_id, event.event_type,
                       event.effective_date, event.previous_state, event.new_state,
                       pattern.pattern_type, pattern.variant,
                       watch.isin, equity.symbol, equity.company_name,
                       NULL::NUMERIC AS strength, NULL::NUMERIC AS momentum,
                       NULL::TEXT AS methodology_version, event.recorded_at
                FROM user_watchlist watch
                JOIN nse_equities equity ON equity.isin = watch.isin
                JOIN pattern_instances pattern ON pattern.isin = watch.isin
                  AND pattern.pattern_group = 'SETUP' AND pattern.timeframe = '1D'
                JOIN pattern_events event ON event.pattern_instance_id = pattern.id
                WHERE watch.user_id = %s
                  AND event.event_type IN ('PATTERN_DETECTED', 'STATE_CHANGED', 'TRIGGERED',
                                           'CONFIRMED', 'FAILED', 'INVALIDATED', 'EXPIRED')
                UNION ALL
                SELECT 'QUADRANT' AS activity_type, event.id AS event_id,
                       NULL::UUID AS pattern_instance_id, event.event_type,
                       event.effective_date, event.previous_zone AS previous_state,
                       event.new_zone AS new_state, NULL::TEXT AS pattern_type,
                       NULL::TEXT AS variant, watch.isin, equity.symbol, equity.company_name,
                       event.strength, event.momentum, event.methodology_version, event.recorded_at
                FROM user_watchlist watch
                JOIN nse_equities equity ON equity.isin = watch.isin
                JOIN watchlist_quadrant_events event
                  ON event.user_id = watch.user_id AND event.isin = watch.isin
                WHERE watch.user_id = %s
                ) activity
                ORDER BY effective_date DESC, recorded_at DESC, event_id
                LIMIT %s
                """,
                (user_id, user_id, limit),
            )
            columns = [column.name for column in cursor.description]
            return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in cursor.fetchall()]

    def reconcile_quadrants(self, as_of: date | None = None) -> int:
        """Persist one notification-ready event when a watched stock changes zone."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('watchlist-quadrants', 0))")
            cursor.execute(
                """
                SELECT watch.user_id, watch.isin, feature.trading_date AS data_as_of,
                       feature.relative_strength_3m AS strength,
                       feature.relative_strength_1m - feature.relative_strength_3m / 3 AS momentum,
                       state.zone AS previous_zone, state.strength AS previous_strength,
                       state.momentum AS previous_momentum, state.data_as_of AS previous_data_as_of
                FROM user_watchlist watch
                LEFT JOIN LATERAL (
                    SELECT trading_date, relative_strength_1m, relative_strength_3m
                    FROM technical_features
                    WHERE isin = watch.isin AND (%s::DATE IS NULL OR trading_date <= %s::DATE)
                    ORDER BY trading_date DESC, generated_at DESC LIMIT 1
                ) feature ON TRUE
                LEFT JOIN watchlist_quadrant_state state
                  ON state.user_id = watch.user_id AND state.isin = watch.isin
                ORDER BY watch.user_id, watch.isin
                """,
                (as_of, as_of),
            )
            columns = [column.name for column in cursor.description]
            rows = [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in cursor.fetchall()]
            created = 0
            for row in rows:
                if (row.get("previous_data_as_of") is not None and row.get("data_as_of") is not None
                        and row["data_as_of"] < row["previous_data_as_of"]):
                    continue
                current_zone = zone(row.get("strength"), row.get("momentum"))
                previous_zone = row.get("previous_zone")
                effective_date = row.get("data_as_of")
                event_type = _quadrant_event_type(previous_zone, current_zone)
                if event_type and effective_date is not None:
                    cursor.execute(
                        """INSERT INTO watchlist_quadrant_events
                           (id, user_id, isin, event_type, previous_zone, new_zone,
                            strength, momentum, effective_date)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (user_id, isin, effective_date) DO NOTHING""",
                        (str(uuid4()), row["user_id"], row["isin"], event_type,
                         previous_zone, current_zone, row.get("strength"), row.get("momentum"), effective_date),
                    )
                    created += cursor.rowcount
                cursor.execute(
                    """INSERT INTO watchlist_quadrant_state
                       (user_id, isin, zone, strength, momentum, data_as_of, observed_at)
                       VALUES (%s, %s, %s, %s, %s, %s, NOW())
                       ON CONFLICT (user_id, isin) DO UPDATE SET
                         zone = EXCLUDED.zone, strength = EXCLUDED.strength,
                         momentum = EXCLUDED.momentum, data_as_of = EXCLUDED.data_as_of,
                         observed_at = NOW()""",
                    (row["user_id"], row["isin"], current_zone, row.get("strength"),
                     row.get("momentum"), effective_date),
                )
        return created


class InMemoryWatchlistRepository:
    def __init__(self, securities: Iterable[dict[str, object]] | None = None, events: Iterable[dict[str, object]] | None = None) -> None:
        self._items: dict[str, list[str]] = {}
        self._securities = None if securities is None else {str(item["isin"]): dict(item) for item in securities}
        self._events = [dict(event) for event in events or ()]
        self._quadrant_state: dict[tuple[str, str], dict[str, object]] = {}

    def security_exists(self, isin: str) -> bool:
        return self._securities is None or isin in self._securities

    def add_item(self, user_id: str, isin: str, limit: int) -> bool:
        items = self._items.setdefault(str(user_id), [])
        if isin in items:
            return False
        if len(items) >= limit:
            raise ValueError(f"A watchlist can contain at most {limit} stocks")
        items.insert(0, isin)
        return True

    def remove_item(self, user_id: str, isin: str) -> bool:
        items = self._items.setdefault(str(user_id), [])
        if isin not in items:
            return False
        items.remove(isin)
        return True

    def list_items(self, user_id: str) -> list[dict[str, object]]:
        return [
            {**(self._securities or {}).get(isin, {}), "isin": isin,
             "symbol": (self._securities or {}).get(isin, {}).get("symbol", isin),
             "company_name": (self._securities or {}).get(isin, {}).get("company_name", isin),
             "added_at": (self._securities or {}).get(isin, {}).get("added_at"),
             "data_as_of": (self._securities or {}).get(isin, {}).get("data_as_of")}
            for isin in self._items.get(str(user_id), [])
        ]

    def list_recent_events(self, user_id: str, limit: int) -> list[dict[str, object]]:
        watched = set(self._items.get(str(user_id), []))
        rows = [event for event in self._events if event.get("isin") in watched]
        return sorted(rows, key=lambda event: (event.get("effective_date") or "", event.get("recorded_at") or ""), reverse=True)[:limit]

    def reconcile_quadrants(self, as_of: date | None = None) -> int:
        created = 0
        for user_id, isins in self._items.items():
            for isin in isins:
                security = (self._securities or {}).get(isin, {})
                effective_date = security.get("data_as_of")
                if as_of is not None and effective_date is not None and effective_date > as_of:
                    continue
                strength = security.get("relative_strength_3m")
                short = security.get("relative_strength_1m")
                momentum = None if strength is None or short is None else float(short) - float(strength) / 3
                current_zone = zone(strength, momentum)
                key = (user_id, isin)
                previous = self._quadrant_state.get(key)
                if (previous and previous.get("data_as_of") is not None and effective_date is not None
                        and effective_date < previous["data_as_of"]):
                    continue
                previous_zone = previous.get("zone") if previous else None
                event_type = _quadrant_event_type(previous_zone, current_zone)
                if event_type and effective_date is not None:
                    self._events.append({
                        "activity_type": "QUADRANT", "event_id": str(uuid4()),
                        "event_type": event_type, "effective_date": effective_date,
                        "previous_state": previous_zone, "new_state": current_zone,
                        "strength": strength, "momentum": momentum,
                        "methodology_version": "sector-rotation-v1", "isin": isin,
                        "symbol": security.get("symbol", isin),
                        "company_name": security.get("company_name", isin),
                    })
                    created += 1
                self._quadrant_state[key] = {"zone": current_zone, "data_as_of": effective_date}
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
