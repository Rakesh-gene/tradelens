"""Deterministic corporate-action adjustment over immutable source bars."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from typing import Mapping

from pattern_engine.models import serialize_value
from repositories.market_data import MarketDataRepository


PRICE_QUANTUM = Decimal("0.01")
VOLUME_QUANTUM = Decimal("1")


@dataclass(frozen=True, slots=True)
class AdjustmentRequest:
    isin: str
    from_date: date
    to_date: date
    adjustment_version: str = "v1"
    as_of: datetime | None = None
    cash_dividend_policy: str = "ignore"
    source_mode: str = "TRADELENS_REBUILT"


@dataclass(frozen=True, slots=True)
class AdjustmentResult:
    isin: str
    adjustment_version: str
    action_set_checksum: str
    rows_written: int
    earliest_changed_date: date | None


class AdjustmentService:
    """Build adjusted bars without mutating raw bars or applying actions twice."""

    def __init__(self, repository: MarketDataRepository) -> None:
        self._repository = repository

    def rebuild(self, request: AdjustmentRequest) -> AdjustmentResult:
        self._validate_request(request)
        raw_bars = self._repository.load_raw_bars(request.isin, request.from_date, request.to_date)
        actions = self._repository.load_corporate_actions(
            request.isin, request.from_date, request.to_date, as_of=request.as_of
        )
        action_checksum = _action_set_checksum(actions)
        methodology = f"{action_checksum}|{request.cash_dividend_policy}|{request.source_mode}"
        methodology_checksum = hashlib.sha256(methodology.encode()).hexdigest()
        effective_version = f"{request.adjustment_version}:{methodology_checksum[:16]}"
        adjusted = self._build_bars(
            raw_bars, actions, request.cash_dividend_policy, request.source_mode,
            effective_version, action_checksum,
        )
        rows_written = self._repository.upsert_adjusted_bars(adjusted)
        earliest_changed = min((row["trading_date"] for row in adjusted), default=None) if actions else None
        return AdjustmentResult(
            request.isin,
            effective_version,
            action_checksum,
            rows_written,
            earliest_changed,
        )

    @staticmethod
    def _build_bars(
        raw_bars: list[Mapping[str, object]],
        actions: list[Mapping[str, object]],
        cash_dividend_policy: str,
        source_mode: str,
        version: str,
        action_checksum: str,
    ) -> list[dict[str, object]]:
        ordered_actions = sorted(actions, key=lambda action: (action.get("ex_date"), str(action.get("source_event_key", ""))))
        result: list[dict[str, object]] = []
        for raw in sorted(raw_bars, key=lambda row: row["trading_date"]):
            trading_date = raw["trading_date"]
            price_factor = Decimal("1")
            if source_mode == "TRADELENS_REBUILT":
                for action in ordered_actions:
                    ex_date = action.get("ex_date")
                    if not isinstance(ex_date, date) or ex_date <= trading_date:
                        continue
                    price_factor *= _action_price_factor(action, raw_bars, cash_dividend_policy)
            volume_factor = Decimal("1") / price_factor
            result.append({
                "isin": raw["isin"],
                "trading_date": trading_date,
                "adjustment_version": version,
                "open_price": _money(_decimal(raw["open_price"]) * price_factor),
                "high_price": _money(_decimal(raw["high_price"]) * price_factor),
                "low_price": _money(_decimal(raw["low_price"]) * price_factor),
                "close_price": _money(_decimal(raw["close_price"]) * price_factor),
                "volume": _whole(Decimal(str(raw["volume"])) * volume_factor),
                "price_adjustment_factor": price_factor,
                "volume_adjustment_factor": volume_factor,
                "adjustment_source": source_mode,
                "source_revision": int(raw.get("raw_revision") or 1),
                "action_set_checksum": action_checksum,
            })
        return result

    @staticmethod
    def _validate_request(request: AdjustmentRequest) -> None:
        if not request.isin.strip():
            raise ValueError("isin is required")
        if request.from_date > request.to_date:
            raise ValueError("from_date cannot be after to_date")
        if not request.adjustment_version.strip():
            raise ValueError("adjustment_version is required")
        if request.cash_dividend_policy not in {"ignore", "adjust_price"}:
            raise ValueError("cash_dividend_policy must be 'ignore' or 'adjust_price'")
        if request.source_mode not in {"TRADELENS_REBUILT", "NSE_SOURCE"}:
            raise ValueError("source_mode must be 'NSE_SOURCE' or 'TRADELENS_REBUILT'")


def _action_price_factor(
    action: Mapping[str, object], raw_bars: list[Mapping[str, object]], cash_dividend_policy: str
) -> Decimal:
    action_type = str(action.get("action_type") or "OTHER").upper()
    numerator, denominator = _decimal(action.get("numerator")), _decimal(action.get("denominator"))
    if action_type in {"SPLIT", "CONSOLIDATION"} and numerator and denominator:
        return numerator / denominator
    if action_type == "BONUS" and numerator and denominator:
        return denominator / (numerator + denominator)
    if action_type == "DIVIDEND" and cash_dividend_policy == "adjust_price":
        cash = _decimal(action.get("cash_value"))
        ex_date = action.get("ex_date")
        ex_close = next((
            _decimal(bar.get("close_price")) for bar in raw_bars
            if bar.get("trading_date") == ex_date
        ), None)
        if cash and ex_close and ex_close > cash:
            return (ex_close - cash) / ex_close
    return Decimal("1")


def _action_set_checksum(actions: list[Mapping[str, object]]) -> str:
    canonical = [
        {key: serialize_value(value) for key, value in sorted(action.items())
         if key not in {"imported_at", "updated_at", "import_run_id"}}
        for action in sorted(actions, key=lambda item: str(item.get("source_event_key", "")))
    ]
    encoded = json.dumps(canonical, default=str, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(PRICE_QUANTUM, rounding=ROUND_HALF_UP)


def _whole(value: Decimal) -> int:
    return int(value.quantize(VOLUME_QUANTUM, rounding=ROUND_HALF_UP))
