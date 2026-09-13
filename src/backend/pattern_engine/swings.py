"""Look-ahead-safe swing points and deterministic support/resistance zones."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from pattern_engine.enums import SwingType, ZoneType
from pattern_engine.models import PriceZone, SwingPoint, serialize_value
from repositories.market_data import MarketDataRepository


_HUNDRED = Decimal("100")
_MIN_MOVE_PCT = Decimal("4")
_MIN_ZONE_TOLERANCE = Decimal("0.75")
_MAX_ZONE_TOLERANCE = Decimal("2")
_MIN_BREAKOUT_BUFFER = Decimal("0.30")
_MAX_BREAKOUT_BUFFER = Decimal("1")


class SwingZoneService:
    """Persist a reproducible swing/zone snapshot for a single security."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def rebuild(
        self, isin: str, from_date: date, to_date: date, adjustment_version: str,
        feature_version: str, data_version: str, *, as_of: date | None = None,
    ) -> tuple[int, int]:
        bars = self._repository.load_adjusted_bars(isin, from_date, to_date, adjustment_version)
        features = self._repository.load_technical_features(isin, from_date, to_date, feature_version)
        feature_by_date = {_bar_date(row): row for row in features}
        existing_swings = self._repository.load_swing_points(
            isin, from_date, to_date, feature_version, as_of=as_of,
        )
        swings = _assign_swing_ids(
            detect_swings(bars, feature_by_date, as_of=as_of),
            existing_swings,
            feature_version,
        )
        zones = build_price_zones(swings, as_of=as_of, lookback_start=from_date)
        existing_zones = self._repository.load_price_zones(
            isin, from_date, to_date, feature_version, as_of=as_of,
        )
        zones = _preserve_zone_ids(zones, existing_zones)
        swing_rows = [_swing_row(swing, feature_version, data_version) for swing in swings]
        zone_rows = [_zone_row(zone, feature_version, data_version) for zone in zones]
        return self._repository.upsert_swing_points(swing_rows), self._repository.upsert_price_zones(zone_rows)


def detect_swings(
    bars: Sequence[Mapping[str, object]],
    features_by_date: Mapping[date, Mapping[str, object]] | None = None,
    *,
    left_bars: int = 3,
    right_bars: int = 3,
    as_of: date | None = None,
) -> list[SwingPoint]:
    """Return raw pivots whose third subsequent *trading session* is known.

    `right_bars` operates on the supplied ordered sessions, never calendar days.
    The optional as-of boundary makes replay callers unable to observe future
    pivots before their confirmation session.
    """

    if left_bars < 1 or right_bars < 1:
        raise ValueError("left_bars and right_bars must be positive")
    ordered = sorted(bars, key=lambda bar: _bar_date(bar))
    feature_rows = features_by_date or {}
    candidates: list[SwingPoint] = []
    for index in range(left_bars, len(ordered) - right_bars):
        current = ordered[index]
        pivot_date = _bar_date(current)
        confirmation_date = _bar_date(ordered[index + right_bars])
        if as_of is not None and confirmation_date > as_of:
            continue
        high = _decimal(current["high_price"])
        low = _decimal(current["low_price"])
        left = ordered[index - left_bars:index]
        right = ordered[index + 1:index + right_bars + 1]
        natr = _optional_decimal(feature_rows.get(pivot_date, {}).get("natr_14"))
        if high >= max(_decimal(bar["high_price"]) for bar in left) and high >= max(_decimal(bar["high_price"]) for bar in right):
            candidates.append(SwingPoint(None, str(current["isin"]), pivot_date, confirmation_date, SwingType.HIGH, high, natr, None, False))
        if low <= min(_decimal(bar["low_price"]) for bar in left) and low <= min(_decimal(bar["low_price"]) for bar in right):
            candidates.append(SwingPoint(None, str(current["isin"]), pivot_date, confirmation_date, SwingType.LOW, low, natr, None, False))
    candidates.sort(key=lambda item: (item.pivot_date, item.swing_type.value))
    return _mark_meaningful(candidates)


def build_price_zones(
    swings: Sequence[SwingPoint], *, as_of: date | None = None, lookback_start: date | None = None
) -> list[PriceZone]:
    """Cluster confirmed meaningful swings independently by high/low type."""

    visible = [
        swing for swing in swings
        if swing.is_meaningful
        and (as_of is None or swing.confirmation_date <= as_of)
        and (lookback_start is None or swing.pivot_date >= lookback_start)
    ]
    zones: list[PriceZone] = []
    for swing_type, zone_type in ((SwingType.HIGH, ZoneType.RESISTANCE), (SwingType.LOW, ZoneType.SUPPORT)):
        relevant = [swing for swing in visible if swing.swing_type is swing_type]
        for cluster in _cluster_swings(relevant):
            prices = sorted(swing.price for swing in cluster)
            center = Decimal(str(median(prices)))
            natr_values = [swing.natr for swing in cluster if swing.natr is not None]
            natr = Decimal(str(median(natr_values))) if natr_values else Decimal("1.5")
            tolerance = _clamp(natr * Decimal("0.5"), _MIN_ZONE_TOLERANCE, _MAX_ZONE_TOLERANCE)
            buffer = _clamp(natr * Decimal("0.25"), _MIN_BREAKOUT_BUFFER, _MAX_BREAKOUT_BUFFER)
            source_ids = tuple(sorted(swing.swing_id or _swing_key(swing) for swing in cluster))
            zone_id = str(uuid5(NAMESPACE_URL, f"zone:{cluster[0].isin}:{zone_type.value}:{'|'.join(source_ids)}"))
            last_test = max(s.pivot_date for s in cluster)
            confirmation = max(s.confirmation_date for s in cluster)
            zones.append(PriceZone(zone_id, cluster[0].isin, zone_type, min(s.pivot_date for s in cluster), last_test, center, tolerance, _dispersion(prices, center), source_ids, len(cluster), buffer, last_test, confirmation))
    return sorted(zones, key=lambda zone: (zone.zone_type.value, zone.median_price, zone.start_date))


def _mark_meaningful(candidates: Sequence[SwingPoint]) -> list[SwingPoint]:
    last_meaningful: SwingPoint | None = None
    result: list[SwingPoint] = []
    for swing in candidates:
        is_alternating = last_meaningful is None or swing.swing_type is not last_meaningful.swing_type
        move = None if last_meaningful is None or not is_alternating else abs(swing.price - last_meaningful.price) / last_meaningful.price * _HUNDRED
        threshold = max(_MIN_MOVE_PCT, (swing.natr or Decimal("0")) * Decimal("2"))
        meaningful = last_meaningful is None or is_alternating and move is not None and move >= threshold
        identified = SwingPoint(str(uuid5(NAMESPACE_URL, _swing_key(swing))), swing.isin, swing.pivot_date, swing.confirmation_date, swing.swing_type, swing.price, swing.natr, move, meaningful)
        result.append(identified)
        if meaningful:
            last_meaningful = identified
    return result


def _cluster_swings(swings: Sequence[SwingPoint]) -> list[list[SwingPoint]]:
    clusters: list[list[SwingPoint]] = []
    for swing in sorted(swings, key=lambda item: (item.price, item.pivot_date, item.swing_id or "")):
        if not clusters:
            clusters.append([swing])
            continue
        current = clusters[-1]
        center = Decimal(str(median(sorted(item.price for item in current))))
        natr = swing.natr or Decimal("1.5")
        tolerance = _clamp(natr * Decimal("0.5"), _MIN_ZONE_TOLERANCE, _MAX_ZONE_TOLERANCE)
        if abs(swing.price - center) / center * _HUNDRED <= tolerance:
            current.append(swing)
        else:
            clusters.append([swing])
    return clusters


def _bar_date(bar: Mapping[str, object]) -> date:
    value = bar["trading_date"]
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


def _dispersion(prices: Sequence[Decimal], center: Decimal) -> Decimal:
    return (max(prices) - min(prices)) / center * _HUNDRED if center else Decimal("0")


def _swing_key(swing: SwingPoint) -> str:
    return f"swing:{swing.isin}:{swing.pivot_date.isoformat()}:{swing.swing_type.value}"


def _assign_swing_ids(
    swings: Sequence[SwingPoint], existing_rows: Sequence[Mapping[str, object]], feature_version: str,
) -> list[SwingPoint]:
    existing_ids = {
        (_bar_date({"trading_date": row["pivot_date"]}), str(row["swing_type"])): str(row["id"])
        for row in existing_rows
        if row.get("id") is not None
    }
    return [
        replace(
            swing,
            swing_id=existing_ids.get(
                (swing.pivot_date, swing.swing_type.value),
                str(uuid5(NAMESPACE_URL, f"{_swing_key(swing)}:{feature_version}")),
            ),
        )
        for swing in swings
    ]


def _preserve_zone_ids(
    zones: Sequence[PriceZone], existing_rows: Sequence[Mapping[str, object]],
) -> list[PriceZone]:
    existing_ids = {
        (str(row["zone_type"]), date.fromisoformat(str(row["start_date"])), date.fromisoformat(str(row["end_date"]))): str(row["id"])
        for row in existing_rows
        if row.get("id") is not None
    }
    return [
        replace(
            zone,
            zone_id=existing_ids.get(
                (zone.zone_type.value, zone.start_date, zone.end_date), zone.zone_id,
            ),
        )
        for zone in zones
    ]


def _swing_row(swing: SwingPoint, feature_version: str, data_version: str) -> dict[str, object]:
    row = {
        "id": swing.swing_id or str(uuid5(NAMESPACE_URL, f"{_swing_key(swing)}:{feature_version}")), "isin": swing.isin,
        "pivot_date": swing.pivot_date, "confirmation_date": swing.confirmation_date,
        "swing_type": swing.swing_type.value, "price": swing.price, "natr_14": swing.natr,
        "move_size_pct": swing.move_size_pct, "is_meaningful": swing.is_meaningful,
        "feature_version": feature_version, "data_version": data_version,
    }
    row["input_checksum"] = _checksum(row)
    return row


def _zone_row(zone: PriceZone, feature_version: str, data_version: str) -> dict[str, object]:
    row = {
        "id": zone.zone_id, "isin": zone.isin, "zone_type": zone.zone_type.value,
        "start_date": zone.start_date, "end_date": zone.end_date, "median_price": zone.median_price,
        "tolerance_pct": zone.tolerance_pct, "breakout_buffer_pct": zone.breakout_buffer_pct,
        "dispersion_pct": zone.dispersion_pct, "source_swing_ids": zone.source_swing_ids,
        "test_count": zone.test_count, "feature_version": feature_version, "data_version": data_version,
        "last_test_date": zone.last_test_date or zone.end_date,
        "confirmation_date": zone.confirmation_date or zone.end_date,
    }
    row["input_checksum"] = _checksum(row)
    return row


def _checksum(row: Mapping[str, object]) -> str:
    return sha256(json.dumps(serialize_value(row), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
