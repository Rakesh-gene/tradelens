"""Validation and browser contracts for each user's stock watchlist."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Protocol

from pattern_engine.sector_rotation import zone


WATCHLIST_LIMIT = 100
ISIN_PATTERN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


class WatchlistRepository(Protocol):
    def list_items(self, user_id: str) -> list[dict[str, object]]: ...
    def list_recent_events(self, user_id: str, limit: int) -> list[dict[str, object]]: ...
    def add_item(self, user_id: str, isin: str, limit: int) -> bool: ...
    def remove_item(self, user_id: str, isin: str) -> bool: ...
    def security_exists(self, isin: str) -> bool: ...
    def reconcile_quadrants(self, as_of: date | None = None) -> int: ...


class WatchlistService:
    def __init__(self, repository: WatchlistRepository) -> None:
        self._repository = repository

    def list(self, user_id: str) -> dict[str, object]:
        rows = self._repository.list_items(user_id)
        dates = [row.get("data_as_of") for row in rows if row.get("data_as_of")]
        data_as_of = max(dates, default=None)
        items = [self._item(row) for row in rows]
        group_order = ("ACTION_REQUIRED", "NEAR_BREAKOUT", "DEVELOPING", "WEAKENING", "NO_ACTIVE_SETUP")
        groups = [
            {"id": group, "count": sum(item["attentionGroup"] == group for item in items),
             "items": [item for item in items if item["attentionGroup"] == group]}
            for group in group_order
        ]
        return {
            "dataAsOf": data_as_of,
            "generatedAt": datetime.now(timezone.utc),
            "isStale": bool(data_as_of and (date.today() - data_as_of).days > 3),
            "count": len(rows),
            "limit": WATCHLIST_LIMIT,
            "items": items,
            "groups": groups,
            "activity": [self._event(row) for row in self._repository.list_recent_events(user_id, 25)],
        }

    def add(self, user_id: str, isin: object) -> dict[str, object]:
        normalized = self._isin(isin)
        if not self._repository.security_exists(normalized):
            raise LookupError("Security not found")
        added = self._repository.add_item(user_id, normalized, WATCHLIST_LIMIT)
        return {"isin": normalized, "added": added, "count": len(self._repository.list_items(user_id)), "limit": WATCHLIST_LIMIT}

    def remove(self, user_id: str, isin: object) -> dict[str, object]:
        normalized = self._isin(isin)
        removed = self._repository.remove_item(user_id, normalized)
        return {"isin": normalized, "removed": removed, "count": len(self._repository.list_items(user_id)), "limit": WATCHLIST_LIMIT}

    @staticmethod
    def _isin(value: object) -> str:
        isin = str(value or "").strip().upper()
        if not ISIN_PATTERN.fullmatch(isin):
            raise ValueError("A valid ISIN is required")
        return isin

    @staticmethod
    def _item(row: dict[str, object]) -> dict[str, object]:
        last_close = row.get("last_close")
        previous_close = row.get("previous_close")
        daily_change = None
        if last_close is not None and previous_close not in (None, 0):
            daily_change = (float(last_close) - float(previous_close)) / float(previous_close) * 100
        pivot = row.get("pivot_price")
        distance_to_pivot = None
        if last_close is not None and pivot not in (None, 0):
            distance_to_pivot = (float(last_close) - float(pivot)) / float(pivot) * 100
        trend = {
            "aboveEma20": WatchlistService._above(last_close, row.get("ema_20")),
            "aboveSma50": WatchlistService._above(last_close, row.get("sma_50")),
            "aboveSma200": WatchlistService._above(last_close, row.get("sma_200")),
        }
        rs1m = row.get("relative_strength_1m")
        rs3m = row.get("relative_strength_3m")
        momentum = None if rs1m is None or rs3m is None else float(rs1m) - float(rs3m) / 3
        group = WatchlistService._attention_group(row, distance_to_pivot, trend)
        return {
            "security": {
                "isin": row.get("isin"), "symbol": row.get("symbol"),
                "name": row.get("company_name"), "sectorId": row.get("sector_code"),
                "sectorName": row.get("sector_name"),
            },
            "addedAt": row.get("added_at"), "dataAsOf": row.get("data_as_of"),
            "attentionGroup": group,
            "lastClose": last_close, "dailyChangePct": daily_change,
            "distanceTo52WeekHighPct": row.get("distance_to_52_week_high_pct"),
            "relativeStrength1m": row.get("relative_strength_1m"),
            "relativeStrength3m": row.get("relative_strength_3m"),
            "relativeStrength6m": row.get("relative_strength_6m"),
            "relativeStrength12m": row.get("relative_strength_12m"),
            "relativeStrengthPercentile": row.get("relative_strength_percentile"),
            "volumeExpansionRatio": row.get("volume_ratio_5_to_50"),
            "trend": trend,
            "sectorContext": {
                "relativeStrength": row.get("sector_relative_strength"),
                "strengthScore": row.get("sector_strength_score"),
            },
            "rotation": {
                "strength": rs3m, "momentum": momentum,
                "zone": zone(rs3m, momentum),
                "methodologyVersion": "sector-rotation-v1",
            },
            "primarySetup": None if not row.get("pattern_id") else {
                "patternInstanceId": row.get("pattern_id"), "patternClass": row.get("pattern_class"),
                "patternType": row.get("pattern_type"), "variant": row.get("variant"),
                "state": row.get("state"), "setupScore": row.get("setup_score"),
                "pivotPrice": pivot, "supportPrice": row.get("support_price"),
                "invalidationPrice": row.get("invalidation_price"),
                "distanceToPivotPct": distance_to_pivot,
            },
        }

    @staticmethod
    def _above(price: object, average: object) -> bool | None:
        if price is None or average is None:
            return None
        return float(price) >= float(average)

    @staticmethod
    def _attention_group(row: dict[str, object], distance_to_pivot: float | None, trend: dict[str, bool | None]) -> str:
        recent_state = row.get("recent_event_state")
        if not row.get("pattern_id") and recent_state in {"FAILED", "INVALIDATED", "EXPIRED"}:
            return "WEAKENING"
        state = row.get("state")
        if state in {"TRIGGERED", "CONFIRMED"}:
            return "ACTION_REQUIRED"
        if state == "READY" and distance_to_pivot is not None and -3 <= distance_to_pivot <= 0:
            return "NEAR_BREAKOUT"
        rs3m = row.get("relative_strength_3m")
        if trend["aboveSma50"] is False or (rs3m is not None and float(rs3m) < 0):
            return "WEAKENING"
        if state:
            return "DEVELOPING"
        return "NO_ACTIVE_SETUP"

    @staticmethod
    def _event(row: dict[str, object]) -> dict[str, object]:
        if row.get("activity_type") == "QUADRANT":
            return {
                "eventId": row.get("event_id"), "activityType": "QUADRANT",
                "eventType": row.get("event_type"), "effectiveDate": row.get("effective_date"),
                "previousZone": row.get("previous_state"), "newZone": row.get("new_state"),
                "strength": row.get("strength"), "momentum": row.get("momentum"),
                "security": {"isin": row.get("isin"), "symbol": row.get("symbol"), "name": row.get("company_name")},
                "methodologyVersion": row.get("methodology_version"),
            }
        return {
            "eventId": row.get("event_id"), "activityType": "PATTERN",
            "patternInstanceId": row.get("pattern_instance_id"),
            "eventType": row.get("event_type"), "effectiveDate": row.get("effective_date"),
            "previousState": row.get("previous_state"), "newState": row.get("new_state"),
            "security": {"isin": row.get("isin"), "symbol": row.get("symbol"), "name": row.get("company_name")},
            "patternType": row.get("pattern_type"), "variant": row.get("variant"),
        }
