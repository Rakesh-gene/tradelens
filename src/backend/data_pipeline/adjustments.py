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
    maximum_ex_date_jump_pct: Decimal = Decimal("35")


@dataclass(frozen=True, slots=True)
class AdjustmentResult:
    isin: str
    adjustment_version: str
    action_set_checksum: str
    rows_written: int
    earliest_changed_date: date | None


class CorporateActionAdjustmentError(ValueError):
    """A material action cannot be safely converted to one price scale."""


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
        methodology_checksum = _adjustment_methodology_checksum(
            actions, request.cash_dividend_policy, request.source_mode
        )
        effective_version = f"{request.adjustment_version}:{methodology_checksum[:16]}"
        adjusted = self._build_bars(
            raw_bars, actions, request.cash_dividend_policy, request.source_mode,
            effective_version, action_checksum, request.maximum_ex_date_jump_pct,
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
        maximum_ex_date_jump_pct: Decimal = Decimal("35"),
    ) -> list[dict[str, object]]:
        ordered_actions = sorted(actions, key=lambda action: (action.get("ex_date"), str(action.get("source_event_key", ""))))
        factors = [
            (action, *_action_factors(action, raw_bars, cash_dividend_policy))
            for action in ordered_actions
        ] if source_mode == "TRADELENS_REBUILT" else []
        result: list[dict[str, object]] = []
        for raw in sorted(raw_bars, key=lambda row: row["trading_date"]):
            trading_date = raw["trading_date"]
            price_factor = Decimal("1")
            volume_factor = Decimal("1")
            if source_mode == "TRADELENS_REBUILT":
                for action, action_price_factor, action_volume_factor in factors:
                    ex_date = action.get("ex_date")
                    if not isinstance(ex_date, date) or ex_date <= trading_date:
                        continue
                    price_factor *= action_price_factor
                    volume_factor *= action_volume_factor
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
        if source_mode == "TRADELENS_REBUILT":
            _validate_ex_date_continuity(result, factors, maximum_ex_date_jump_pct)
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
        if request.maximum_ex_date_jump_pct <= 0:
            raise ValueError("maximum_ex_date_jump_pct must be positive")


def _action_factors(
    action: Mapping[str, object], raw_bars: list[Mapping[str, object]], cash_dividend_policy: str
) -> tuple[Decimal, Decimal]:
    action_type = str(action.get("action_type") or "OTHER").upper()
    numerator, denominator = _decimal(action.get("numerator")), _decimal(action.get("denominator"))
    manual_price = _decimal(action.get("manual_price_factor"))
    if manual_price is not None:
        manual_volume = _decimal(action.get("manual_volume_factor")) or Decimal("1")
        return manual_price, manual_volume
    if action_type in {"SPLIT", "CONSOLIDATION"}:
        if not numerator or not denominator:
            raise _unresolved(action, "split/consolidation ratio is missing")
        return numerator / denominator, denominator / numerator
    if action_type == "BONUS":
        if not numerator or not denominator:
            raise _unresolved(action, "equity bonus ratio is missing")
        return denominator / (numerator + denominator), (numerator + denominator) / denominator
    if action_type == "BONUS_SPLIT":
        old_face = _decimal(action.get("old_face_value"))
        new_face = _decimal(action.get("new_face_value"))
        if not numerator or not denominator or not old_face or not new_face:
            raise _unresolved(action, "composite bonus/split terms are incomplete")
        bonus_price = denominator / (numerator + denominator)
        split_price = new_face / old_face
        return bonus_price * split_price, ((numerator + denominator) / denominator) * (old_face / new_face)
    if action_type == "RIGHTS":
        issue_price = _decimal(action.get("issue_price"))
        previous_close = _previous_close(raw_bars, action.get("ex_date"))
        if not numerator or not denominator or issue_price is None or previous_close is None:
            raise _unresolved(action, "rights ratio, issue price, or cum-date close is missing")
        entitlement = numerator + denominator
        benefit_per_share = (previous_close - issue_price) * numerator / entitlement
        price_factor = (previous_close - benefit_per_share) / previous_close
        if price_factor <= 0:
            raise _unresolved(action, "rights adjustment factor is not positive")
        return price_factor, entitlement / denominator
    if action_type == "DIVIDEND" and cash_dividend_policy == "adjust_price":
        cash = _decimal(action.get("cash_value"))
        previous_close = _previous_close(raw_bars, action.get("ex_date"))
        if cash is None or previous_close is None or previous_close <= cash:
            raise _unresolved(action, "dividend amount or cum-date close is invalid")
        return (previous_close - cash) / previous_close, Decimal("1")
    if action_type in {
        "DEMERGER", "MERGER", "AMALGAMATION", "CAPITAL_REDUCTION",
        "HIVE_OFF", "SCHEME_OF_ARRANGEMENT", "NON_EQUITY_DISTRIBUTION",
    }:
        raise _unresolved(action, "a reviewed manual adjustment factor is required")
    return Decimal("1"), Decimal("1")


def _previous_close(
    raw_bars: list[Mapping[str, object]], ex_date: object
) -> Decimal | None:
    if not isinstance(ex_date, date):
        return None
    previous = [
        bar for bar in raw_bars
        if isinstance(bar.get("trading_date"), date) and bar["trading_date"] < ex_date
    ]
    if not previous:
        return None
    return _decimal(max(previous, key=lambda row: row["trading_date"]).get("close_price"))


def _unresolved(action: Mapping[str, object], reason: str) -> CorporateActionAdjustmentError:
    return CorporateActionAdjustmentError(
        "Unresolved corporate action "
        f"{action.get('action_type')} on {action.get('ex_date')}: {reason}; "
        f"sourceEventKey={action.get('source_event_key')}"
    )


def _validate_ex_date_continuity(
    adjusted: list[Mapping[str, object]],
    factors: list[tuple[Mapping[str, object], Decimal, Decimal]],
    maximum_jump_pct: Decimal,
) -> None:
    action_dates = sorted({
        action.get("ex_date") for action, price_factor, _ in factors
        if isinstance(action.get("ex_date"), date) and price_factor != Decimal("1")
    })
    for ex_date in action_dates:
        previous = [row for row in adjusted if row.get("trading_date") < ex_date]
        following = [row for row in adjusted if row.get("trading_date") >= ex_date]
        if not previous or not following:
            continue
        cum_bar = max(previous, key=lambda row: row["trading_date"])
        ex_bar = min(following, key=lambda row: row["trading_date"])
        if (ex_bar["trading_date"] - cum_bar["trading_date"]).days > 7:
            continue
        cum_close = _decimal(cum_bar.get("close_price"))
        ex_close = _decimal(ex_bar.get("close_price"))
        if not cum_close or not ex_close:
            continue
        jump_pct = abs(ex_close / cum_close - Decimal("1")) * Decimal("100")
        if jump_pct > maximum_jump_pct:
            raise CorporateActionAdjustmentError(
                f"Adjusted ex-date discontinuity on {ex_date}: {jump_pct.quantize(Decimal('0.01'))}% "
                f"exceeds {maximum_jump_pct}%"
            )


def _action_set_checksum(actions: list[Mapping[str, object]]) -> str:
    canonical = [
        {key: serialize_value(value) for key, value in sorted(action.items())
         if key not in {"imported_at", "updated_at", "import_run_id"}}
        for action in sorted(actions, key=lambda item: str(item.get("source_event_key", "")))
    ]
    encoded = json.dumps(canonical, default=str, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _adjustment_methodology_checksum(
    actions: list[Mapping[str, object]], cash_dividend_policy: str, source_mode: str
) -> str:
    """Version the price scale, not irrelevant corporate-action metadata."""

    effective_actions = []
    if source_mode == "TRADELENS_REBUILT":
        for action in actions:
            action_type = str(action.get("action_type") or "OTHER").upper()
            include = action_type in {
                "SPLIT", "CONSOLIDATION", "BONUS", "BONUS_SPLIT", "RIGHTS",
                "DEMERGER", "MERGER", "AMALGAMATION", "CAPITAL_REDUCTION",
                "HIVE_OFF", "SCHEME_OF_ARRANGEMENT", "NON_EQUITY_DISTRIBUTION",
            }
            include = include or (
                action_type == "DIVIDEND" and cash_dividend_policy == "adjust_price"
            )
            if not include:
                continue
            effective_actions.append({
                "action_type": action_type,
                "ex_date": serialize_value(action.get("ex_date")),
                "numerator": serialize_value(action.get("numerator")),
                "denominator": serialize_value(action.get("denominator")),
                "cash_value": serialize_value(action.get("cash_value")),
                "issue_price": serialize_value(action.get("issue_price")),
                "old_face_value": serialize_value(action.get("old_face_value")),
                "new_face_value": serialize_value(action.get("new_face_value")),
                "manual_price_factor": serialize_value(action.get("manual_price_factor")),
                "manual_volume_factor": serialize_value(action.get("manual_volume_factor")),
            })
    methodology = {
        "cash_dividend_policy": cash_dividend_policy,
        "source_mode": source_mode,
        "effective_actions": sorted(
            effective_actions,
            key=lambda action: json.dumps(action, sort_keys=True, separators=(",", ":")),
        ),
    }
    encoded = json.dumps(methodology, sort_keys=True, separators=(",", ":")).encode()
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
