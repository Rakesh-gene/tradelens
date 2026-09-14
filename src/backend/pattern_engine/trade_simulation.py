"""Pure, deterministic case-study trade simulation."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from typing import Mapping, Sequence

ZERO = Decimal("0")
DIRECTIONS = {"BULLISH", "BEARISH"}

@dataclass(frozen=True, slots=True)
class SwingTradePolicy:
    version: str = "swing-trade-v1"
    reference_capital: Decimal = Decimal("100000")
    risk_budget_pct: Decimal = Decimal("1")
    maximum_entry_extension_pct: Decimal = Decimal("5")
    target_r_multiple: Decimal = Decimal("2")
    time_exit_sessions: int = 20
    round_trip_cost_pct: Decimal = ZERO
    fixed_cost: Decimal = ZERO

    def __post_init__(self):
        if self.reference_capital <= 0 or self.risk_budget_pct <= 0:
            raise ValueError("reference capital and risk budget must be positive")
        if self.risk_budget_pct > 100:
            raise ValueError("risk budget cannot exceed reference capital")
        if self.maximum_entry_extension_pct < 0 or self.target_r_multiple <= 0:
            raise ValueError("entry extension cannot be negative and target R must be positive")
        if self.maximum_entry_extension_pct > 100 or self.target_r_multiple > 100:
            raise ValueError("entry extension and target R are outside the supported range")
        if not 1 <= self.time_exit_sessions <= 252 or self.round_trip_cost_pct < 0 or self.fixed_cost < 0:
            raise ValueError("time exit must be positive and costs cannot be negative")
        if self.round_trip_cost_pct > 100:
            raise ValueError("round-trip cost percentage cannot exceed 100")

    @property
    def risk_budget(self): return self.reference_capital * self.risk_budget_pct / 100
    def inputs(self): return asdict(self)

DEFAULT_POLICY = SwingTradePolicy()

def simulate_swing_trade(*, signal_date: date, bars: Sequence[Mapping[str, object]], invalidation_price: object | None, pivot_price: object | None = None, direction: str = "BULLISH", policy: SwingTradePolicy = DEFAULT_POLICY) -> dict[str, object]:
    direction = str(direction).upper()
    if direction not in DIRECTIONS: raise ValueError("direction must be BULLISH or BEARISH")
    signal_date = _date(signal_date)
    ordered = sorted((dict(row) for row in bars if _date(row["trading_date"]) > signal_date), key=lambda row: _date(row["trading_date"]))
    base = {"policy_version": policy.version, "policy_inputs": policy.inputs(), "signal_date": signal_date, "direction": direction, "same_session_policy": "STOP_FIRST", "ambiguous": False}
    if invalidation_price is None: return {**base, "status": "SKIPPED", "exit_reason": "MISSING_INVALIDATION"}
    if not ordered: return {**base, "status": "INCOMPLETE", "exit_reason": "MISSING_NEXT_SESSION", "available_sessions": 0}
    entry_bar, stop = ordered[0], _decimal(invalidation_price)
    entry, entry_date = _price(entry_bar, "open_price"), _date(entry_bar["trading_date"])
    if entry is None: return {**base, "status": "INCOMPLETE", "exit_reason": "MISSING_ENTRY_OPEN", "entry_date": entry_date}
    if pivot_price is not None and _entry_is_extended(entry, _decimal(pivot_price), direction, policy.maximum_entry_extension_pct): return {**base, "status": "SKIPPED", "exit_reason": "ENTRY_GAP_TOO_LARGE", "entry_date": entry_date, "entry_price": entry}
    risk_per_share = entry - stop if direction == "BULLISH" else stop - entry
    if risk_per_share <= ZERO: return {**base, "status": "SKIPPED", "exit_reason": "NON_POSITIVE_RISK", "entry_date": entry_date, "entry_price": entry, "stop_price": stop}
    quantity = int((policy.risk_budget / risk_per_share).to_integral_value(rounding=ROUND_FLOOR))
    if quantity <= 0 or entry * quantity > policy.reference_capital: return {**base, "status": "SKIPPED", "exit_reason": "INSUFFICIENT_CAPITAL", "entry_date": entry_date, "entry_price": entry, "stop_price": stop}
    target = entry + policy.target_r_multiple * risk_per_share if direction == "BULLISH" else entry - policy.target_r_multiple * risk_per_share
    trade = {**base, "status": "COMPLETED", "entry_date": entry_date, "entry_price": entry, "stop_price": stop, "target_price": target, "quantity": quantity, "deployed_capital": entry * quantity, "initial_risk": risk_per_share * quantity}
    observed, highs, lows = ordered[:policy.time_exit_sessions], [], []
    for session, bar in enumerate(observed):
        high, low, opening = (_price(bar, key) for key in ("high_price", "low_price", "open_price"))
        if None in (high, low, opening): return {**trade, "status": "INCOMPLETE", "exit_reason": "INCOMPLETE_BAR", "available_sessions": session}
        highs.append(high); lows.append(low)
        stop_hit = low <= stop if direction == "BULLISH" else high >= stop
        target_hit = high >= target if direction == "BULLISH" else low <= target
        if stop_hit and target_hit: return _finalize(trade, bar, _gap_or_level(opening, stop, direction, True), "AMBIGUOUS_INTRADAY_SEQUENCE", session, policy, highs, lows, True)
        if stop_hit: return _finalize(trade, bar, _gap_or_level(opening, stop, direction, True), "STOP_LOSS", session, policy, highs, lows)
        if target_hit: return _finalize(trade, bar, _gap_or_level(opening, target, direction, False), "TARGET_HIT", session, policy, highs, lows)
    if len(ordered) < policy.time_exit_sessions: return {**trade, "status": "INCOMPLETE", "exit_reason": "INSUFFICIENT_FUTURE_HISTORY", "available_sessions": len(ordered)}
    exit_bar, close = ordered[policy.time_exit_sessions - 1], _price(ordered[policy.time_exit_sessions - 1], "close_price")
    if close is None: return {**trade, "status": "INCOMPLETE", "exit_reason": "INCOMPLETE_BAR", "available_sessions": policy.time_exit_sessions - 1}
    return _finalize(trade, exit_bar, close, "TIME_EXIT", policy.time_exit_sessions, policy, highs, lows)

def _finalize(trade, bar, exit_price, reason, sessions, policy, highs, lows, ambiguous=False):
    sign = Decimal("1") if trade["direction"] == "BULLISH" else Decimal("-1")
    gross = (exit_price - trade["entry_price"]) * trade["quantity"] * sign
    costs = trade["deployed_capital"] * policy.round_trip_cost_pct / 100 + policy.fixed_cost
    net = gross - costs
    mfe = (max(highs) / trade["entry_price"] - 1) * 100 if sign > 0 else (1 - min(lows) / trade["entry_price"]) * 100
    mae = (min(lows) / trade["entry_price"] - 1) * 100 if sign > 0 else (1 - max(highs) / trade["entry_price"]) * 100
    exit_date = _date(bar["trading_date"])
    return {**trade, "exit_date": exit_date, "exit_price": exit_price, "exit_reason": reason, "duration_sessions": sessions, "ambiguous": ambiguous, "target_touch_date": exit_date if reason in {"TARGET_HIT", "AMBIGUOUS_INTRADAY_SEQUENCE"} else None, "stop_touch_date": exit_date if reason in {"STOP_LOSS", "AMBIGUOUS_INTRADAY_SEQUENCE"} else None, "gross_pnl": gross, "costs": costs, "net_pnl": net, "gross_return_pct": gross / trade["deployed_capital"] * 100, "net_return_pct": net / trade["deployed_capital"] * 100, "gross_r_multiple": gross / trade["initial_risk"], "net_r_multiple": net / trade["initial_risk"], "mfe_pct": mfe, "mae_pct": mae}

def _entry_is_extended(entry, pivot, direction, extension_pct):
    return entry > pivot * (1 + extension_pct / 100) if direction == "BULLISH" else entry < pivot * (1 - extension_pct / 100)
def _gap_or_level(opening, level, direction, stop):
    if direction == "BULLISH": return opening if (opening < level if stop else opening > level) else level
    return opening if (opening > level if stop else opening < level) else level
def _price(row, key):
    value = row.get(key); return None if value is None else _decimal(value)
def _date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value): return value if isinstance(value, Decimal) else Decimal(str(value))
