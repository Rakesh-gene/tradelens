"""Point-in-time forward stock performance for positional case studies."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

HORIZONS = (("3M", "3 months", 63), ("6M", "6 months", 126), ("1Y", "1 year", 252))


def calculate_positional_performance(*, signal_date: date, bars: Sequence[Mapping[str, object]]) -> dict[str, object]:
    ordered = sorted(
        (dict(row) for row in bars if _date(row["trading_date"]) > _date(signal_date)),
        key=lambda row: _date(row["trading_date"]),
    )
    if not ordered:
        return {"entryDate": None, "entryPrice": None, "performanceToDate": _to_date_missing(), "horizons": {key: _missing(label, sessions) for key, label, sessions in HORIZONS}}
    entry_date = _date(ordered[0]["trading_date"])
    entry_price = _decimal_or_none(ordered[0].get("open_price"))
    if entry_price is None or entry_price <= 0:
        return {"entryDate": entry_date, "entryPrice": None, "performanceToDate": _to_date_missing(), "horizons": {key: _missing(label, sessions) for key, label, sessions in HORIZONS}}
    available = [row for row in ordered if all(_decimal_or_none(row.get(field)) is not None for field in ("high_price", "low_price", "close_price"))]
    latest = available[-1] if available else None
    latest_close = _decimal_or_none(latest.get("close_price")) if latest else None
    horizons = {}
    for key, label, target_sessions in HORIZONS:
        window = ordered[:target_sessions]
        valid = [row for row in window if all(_decimal_or_none(row.get(field)) is not None for field in ("high_price", "low_price", "close_price"))]
        observation = valid[-1] if valid else None
        close = _decimal_or_none(observation.get("close_price")) if observation else None
        highs = [_decimal_or_none(row.get("high_price")) for row in valid]
        lows = [_decimal_or_none(row.get("low_price")) for row in valid]
        complete = len(window) >= target_sessions and len(valid) >= target_sessions
        horizons[key] = {
            "label": label, "targetSessions": target_sessions, "availableSessions": len(window),
            "complete": complete,
            "observationDate": _date(observation["trading_date"]) if complete and observation else None,
            "closePrice": close if complete else None,
            "returnPct": ((close / entry_price) - 1) * 100 if complete and close is not None else None,
            "maxAdvancePct": ((max(highs) / entry_price) - 1) * 100 if complete and highs else None,
            "maxDrawdownPct": ((min(lows) / entry_price) - 1) * 100 if complete and lows else None,
        }
    return {"entryDate": entry_date, "entryPrice": entry_price, "performanceToDate": {"availableSessions": len(ordered), "observationDate": _date(latest["trading_date"]) if latest else None, "closePrice": latest_close, "returnPct": ((latest_close / entry_price) - 1) * 100 if latest_close is not None else None, "maxAdvancePct": ((max(_decimal_or_none(row["high_price"]) for row in available) / entry_price) - 1) * 100 if available else None, "maxDrawdownPct": ((min(_decimal_or_none(row["low_price"]) for row in available) / entry_price) - 1) * 100 if available else None}, "horizons": horizons}


def preferred_forward_return(performance: Mapping[str, object]) -> Decimal | None:
    horizons = performance.get("horizons") or {}
    for key in ("1Y", "6M", "3M"):
        value = (horizons.get(key) or {}).get("returnPct")
        if value is not None:
            return Decimal(str(value))
    return None


def _missing(label, sessions):
    return {"label": label, "targetSessions": sessions, "availableSessions": 0, "complete": False, "observationDate": None, "closePrice": None, "returnPct": None, "maxAdvancePct": None, "maxDrawdownPct": None}
def _to_date_missing(): return {"availableSessions": 0, "observationDate": None, "closePrice": None, "returnPct": None, "maxAdvancePct": None, "maxDrawdownPct": None}
def _date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal_or_none(value): return None if value is None else value if isinstance(value, Decimal) else Decimal(str(value))
