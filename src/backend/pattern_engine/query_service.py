"""Validation and browser-facing contracts for protected pattern APIs."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from pattern_engine.enums import PatternClass, PatternState, SUPPORTED_PATTERN_TYPES
from pattern_engine.decision_intelligence import METHODOLOGY_VERSION as DECISION_VERSION, build_decision
from pattern_engine.models import serialize_value


class PatternQueryRepository(Protocol):
    def sector_rotation_rows(self, as_of): ...
    def sector_rotation_history_rows(self, as_of, sessions=5): ...
    def sector_strength_stocks(self, as_of, sector, limit, offset): ...
    def search_securities(self, query, limit): ...
    def list_setups(self, filters, limit, offset): ...
    def setup_facets(self, as_of, equities_only=False): ...
    def overview_summary(self, as_of): ...
    def index_overview_rows(self, as_of, sessions): ...
    def latest_scan_run(self): ...
    def get_pattern(self, pattern_id): ...
    def list_events(self, pattern_id, limit, offset): ...
    def list_chart_bars(self, isin, adjustment_version, as_of, start_date): ...
    def get_latest_adjustment_version(self, isin, as_of): ...
    def list_chart_actions(self, isin, as_of, start_date): ...
    def get_security_identity(self, isin, as_of): ...
    def get_latest_feature(self, isin, as_of): ...
    def list_security_patterns(self, isin, as_of, limit=50): ...
    def list_chart_patterns(self, isin, as_of, start_date, limit=500): ...
    def list_security_events(self, isin, as_of, limit=25): ...


class PatternQueryService:
    def __init__(self, repository: PatternQueryRepository) -> None:
        self._repository = repository

    def sector_rotation(self, query):
        from pattern_engine.sector_rotation import rotation_payload
        as_of = _optional_date(_one(query, "asOf")) or date.today()
        return rotation_payload(
            self._repository.sector_rotation_rows(as_of),
            self._repository.sector_rotation_history_rows(as_of, sessions=5),
        )

    def sector_stocks(self, query):
        as_of = _optional_date(_one(query, "asOf"))
        sector = _one(query, "sector")
        if not as_of or not sector or len(sector) > 100:
            raise ValueError("sector and asOf are required")
        limit = _integer(_one(query, "pageSize"), 25, 1, 100, "pageSize")
        offset = _decode_cursor(_one(query, "cursor"))
        rows = self._repository.sector_strength_stocks(as_of, sector, limit, offset)
        return {"dataAsOf": as_of, "generatedAt": datetime.now(timezone.utc),
                "engineVersion": "sector-rotation-v1", "configurationVersion": "sector-rotation-v1",
                "isStale": (date.today() - as_of).days > 3,
                "items": [{"security": _security(row), "rank": row["rank"] if row.get("relative_strength_3m") is not None else None,
                           "rs3m": row.get("relative_strength_3m"), "rs1m": row.get("relative_strength_1m"),
                           "rs6m": row.get("relative_strength_6m"), "rs12m": row.get("relative_strength_12m"),
                           "featureVersion": row.get("feature_version"), "adjustmentVersion": row.get("data_version")}
                          for row in rows[:limit]],
                "nextCursor": _encode_cursor(offset + limit) if len(rows) > limit else None}

    def overview(self, query):
        as_of = _optional_date(_one(query, "asOf"))
        top = _integer(_one(query, "top"), 10, 1, 25, "top")
        summary = self._repository.overview_summary(as_of)
        data_as_of = summary.get("data_as_of") or as_of
        setup_filters = _default_filters(data_as_of or date.today())
        setup_filters["states"] = ("READY", "TRIGGERED", "CONFIRMED")
        setup_filters["equities_only"] = True
        rows = self._repository.list_setups(setup_filters, top, 0)[:top]
        run = self._repository.latest_scan_run()
        regime = _number(summary.get("regime_score"))
        indices = _index_overview(self._repository.index_overview_rows(data_as_of, 63))
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
                "indices": indices,
            },
            "countsByState": {
                state: int(summary.get(f"{state.lower()}_count") or 0)
                for state in ("READY", "TRIGGERED", "CONFIRMED", "FAILED")
            },
            "topSetups": [_setup(row) for row in rows],
        }

    def search_securities(self, query):
        text = (_one(query, "q") or "").strip()
        if len(text) < 2:
            raise ValueError("Search requires at least two characters")
        limit = _integer(_one(query, "limit"), 8, 1, 20, "limit")
        return {
            "items": [
                _security(row)
                for row in self._repository.search_securities(text, limit)
            ]
        }

    def setups(self, query):
        filters = self._setup_filters(query)
        filters["equities_only"] = True
        page_size = _integer(_one(query, "pageSize"), 25, 10, 100, "pageSize")
        offset = _decode_cursor(_one(query, "cursor"))
        rows = self._repository.list_setups(filters, page_size, offset)
        has_more = len(rows) > page_size
        total_count = int(rows[0].get("total_count") or 0) if rows else 0
        facets = _complete_pattern_type_facets(self._repository.setup_facets(filters["as_of"], equities_only=True))
        return {
            "dataAsOf": filters["as_of"],
            "items": [_setup(row) for row in rows[:page_size]],
            "totalCount": total_count,
            "remainingCount": max(0, total_count - offset - page_size),
            "nextCursor": _encode_cursor(offset + page_size) if has_more else None,
            "facets": facets,
            "ranking": {
                "methodologyVersion": "best-fit-v1",
                "peerGroup": "lifecycleState",
                "weights": {"setup": 75, "context": 10, "liquidity": 15},
                "activeStates": list(_ACTIVE_OPPORTUNITY_STATES),
                "excludedStates": ["FAILED", "INVALIDATED", "EXPIRED"],
                "historicalOutcomesIncluded": False,
                "decisionMethodologyVersion": DECISION_VERSION,
            },
        }

    def pattern_scanner(self, query):
        filters = self._setup_filters(query, default_pattern_group=None)
        page_size = _integer(_one(query, 'pageSize'), 25, 10, 100, 'pageSize')
        offset = _decode_cursor(_one(query, 'cursor'))
        rows = self._repository.list_setups(filters, page_size, offset)
        has_more = len(rows) > page_size
        total_count = int(rows[0].get('total_count') or 0) if rows else 0
        return {
            'dataAsOf': filters['as_of'], 'generatedAt': datetime.now(timezone.utc),
            'engineVersion': _latest_value(rows, 'engine_version'),
            'configurationVersion': _latest_value(rows, 'configuration_version'),
            'isStale': (date.today() - filters['as_of']).days > 3,
            'timeframe': filters['timeframe'], 'items': [_setup(row) for row in rows[:page_size]],
            'totalCount': total_count,
            'nextCursor': _encode_cursor(offset + page_size) if has_more else None,
            'facets': _complete_pattern_type_facets(self._repository.setup_facets(filters['as_of'])),
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
        start_date = as_of - timedelta(days=_CHART_WINDOW_DAYS[window])
        evidence = self._repository.list_chart_patterns(row["isin"], as_of, start_date)
        if not any(str(item.get("id")) == str(row.get("id")) for item in evidence):
            evidence = [row, *evidence]
        actions = self._repository.list_chart_actions(row["isin"], as_of, start_date)
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
                "ema20": bar.get("ema_20"), "sma50": bar.get("sma_50"), "sma200": bar.get("sma_200"),
            } for bar in bars],
            "levels": {
                "pivot": row.get("pivot_price"), "support": row.get("support_price"),
                "invalidation": row.get("invalidation_price"),
            },
            "markerDate": row.get("trigger_date") or row.get("detected_date"),
            "patternWindow": {"startDate": row.get("start_date"), "endDate": row.get("last_updated_date")},
            "evidence": [_evidence(item) for item in evidence],
            "corporateActions": [_chart_action(item) for item in actions],
        }

    def security_chart(self, isin, query):
        """Return adjusted bars and current evidence without requiring a setup."""
        as_of = _optional_date(_one(query, "asOf")) or date.today()
        security = self._repository.get_security_identity(isin, as_of)
        if security is None:
            raise LookupError("Security not found")
        window = _chart_window(_one(query, "range"))
        start_date = as_of - timedelta(days=_CHART_WINDOW_DAYS[window])
        evidence = self._repository.list_chart_patterns(isin, as_of, start_date)
        actions = self._repository.list_chart_actions(isin, as_of, start_date)
        adjustment_version = self._repository.get_latest_adjustment_version(isin, as_of)
        bars = [] if not adjustment_version else self._repository.list_chart_bars(
            isin, adjustment_version, as_of, start_date,
        )
        primary = next((row for row in evidence if row.get("terminal_date") is None and row.get("pattern_class") in {"BASE", "BREAKOUT", "PULLBACK"}), None)
        return {
            "security": _security(security), "dataAsOf": bars[-1].get("trading_date") if bars else as_of,
            "range": window, "adjusted": True, "adjustmentVersion": adjustment_version,
            "candles": [{
                "date": bar.get("trading_date"), "open": bar.get("open_price"),
                "high": bar.get("high_price"), "low": bar.get("low_price"),
                "close": bar.get("close_price"), "volume": bar.get("volume"),
                "ema20": bar.get("ema_20"), "sma50": bar.get("sma_50"), "sma200": bar.get("sma_200"),
            } for bar in bars],
            "levels": {
                "pivot": primary.get("pivot_price") if primary else None,
                "support": primary.get("support_price") if primary else None,
                "invalidation": primary.get("invalidation_price") if primary else None,
            },
            "evidence": [_evidence(item) for item in evidence],
            "corporateActions": [_chart_action(item) for item in actions],
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
        score_source = next((
            row for row in active
            if row.get("pattern_class") != "FAILURE" and row.get("setup_score") is not None
        ), None)
        supporting = lambda kind: [_setup(row) for row in active if row.get("pattern_class") == kind]
        return {
            "security": _security(security), "dataAsOf": feature.get("trading_date") or as_of,
            "classification": {
                "status": security.get("classification_status") or "MISSING",
                "macroSector": {"code": security.get("macro_sector_code"), "name": security.get("macro_sector_name")},
                "sector": {"code": security.get("sector_code"), "name": security.get("sector_name")},
                "industry": {"code": security.get("industry_code"), "name": security.get("industry_name")},
                "basicIndustry": {"code": security.get("basic_industry_code"), "name": security.get("basic_industry_name")},
                "source": "NSE", "asOf": as_of,
            },
            "sectorStrength": {key: security.get(value) for key, value in {
                "score": "sector_strength_score", "coveragePct": "coverage_pct",
                "aboveEma20Pct": "above_ema20_pct", "aboveSma50Pct": "above_sma50_pct",
                "aboveSma200Pct": "above_sma200_pct", "medianRelativeStrength": "median_relative_strength",
                "asOf": "sector_snapshot_date",
            }.items()},
            "trend": {
                "close": feature.get("close_price"), "ema20": feature.get("ema_20"),
                "sma50": feature.get("sma_50"), "sma200": feature.get("sma_200"),
                "ema20Slope": feature.get("ema_20_slope"), "sma50Slope": feature.get("sma_50_slope"),
            },
            "primarySetup": _pattern(primary) if primary else None,
            "scoreSource": _setup(score_source) if score_source else None,
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
            "context": (score_source.get("measurements") or {}).get("scoring", {}).get("context_inputs", {}) if score_source else {},
            "scores": {key: score_source.get(value) if score_source else None for key, value in {
                "quality": "quality_score", "maturity": "maturity_score",
                "context": "context_score", "setup": "setup_score",
            }.items()},
            "activePatterns": [_setup(row) for row in active],
            "recentEvents": [_event(row) for row in events],
            "lineage": {
                "engineVersion": score_source.get("engine_version") if score_source else None,
                "configurationVersion": score_source.get("configuration_version") if score_source else None,
                "featureVersion": score_source.get("feature_version") if score_source else feature.get("feature_version"),
                "adjustmentVersion": score_source.get("adjustment_version") if score_source else None,
            },
        }

    def _setup_filters(self, query, default_pattern_group="SETUP"):
        as_of = _optional_date(_one(query, "asOf")) or date.today()
        filters = _default_filters(as_of)
        pattern_class = _one(query, "patternClass")
        if pattern_class:
            try: filters["pattern_class"] = PatternClass(pattern_class).value
            except ValueError as exc: raise ValueError("Invalid patternClass") from exc
        states = []
        for value in query.get("state", []): states.extend(item for item in value.split(",") if item)
        try:
            if states: filters["states"] = tuple(PatternState(value).value for value in states)
        except ValueError as exc: raise ValueError("Invalid state") from exc
        filters.update({"pattern_type": _one(query, "patternType"), "variant": _one(query, "variant"), "sector": _one(query, "sector")})
        for client, key in (("minSetupScore", "min_setup_score"), ("maxSetupScore", "max_setup_score"), ("minRs6m", "min_rs6m"), ("minLiquidityScore", "min_liquidity_score")):
            filters[key] = _score(_one(query, client), client)
        sort = _one(query, "sort") or "setupScore"
        if sort not in {"bestFit", "setupScore", "qualityScore", "maturityScore", "detectedDate", "distanceToPivotPct"}: raise ValueError("Invalid sort")
        direction = _one(query, "direction") or "desc"
        if direction not in {"asc", "desc"}: raise ValueError("Invalid direction")
        filters.update({"sort": sort, "direction": direction})
        timeframe = _one(query, 'timeframe') or '1D'
        if timeframe not in {'1D', '1W', '1M'}:
            raise ValueError('Invalid timeframe')
        pattern_group = (_one(query, 'patternGroup') or '').strip() or default_pattern_group
        if pattern_group and pattern_group not in {'SETUP', 'REVERSAL', 'CONTINUATION', 'HARMONIC'}:
            raise ValueError('Invalid patternGroup')
        pattern_direction = (_one(query, 'patternDirection') or '').strip() or None
        if pattern_direction and pattern_direction not in {'BULLISH', 'BEARISH', 'NEUTRAL'}:
            raise ValueError('Invalid patternDirection')
        filters.update({'timeframe': timeframe, 'pattern_group': pattern_group,
                        'pattern_direction': pattern_direction})
        return filters


_ACTIVE_OPPORTUNITY_STATES = (
    "DETECTED", "FORMING", "MATURE", "READY", "TRIGGERED", "CONFIRMED",
)


def _default_filters(as_of):
    return {"as_of": as_of, "pattern_class": None, "pattern_type": None, "variant": None, "states": _ACTIVE_OPPORTUNITY_STATES, "sector": None, "min_setup_score": None, "max_setup_score": None, "min_rs6m": None, "min_liquidity_score": None, "sort": "bestFit", "direction": "desc", "timeframe": "1D", "pattern_group": "SETUP", "pattern_direction": None}


def _index_overview(rows):
    grouped = {"NIFTY 50": [], "NIFTY 500": []}
    for row in rows:
        if row.get("index_code") in grouped:
            grouped[row["index_code"]].append(row)
    result = []
    for code in ("NIFTY 50", "NIFTY 500"):
        points = sorted(grouped[code], key=lambda row: row["trading_date"])
        first = _number(points[0].get("close_price")) if points else None
        latest = _number(points[-1].get("close_price")) if points else None
        change = None if first in (None, 0) or latest is None else (latest - first) / first * 100
        result.append({
            "code": code, "name": code, "dataAsOf": points[-1]["trading_date"] if points else None,
            "lastClose": latest, "periodChangePct": change,
            "series": [{"date": row["trading_date"], "close": _number(row.get("close_price"))} for row in points],
        })
    return result


_CHART_WINDOW_DAYS = {"3m": 92, "6m": 184, "1y": 365, "5y": 1826, "10y": 3653}


def _chart_window(value):
    window = value or "6m"
    if window == "max":  # compatibility for previously bookmarked chart URLs
        return "10y"
    if window not in _CHART_WINDOW_DAYS:
        raise ValueError("range must be one of 3m, 6m, 1y, 5y, or 10y")
    return window


def _setup(row):
    measurements = row.get("measurements") or {}
    scoring = measurements.get("scoring", {}) if isinstance(measurements, Mapping) else {}
    context_inputs = scoring.get("context_inputs", {}) if isinstance(scoring, Mapping) else {}
    result = {"patternInstanceId": row.get("id") or row.get("pattern_instance_id"), "security": _security(row), "patternClass": row.get("pattern_class"), "patternType": row.get("pattern_type"), "variant": row.get("variant"), "state": row.get("state"), "detectedDate": row.get("detected_date"), "lastUpdatedDate": row.get("last_updated_date"), "qualityScore": row.get("quality_score"), "maturityScore": row.get("maturity_score"), "maturityBand": scoring.get("maturity_band"), "contextScore": row.get("context_score"), "setupScore": row.get("setup_score"), "pivotPrice": row.get("pivot_price"), "lastClose": row.get("last_close"), "distanceToPivotPct": row.get("distance_to_pivot_pct"), "relativeStrength6m": row.get("relative_strength_6m"), "liquidityScore": context_inputs.get("liquidity"), "supportingPatterns": row.get("supporting_patterns") or [], "evidenceCount": row.get("evidence_count", 1)}
    result["bestFit"] = _best_fit(row, result)
    result["decision"] = build_decision(row, result)
    result.update({
        'patternGroup': row.get('pattern_group') or 'SETUP',
        'timeframe': row.get('timeframe') or '1D',
        'direction': row.get('direction') or 'NEUTRAL',
        'intervalComplete': row.get('interval_complete', True),
    })
    return result


def _best_fit(row, setup):
    if setup.get("state") not in _ACTIVE_OPPORTUNITY_STATES:
        return {
            "score": None, "rankWithinState": None, "percentileWithinState": None,
            "stateCandidateCount": None, "tier": "EXCLUDED",
            "evidenceCompletenessPct": None, "strengths": [],
            "cautions": ["Terminal lifecycle states are not opportunity-ranked"],
            "historicalProbability": None, "historicalSampleSize": 0,
        }
    percentile = _number(row.get("best_fit_percentile"))
    score = _number(row.get("best_fit_score"))
    strengths = []
    cautions = []
    if _at_least(setup.get("qualityScore"), 80): strengths.append("High pattern quality")
    if _at_least(setup.get("maturityScore"), 80): strengths.append("Advanced lifecycle maturity")
    if _at_least(setup.get("liquidityScore"), 75): strengths.append("Passes liquidity profile")
    if _at_least(row.get("relative_strength_percentile"), 80): strengths.append("Leading relative strength")
    if int(setup.get("evidenceCount") or 0) >= 3: strengths.append("Multiple confirming signals")
    if setup.get("liquidityScore") is None: cautions.append("Liquidity evidence unavailable")
    elif not _at_least(setup.get("liquidityScore"), 75): cautions.append("Below preferred liquidity profile")
    if setup.get("contextScore") is None or not _at_least(setup.get("contextScore"), 40):
        cautions.append("Market or sector context is weak or incomplete")
    distance = setup.get("distanceToPivotPct")
    if distance is not None and Decimal(str(distance)) > Decimal("8"):
        cautions.append("Price is extended above the pivot")
    values = (
        setup.get("setupScore"), setup.get("qualityScore"), setup.get("maturityScore"),
        setup.get("contextScore"), setup.get("liquidityScore"),
        row.get("relative_strength_percentile"), setup.get("distanceToPivotPct"),
    )
    completeness = Decimal(sum(value is not None for value in values)) / len(values) * 100
    return {
        "score": score,
        "rankWithinState": row.get("best_fit_rank"),
        "percentileWithinState": percentile,
        "stateCandidateCount": row.get("state_candidate_count"),
        "tier": _fit_tier(percentile),
        "evidenceCompletenessPct": completeness,
        "strengths": strengths[:3],
        "cautions": cautions[:3],
        "historicalProbability": None,
        "historicalSampleSize": 0,
    }


def _at_least(value, threshold):
    return value is not None and Decimal(str(value)) >= Decimal(str(threshold))


def _fit_tier(percentile):
    if percentile is None: return "UNRANKED"
    value = Decimal(str(percentile))
    if value >= 95: return "LEADING"
    if value >= 80: return "STRONG"
    if value >= 50: return "QUALIFIED"
    return "DEVELOPING"


def _pattern(row, evidence=()):
    measurements = row.get("measurements") or {}
    scoring = measurements.get("scoring", {}) if isinstance(measurements, Mapping) else {}
    all_evidence = list(evidence)
    if not any(str(item.get("id")) == str(row.get("id")) for item in all_evidence): all_evidence.append(row)
    return {**_setup(row), "startDate": row.get("start_date"), "triggerDate": row.get("trigger_date"), "confirmationDate": row.get("confirmation_date"), "terminalDate": row.get("terminal_date"), "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price"), "sourcePatternId": row.get("source_pattern_id"), "measurements": measurements, "scoreComponents": {"context": scoring.get("context_contributions", {}), "setup": scoring.get("setup_contributions", {})}, "allEvidence": [_evidence(item) for item in all_evidence], "lineage": {"engineVersion": row.get("engine_version"), "configurationVersion": row.get("configuration_version"), "featureVersion": row.get("feature_version"), "adjustmentVersion": row.get("adjustment_version")}}


def _evidence(row):
    return {
        **_setup(row),
        "triggerDate": row.get("trigger_date"),
        "supportPrice": row.get("support_price"),
        "invalidationPrice": row.get("invalidation_price"),
        "measurements": row.get("measurements") or {},
    }


def _event(row):
    return {"eventId": row.get("id"), "patternInstanceId": row.get("pattern_instance_id"), "eventType": row.get("event_type"), "effectiveDate": row.get("effective_date"), "recordedAt": row.get("recorded_at"), "previousState": row.get("previous_state"), "newState": row.get("new_state"), "changes": {"previous": row.get("previous_values") or {}, "new": row.get("new_values") or {}}}


def _chart_action(row):
    return {"sourceEventKey": row.get("source_event_key"), "actionType": row.get("action_type"), "exDate": row.get("ex_date"), "description": row.get("raw_description")}


def _security(row):
    return {"isin": row.get("isin"), "symbol": row.get("symbol"), "name": row.get("company_name"), "sectorId": row.get("sector_code"), "sectorName": row.get("sector_name"), "basicIndustryName": row.get("basic_industry_name")}


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


def _complete_pattern_type_facets(facets):
    observed_types = {
        str(item.get("value")): int(item.get("count") or 0)
        for item in facets.get("patternTypes", []) if item.get("value")
    }
    return {
        **facets,
        "patternTypes": [
            {"value": pattern_type, "count": observed_types.get(pattern_type, 0)}
            for pattern_type in SUPPORTED_PATTERN_TYPES
        ],
    }
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
