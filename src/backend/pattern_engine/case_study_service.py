"""Validation and browser-facing contracts for historical case studies."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import base64
import json
from uuid import UUID
from pattern_engine.positional_performance import calculate_positional_performance
from pattern_engine.enums import SETUP_PATTERN_TYPES

ALLOWED_FILTERS = {"q", "isin", "sector", "patternClass", "patternType", "variant", "timeframe", "direction", "fromDate", "toDate", "exitReason", "outcome", "marketRegime", "minSetupScore", "sort", "directionOrder", "cursor", "pageSize"}
SORTS = {"detectionDate", "entryDate", "netPnl", "netReturnPct", "netRMultiple", "setupScore"}

class CaseStudyService:
    def __init__(self, repository): self._repository = repository

    def catalog(self, query):
        unknown = set(query) - ALLOWED_FILTERS
        if unknown: raise ValueError(f"Unknown case-study filter: {sorted(unknown)[0]}")
        filters = {name: _one(query, name) for name in ALLOWED_FILTERS if _one(query, name) not in (None, "")}
        filters["sort"] = filters.get("sort", "detectionDate")
        filters["directionOrder"] = filters.get("directionOrder", "desc")
        if filters["sort"] not in SORTS: raise ValueError("sort is not supported")
        if filters["directionOrder"] not in {"asc", "desc"}: raise ValueError("directionOrder must be asc or desc")
        for name in ("fromDate", "toDate"):
            if name in filters:
                try: filters[name] = date.fromisoformat(filters[name])
                except ValueError as exc: raise ValueError(f"{name} must be an ISO date") from exc
        if filters.get("fromDate") and filters.get("toDate") and filters["fromDate"] > filters["toDate"]: raise ValueError("fromDate cannot be after toDate")
        if "minSetupScore" in filters:
            filters["minSetupScore"] = float(filters["minSetupScore"])
            if not 0 <= filters["minSetupScore"] <= 100: raise ValueError("minSetupScore must be between 0 and 100")
        page_size = _number(filters.get("pageSize"), 25, 1, 100)
        offset = _decode_cursor(filters.get("cursor"))
        rows = self._repository.list_cases(filters, page_size, offset)
        items = [_summary(row if _has_positional_performance(row) else self._with_positional_performance(row)) for row in rows[:page_size]]
        return {"items": items, "nextCursor": _encode_cursor(offset + page_size) if len(rows) > page_size else None, **_lineage(rows[0] if rows else {})}

    def detail(self, case_id):
        _uuid(case_id)
        row = self._repository.get_case(case_id)
        if row is None: raise LookupError("Case study not found")
        row = self._with_positional_performance(row)
        return {"caseStudy": _detail(row), **_lineage(row)}

    def chart(self, case_id, query):
        _uuid(case_id)
        row = self._repository.get_case(case_id)
        if row is None: raise LookupError("Case study not found")
        row = self._with_positional_performance(row)
        lineage = row.get("lineage") or {}
        start = row["detection_date"] - timedelta(days=90)
        horizon_end = (row.get("entry_date") or row["detection_date"]) + timedelta(days=400)
        end = min(horizon_end, row.get("study_data_as_of") or horizon_end)
        bars = self._repository.load_chart_bars(row["isin"], start, end, lineage.get("adjustmentVersion"))
        candles = [{"date": bar.get("trading_date"), "open": bar.get("open_price"), "high": bar.get("high_price"), "low": bar.get("low_price"), "close": bar.get("close_price"), "volume": bar.get("volume")} for bar in bars]
        annotations = {"detectionDate": row.get("detection_date"), "triggerDate": row.get("trigger_date"), "entryDate": row.get("entry_date"), "exitDate": row.get("exit_date"), "entryPrice": row.get("entry_price"), "stopPrice": row.get("stop_price"), "targetPrice": row.get("target_price"), "exitPrice": row.get("exit_price")}
        levels = {"pivot": row.get("pivot_price"), "support": row.get("support_price"), "invalidation": row.get("invalidation_price"), "entry": row.get("entry_price")}
        evidence = [{"patternInstanceId": str(row["id"]), "patternType": row.get("pattern_type"), "variant": row.get("variant"), "state": row.get("lifecycle_state"), "detectedDate": row.get("detection_date"), "pivotPrice": row.get("pivot_price"), "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price"), "measurements": row.get("measurements") or {}}]
        performance = row.get("_positional_performance") or {}
        milestones = [{"date": value.get("observationDate"), "label": key, "returnPct": value.get("returnPct"), "complete": value.get("complete")} for key, value in (performance.get("horizons") or {}).items() if value.get("observationDate")]
        return {"caseStudyId": str(row["id"]), "candles": candles, "annotations": annotations, "levels": levels, "markerDate": row.get("detection_date"), "evidence": evidence, "milestones": milestones, **_lineage(row)}

    def facets(self):
        source = self._repository.facets()
        return {"facets": {"stocks": _list(source, "stocks", "isin"), "patternClasses": _list(source, "pattern_classes", "pattern_class"), "patternTypes": _list(source, "pattern_types", "pattern_type"), "variants": _list(source, "variants", "variant"), "timeframes": _list(source, "timeframes", "timeframe"), "directions": _list(source, "directions", "direction"), "exitReasons": _list(source, "exit_reasons", "exit_reason"), "sectors": _list(source, "sectors", "sector_code"), "marketRegimes": _list(source, "market_regimes", "market_regime")}, "generatedAt": datetime.now(timezone.utc), "dataAsOf": None, "isStale": False}

    def review_queue(self, query):
        status = str(_one(query, "status") or "PENDING").upper()
        if status not in {"PENDING", "REVIEWED", "REJECTED"}: raise ValueError("status must be PENDING, REVIEWED, or REJECTED")
        page_size = _number(_one(query, "pageSize"), 25, 1, 100)
        offset = _number(_one(query, "offset"), 0, 0, 1_000_000)
        rows = self._repository.list_review_cases(status, page_size, offset)
        return {"items": [_summary(self._with_positional_performance(row)) for row in rows[:page_size]], "nextOffset": offset + page_size if len(rows) > page_size else None}

    def review(self, case_id, payload):
        _uuid(case_id)
        if not isinstance(payload, dict): raise ValueError("request body must be an object")
        status = str(payload.get("status") or "").upper()
        if status not in {"REVIEWED", "REJECTED"}: raise ValueError("status must be REVIEWED or REJECTED")
        existing = self._repository.get_case(case_id)
        if existing is None: raise LookupError("Case study not found")
        if status == "REVIEWED" and existing.get("pattern_type") not in SETUP_PATTERN_TYPES:
            raise ValueError("Only pattern types available on the Setups page can be published as case studies")
        row = self._repository.set_review_status(case_id, status)
        if row is None: raise LookupError("Case study not found")
        return {"caseStudy": _summary(row)}

    def delete(self, case_id):
        _uuid(case_id)
        row = self._repository.delete_case(case_id)
        if row is None: raise LookupError("Case study not found")
        return {"deletedCaseStudyId": str(row["id"])}

    def _with_positional_performance(self, row):
        enriched = dict(row)
        outcomes = enriched.get("fixed_horizon_outcomes") or {}
        performance = outcomes.get("positionalPerformance")
        if not performance:
            lineage = enriched.get("lineage") or {}
            bars = self._repository.load_trade_bars(enriched["isin"], enriched["detection_date"], lineage.get("adjustmentVersion"), 252)
            if enriched.get("study_data_as_of"):
                bars = [bar for bar in bars if _as_date(bar["trading_date"]) <= _as_date(enriched["study_data_as_of"])]
            performance = calculate_positional_performance(signal_date=enriched["detection_date"], bars=bars)
        enriched["_positional_performance"] = performance
        return enriched

def _summary(row):
    outcomes = row.get("fixed_horizon_outcomes") or {}
    performance = row.get("_positional_performance") or outcomes.get("positionalPerformance") or {}
    return {"caseStudyId": str(row["id"]), "reviewStatus": row.get("review_status", "PENDING"), "isin": row["isin"], "symbol": row.get("historical_symbol"), "companyName": row.get("historical_company_name"), "sector": row.get("sector_code"), "patternClass": row.get("pattern_class"), "patternType": row["pattern_type"], "variant": row.get("variant"), "timeframe": row["timeframe"], "direction": row["direction"], "state": row.get("lifecycle_state"), "detectionDate": row.get("detection_date"), "entryDate": performance.get("entryDate") or row.get("entry_date"), "entryPrice": performance.get("entryPrice") or row.get("entry_price"), "setupScore": row.get("setup_score"), "positionalPerformance": performance, "exitDate": row.get("exit_date"), "exitPrice": row.get("exit_price"), "exitReason": row.get("exit_reason"), "netPnl": row.get("net_pnl"), "netReturnPct": row.get("net_return_pct"), "netRMultiple": row.get("net_r_multiple")}
def _detail(row):
    return {**_summary(row), "dates": {"patternStartDate": row.get("pattern_start_date"), "triggerDate": row.get("trigger_date"), "confirmationDate": row.get("confirmation_date")}, "prices": {"entryPrice": row.get("entry_price"), "pivotPrice": row.get("pivot_price"), "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price")}, "entryRationale": _entry_rationale(row), "measurements": row.get("measurements", {}), "supportingEvidence": row.get("supporting_evidence", {}), "context": row.get("context", {}), "lineage": row.get("lineage", {})}
def _entry_rationale(row):
    pattern = row.get("variant") or row.get("pattern_type")
    state = row.get("lifecycle_state") or "detected"
    reasons = [f"The {pattern} geometry matched the versioned detector rules and reached {state} using only information available by the detection close."]
    if row.get("pivot_price") is not None: reasons.append(f"The persisted reference pivot was {row['pivot_price']}.")
    supporting = row.get("supporting_evidence") or []
    labels = [str(value.get("patternType") or value.get("pattern_type") or value) if isinstance(value, dict) else str(value) for value in supporting]
    if labels: reasons.append(f"Supporting signals present at detection: {', '.join(labels)}.")
    if row.get("setup_score") is not None: reasons.append(f"The setup evidence score was {row['setup_score']} out of 100; this ranks evidence quality and is not a return forecast.")
    cautions = []
    if not row.get("measurements"): cautions.append("Detailed detector measurements were unavailable.")
    if not row.get("context"): cautions.append("Market or sector context was unavailable.")
    return {"summary": f"Entry is anchored to the next adjusted market session after the {pattern} EOD signal.", "reasons": reasons, "cautions": cautions, "entryRule": "The signal is known only after the detection-session close, so forward performance starts at the next session's adjusted open."}
def _policy_payload(values):
    names = {"reference_capital": "referenceCapital", "risk_budget_pct": "riskBudgetPct", "maximum_entry_extension_pct": "maximumEntryExtensionPct", "target_r_multiple": "targetRMultiple", "time_exit_sessions": "timeExitSessions", "round_trip_cost_pct": "roundTripCostPct", "fixed_cost": "fixedCost", "version": "version"}
    return {external: values.get(internal) for internal, external in names.items() if internal in values}
def _lineage(row):
    lineage = row.get("lineage") or {}; return {"dataAsOf": row.get("detection_date"), "generatedAt": datetime.now(timezone.utc), "engineVersion": lineage.get("engineVersion"), "configurationVersion": lineage.get("configurationVersion"), "isStale": False}
def _one(query, name): return query.get(name, [None])[-1]
def _has_positional_performance(row): return bool(((row.get("fixed_horizon_outcomes") or {}).get("positionalPerformance") or {}).get("horizons"))
def _as_date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
def _list(source, primary, fallback): return source.get(primary) or source.get(fallback) or []
def _number(value, default, minimum, maximum):
    try: result = default if value in (None, "") else int(value)
    except (TypeError, ValueError) as exc: raise ValueError("pageSize must be an integer") from exc
    if not minimum <= result <= maximum: raise ValueError(f"pageSize must be between {minimum} and {maximum}")
    return result
def _uuid(value):
    try: UUID(str(value))
    except ValueError as exc: raise ValueError("caseStudyId must be a UUID") from exc
def _encode_cursor(offset): return base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode().rstrip("=")
def _decode_cursor(value):
    if not value: return 0
    try:
        decoded = base64.urlsafe_b64decode(str(value) + "=" * (-len(str(value)) % 4))
        offset = int(json.loads(decoded)["offset"])
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc: raise ValueError("Invalid case-study cursor") from exc
    if offset < 0: raise ValueError("Invalid case-study cursor")
    return offset
