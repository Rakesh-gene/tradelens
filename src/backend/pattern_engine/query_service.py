"""Validation and browser-facing contracts for protected pattern APIs."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from pattern_engine.enums import PatternClass, PatternState
from pattern_engine.models import serialize_value


class PatternQueryRepository(Protocol):
    def list_setups(self, filters, limit, offset): ...
    def setup_facets(self, as_of): ...
    def overview_summary(self, as_of): ...
    def latest_scan_run(self): ...
    def get_pattern(self, pattern_id): ...
    def list_events(self, pattern_id, limit, offset): ...
    def list_chart_bars(self, isin, adjustment_version, as_of, start_date): ...
    def get_security_identity(self, isin, as_of): ...
    def get_latest_feature(self, isin, as_of): ...
    def list_security_patterns(self, isin, as_of, limit=50): ...
    def list_security_events(self, isin, as_of, limit=25): ...


class PatternQueryService:
    def __init__(self, repository: PatternQueryRepository) -> None:
        self._repository = repository

    def overview(self, query):
        as_of = _optional_date(_one(query, "asOf"))
        top = _integer(_one(query, "top"), 10, 1, 25, "top")
        summary = self._repository.overview_summary(as_of)
        data_as_of = summary.get("data_as_of") or as_of
        setup_filters = _default_filters(data_as_of or date.today())
        setup_filters["states"] = ("READY", "TRIGGERED", "CONFIRMED")
        rows = self._repository.list_setups(setup_filters, top, 0)[:top]
        run = self._repository.latest_scan_run()
        regime = _number(summary.get("regime_score"))
        return {
            "dataAsOf": _iso(data_as_of), "generatedAt": datetime.now(timezone.utc),
            "engineVersion": _latest_value(rows, "engine_version"),
            "configurationVersion": _latest_value(rows, "configuration_version"),
            "isStale": bool(data_as_of and (date.today() - data_as_of).days > 3),
            "pipeline": {
                "status": run.get("status") or "NOT_RUN",
                "lastSuccessfulRunAt": run.get("finished_at"),
                "securitiesScanned": run.get("securities_completed", 0),
                "failedSecurities": run.get("securities_failed", 0),
            },
            "market": {
                "regimeScore": regime, "label": _regime_label(regime),
                "benchmark": "NIFTY 500",
                "aboveEma20Pct": _number(summary.get("above_ema20_pct")),
                "aboveSma50Pct": _number(summary.get("above_sma50_pct")),
                "aboveSma200Pct": _number(summary.get("above_sma200_pct")),
                "new52WeekHighs": int(summary.get("new_52_week_highs") or 0),
                "new52WeekLows": 0, "breakouts": int(summary.get("breakouts") or 0),
                "failedBreakouts": int(summary.get("failed_breakouts") or 0),
            },
            "countsByState": {
                state: int(summary.get(f"{state.lower()}_count") or 0)
                for state in ("READY", "TRIGGERED", "CONFIRMED", "FAILED")
            },
            "topSetups": [_setup(row) for row in rows],
        }

    def setups(self, query):
        filters = self._setup_filters(query)
        page_size = _integer(_one(query, "pageSize"), 25, 10, 100, "pageSize")
        offset = _decode_cursor(_one(query, "cursor"))
        rows = self._repository.list_setups(filters, page_size, offset)
        has_more = len(rows) > page_size
        return {
            "dataAsOf": filters["as_of"],
            "items": [_setup(row) for row in rows[:page_size]],
            "nextCursor": _encode_cursor(offset + page_size) if has_more else None,
            "facets": self._repository.setup_facets(filters["as_of"]),
        }

    def pattern(self, pattern_id):
        row = self._repository.get_pattern(pattern_id)
        if row is None:
            raise LookupError("Pattern not found")
        evidence = self._repository.list_security_patterns(row["isin"], row["last_updated_date"])
        return {"pattern": _pattern(row, evidence)}

    def events(self, pattern_id, query):
        if self._repository.get_pattern(pattern_id) is None:
            raise LookupError("Pattern not found")
        page_size = _integer(_one(query, "pageSize"), 50, 10, 100, "pageSize")
        offset = _decode_cursor(_one(query, "cursor"))
        rows = self._repository.list_events(pattern_id, page_size, offset)
        return {
            "items": [_event(row) for row in rows[:page_size]],
            "nextCursor": _encode_cursor(offset + page_size) if len(rows) > page_size else None,
        }

    def chart(self, pattern_id, query):
        """Return a bounded, reproducible price window for a pattern detail view."""
        row = self._repository.get_pattern(pattern_id)
        if row is None:
            raise LookupError("Pattern not found")
        adjustment_version = row.get("adjustment_version")
        window = _chart_window(_one(query, "range"))
        as_of = row.get("last_updated_date")
        start_date = None if window == "max" else as_of - timedelta(days=_CHART_WINDOW_DAYS[window])
        evidence = self._repository.list_security_patterns(row["isin"], row["last_updated_date"])
        bars = [] if not adjustment_version else self._repository.list_chart_bars(
            row["isin"], adjustment_version, as_of, start_date,
        )
        return {
            "dataAsOf": row.get("last_updated_date"),
            "range": window,
            "candles": [{
                "date": bar.get("trading_date"), "open": bar.get("open_price"),
                "high": bar.get("high_price"), "low": bar.get("low_price"),
                "close": bar.get("close_price"), "volume": bar.get("volume"),
            } for bar in bars],
            "levels": {
                "pivot": row.get("pivot_price"), "support": row.get("support_price"),
                "invalidation": row.get("invalidation_price"),
            },
            "markerDate": row.get("trigger_date") or row.get("detected_date"),
            "evidence": [_evidence(item) for item in evidence],
        }

    def fingerprint(self, isin, query):
        as_of = _optional_date(_one(query, "asOf")) or date.today()
        security = self._repository.get_security_identity(isin, as_of)
        if security is None:
            raise LookupError("Security not found")
        feature = self._repository.get_latest_feature(isin, as_of) or {}
        patterns = self._repository.list_security_patterns(isin, as_of)
        events = self._repository.list_security_events(isin, as_of)
        active = [row for row in patterns if row.get("terminal_date") is None]
        primary = next((row for row in active if row.get("pattern_class") in {"BASE", "BREAKOUT", "PULLBACK"}), None)
        supporting = lambda kind: [_setup(row) for row in active if row.get("pattern_class") == kind]
        return {
            "security": _security(security), "dataAsOf": feature.get("trading_date") or as_of,
            "trend": {
                "close": feature.get("close_price"), "ema20": feature.get("ema_20"),
                "sma50": feature.get("sma_50"), "sma200": feature.get("sma_200"),
                "ema20Slope": feature.get("ema_20_slope"), "sma50Slope": feature.get("sma_50_slope"),
            },
            "primarySetup": _pattern(primary) if primary else None,
            "compression": supporting("COMPRESSION"), "momentum": supporting("MOMENTUM"),
            "relativeStrength": {key: feature.get(value) for key, value in {
                "oneMonth": "relative_strength_1m", "threeMonth": "relative_strength_3m",
                "sixMonth": "relative_strength_6m", "twelveMonth": "relative_strength_12m",
                "percentile": "relative_strength_percentile",
            }.items()},
            "volume": {
                "ratio20": feature.get("volume_ratio_20"),
                "contractionRatio": feature.get("volume_contraction_ratio"),
                "median20": feature.get("median_volume_20"),
                "medianTradedValue20": feature.get("median_traded_value_20"),
            },
            "location": {
                "distanceTo52WeekHighPct": feature.get("distance_to_52_week_high_pct"),
                "distanceToEma20Pct": feature.get("distance_to_ema_20_pct"),
                "distanceToSma50Pct": feature.get("distance_to_sma_50_pct"),
                "distanceToSma200Pct": feature.get("distance_to_sma_200_pct"),
                "pivotPrice": primary.get("pivot_price") if primary else None,
                "supportPrice": primary.get("support_price") if primary else None,
                "invalidationPrice": primary.get("invalidation_price") if primary else None,
            },
            "context": (primary.get("measurements") or {}).get("scoring", {}).get("context_inputs", {}) if primary else {},
            "scores": {key: primary.get(value) if primary else None for key, value in {
                "quality": "quality_score", "maturity": "maturity_score",
                "context": "context_score", "setup": "setup_score",
            }.items()},
            "activePatterns": [_setup(row) for row in active],
            "recentEvents": [_event(row) for row in events],
            "lineage": {
                "engineVersion": primary.get("engine_version") if primary else None,
                "configurationVersion": primary.get("configuration_version") if primary else None,
                "featureVersion": primary.get("feature_version") if primary else feature.get("feature_version"),
                "adjustmentVersion": primary.get("adjustment_version") if primary else None,
            },
        }

    def _setup_filters(self, query):
        as_of = _optional_date(_one(query, "asOf")) or date.today()
        filters = _default_filters(as_of)
        pattern_class = _one(query, "patternClass")
        if pattern_class:
            try: filters["pattern_class"] = PatternClass(pattern_class).value
            except ValueError as exc: raise ValueError("Invalid patternClass") from exc
        states = []
        for value in query.get("state", []): states.extend(item for item in value.split(",") if item)
        try: filters["states"] = tuple(PatternState(value).value for value in states)
        except ValueError as exc: raise ValueError("Invalid state") from exc
        filters.update({"pattern_type": _one(query, "patternType"), "variant": _one(query, "variant"), "sector": _one(query, "sector")})
        for client, key in (("minSetupScore", "min_setup_score"), ("maxSetupScore", "max_setup_score"), ("minRs6m", "min_rs6m"), ("minLiquidityScore", "min_liquidity_score")):
            filters[key] = _score(_one(query, client), client)
        sort = _one(query, "sort") or "setupScore"
        if sort not in {"setupScore", "qualityScore", "maturityScore", "detectedDate", "distanceToPivotPct"}: raise ValueError("Invalid sort")
        direction = _one(query, "direction") or "desc"
        if direction not in {"asc", "desc"}: raise ValueError("Invalid direction")
        filters.update({"sort": sort, "direction": direction})
        return filters


def _default_filters(as_of):
    return {"as_of": as_of, "pattern_class": None, "pattern_type": None, "variant": None, "states": (), "sector": None, "min_setup_score": None, "max_setup_score": None, "min_rs6m": None, "min_liquidity_score": None, "sort": "setupScore", "direction": "desc"}


_CHART_WINDOW_DAYS = {"3m": 92, "6m": 184, "1y": 365, "5y": 1826}


def _chart_window(value):
    window = value or "6m"
    if window not in {*_CHART_WINDOW_DAYS, "max"}:
        raise ValueError("range must be one of 3m, 6m, 1y, 5y, or max")
    return window


def _setup(row):
    measurements = row.get("measurements") or {}
    scoring = measurements.get("scoring", {}) if isinstance(measurements, Mapping) else {}
    context_inputs = scoring.get("context_inputs", {}) if isinstance(scoring, Mapping) else {}
    return {"patternInstanceId": row.get("id") or row.get("pattern_instance_id"), "security": _security(row), "patternClass": row.get("pattern_class"), "patternType": row.get("pattern_type"), "variant": row.get("variant"), "state": row.get("state"), "detectedDate": row.get("detected_date"), "lastUpdatedDate": row.get("last_updated_date"), "qualityScore": row.get("quality_score"), "maturityScore": row.get("maturity_score"), "maturityBand": scoring.get("maturity_band"), "contextScore": row.get("context_score"), "setupScore": row.get("setup_score"), "pivotPrice": row.get("pivot_price"), "lastClose": row.get("last_close"), "distanceToPivotPct": row.get("distance_to_pivot_pct"), "relativeStrength6m": row.get("relative_strength_6m"), "liquidityScore": context_inputs.get("liquidity"), "supportingPatterns": row.get("supporting_patterns") or [], "evidenceCount": row.get("evidence_count", 1)}


def _pattern(row, evidence=()):
    measurements = row.get("measurements") or {}
    scoring = measurements.get("scoring", {}) if isinstance(measurements, Mapping) else {}
    all_evidence = list(evidence)
    if not any(str(item.get("id")) == str(row.get("id")) for item in all_evidence): all_evidence.append(row)
    return {**_setup(row), "startDate": row.get("start_date"), "triggerDate": row.get("trigger_date"), "confirmationDate": row.get("confirmation_date"), "terminalDate": row.get("terminal_date"), "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price"), "sourcePatternId": row.get("source_pattern_id"), "measurements": measurements, "scoreComponents": {"context": scoring.get("context_contributions", {}), "setup": scoring.get("setup_contributions", {})}, "allEvidence": [_evidence(item) for item in all_evidence], "lineage": {"engineVersion": row.get("engine_version"), "configurationVersion": row.get("configuration_version"), "featureVersion": row.get("feature_version"), "adjustmentVersion": row.get("adjustment_version")}}


def _evidence(row):
    return {**_setup(row), "triggerDate": row.get("trigger_date"), "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price")}


def _event(row):
    return {"eventId": row.get("id"), "patternInstanceId": row.get("pattern_instance_id"), "eventType": row.get("event_type"), "effectiveDate": row.get("effective_date"), "recordedAt": row.get("recorded_at"), "previousState": row.get("previous_state"), "newState": row.get("new_state"), "changes": {"previous": row.get("previous_values") or {}, "new": row.get("new_values") or {}}}


def _security(row):
    return {"isin": row.get("isin"), "symbol": row.get("symbol"), "name": row.get("company_name"), "sectorId": row.get("sector_code"), "sectorName": row.get("sector_name")}


def _one(query, name): return query.get(name, [None])[-1]
def _optional_date(value):
    if not value: return None
    try: return date.fromisoformat(value)
    except ValueError as exc: raise ValueError(f"{value} is not a valid ISO date") from exc
def _integer(value, default, minimum, maximum, name):
    try: result = default if value in (None, "") else int(value)
    except ValueError as exc: raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= result <= maximum: raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result
def _score(value, name):
    if value in (None, ""): return None
    try: result = Decimal(value)
    except Exception as exc: raise ValueError(f"{name} must be a number") from exc
    if not 0 <= result <= 100: raise ValueError(f"{name} must be between 0 and 100")
    return result
def _encode_cursor(offset): return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode().rstrip("=")
def _decode_cursor(value):
    if not value: return 0
    try:
        payload = json.loads(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
        offset = int(payload["offset"])
        if offset < 0: raise ValueError
        return offset
    except Exception as exc: raise ValueError("Invalid cursor") from exc
def _iso(value): return value.isoformat() if isinstance(value, date) else value
def _number(value): return None if value is None else value
def _latest_value(rows, key): return rows[0].get(key) if rows else None
def _regime_label(value):
    if value is None: return "UNAVAILABLE"
    value = Decimal(str(value))
    return "CONSTRUCTIVE" if value >= 70 else "MIXED" if value >= 40 else "DEFENSIVE"


def browser_payload(value):
    if isinstance(value, Decimal): return float(value)
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, Mapping): return {str(key): browser_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [browser_payload(item) for item in value]
    return serialize_value(value)
