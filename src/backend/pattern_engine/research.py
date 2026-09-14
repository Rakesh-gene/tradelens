"""Point-in-time historical replay coordination and outcome calculation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from statistics import median
from time import perf_counter
from datetime import timedelta
from typing import Protocol

from pattern_engine.models import serialize_value
from pattern_engine.runner import PatternEngineVersions, ScanTarget


HORIZONS = (5, 10, 20, 40, 60)
GAIN_THRESHOLDS = (5, 10, 20)
HIT_RULES = ((5, 5), (10, 8), (20, 8))
ENTRY_STATES = {"TRIGGERED", "CONFIRMED"}


class ResearchRepository(Protocol):
    def create_run(self, values: Mapping[str, object]) -> str: ...
    def update_run(self, run_id: str, status: str, **values) -> None: ...
    def list_trading_sessions(self, from_date: date, to_date: date, adjustment_version: str) -> list[date]: ...
    def list_historical_universe(self, index_code: str, as_of_date: date) -> list[dict[str, object]]: ...
    def list_historical_security(self, isin: str, as_of_date: date) -> list[dict[str, object]]: ...
    def load_outcome_bars(self, isin: str, entry_date: date, adjustment_version: str, limit: int) -> list[dict[str, object]]: ...
    def insert_entry_with_outcome(self, run_id: str, entry: Mapping[str, object], outcome: Mapping[str, object]) -> str: ...
    def get_run(self, run_id: str) -> dict[str, object] | None: ...
    def list_results(self, run_id: str, limit: int, offset: int) -> list[dict[str, object]]: ...


class ReplayEvaluator(Protocol):
    def evaluate(self, security: Mapping[str, object], as_of_date: date, versions: PatternEngineVersions) -> Sequence[Mapping[str, object]]: ...


class PatternReplayEvaluator:
    """Adapter that keeps historical research on the production engine path."""

    def __init__(self, runner) -> None:
        self._runner = runner

    def evaluate(self, security, as_of_date, versions):
        outcome = self._runner.evaluate_replay_target(security, as_of_date, versions)
        return outcome.candidates if outcome.status == "COMPLETED" else ()


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    from_date: date
    to_date: date
    index_code: str | None
    isin: str | None
    filters: Mapping[str, object]
    versions: PatternEngineVersions
    configuration_version: str
    minimum_sample_size: int = 30


class BacktestService:
    def __init__(self, repository: ResearchRepository, evaluator: ReplayEvaluator | None = None, *, configuration_version: str | None = None) -> None:
        self._repository = repository
        self._evaluator = evaluator
        self._configuration_version = configuration_version

    def start(self, payload: Mapping[str, object], requested_by: str | None = None, *, resumed_from_run_id: str | None = None):
        started = perf_counter()
        request = _request(payload)
        if self._evaluator is None:
            raise RuntimeError("Historical replay is not configured")
        if self._configuration_version and request.configuration_version != self._configuration_version:
            raise ValueError(f"configuration version must be {self._configuration_version}")
        run_id = self._repository.create_run({
            "requested_from_date": request.from_date,
            "requested_to_date": request.to_date,
            "universe": (
                {"isin": request.isin, "selectionPolicy": "explicit-security"}
                if request.isin else
                {"indexCode": request.index_code, "membershipPolicy": "effective-dated"}
            ),
            "filters": request.filters,
            "engine_version": request.versions.engine,
            "configuration_version": request.configuration_version,
            "feature_version": request.versions.feature,
            "adjustment_version": request.versions.adjustment,
            "minimum_sample_size": request.minimum_sample_size,
            "requested_by": requested_by,
            "point_in_time_policy": {
                "sessionReplay": True,
                "effectiveMembership": True,
                "confirmedPivotsOnly": True,
                "excludeCurrentBarFromReferenceHigh": True,
                "futureBarsUsedForOutcomesOnly": True,
            },
            "resumed_from_run_id": resumed_from_run_id,
        })
        self._repository.update_run(run_id, "RUNNING", started_at=datetime.now(timezone.utc))
        sessions_processed = securities_evaluated = entries_recorded = 0
        seen = set()
        try:
            sessions = self._repository.list_trading_sessions(
                request.from_date, request.to_date, request.versions.adjustment
            )
            for session in sessions:
                sessions_processed += 1
                securities = (
                    self._repository.list_historical_security(request.isin, session)
                    if request.isin else
                    self._repository.list_historical_universe(request.index_code, session)
                )
                for security in securities:
                    securities_evaluated += 1
                    for explanation in self._evaluator.evaluate(security, session, request.versions):
                        candidate = explanation.get("candidate") or {}
                        if not _matches(candidate, explanation, security, request.filters):
                            continue
                        fingerprint_key = _fingerprint_key(candidate)
                        if fingerprint_key in seen:
                            continue
                        entry_date = _entry_date(candidate)
                        if not request.from_date <= entry_date <= request.to_date:
                            continue
                        bars = self._repository.load_outcome_bars(
                            str(candidate["isin"]), entry_date, request.versions.adjustment, max(HORIZONS) + 1
                        )
                        if not bars or _as_date(bars[0]["trading_date"]) != entry_date:
                            continue
                        entry_price = _decimal(bars[0]["close_price"])
                        outcome = calculate_outcomes(entry_price, bars)
                        feature = explanation.get("featureSnapshot") or {}
                        market = explanation.get("marketSnapshot") or {}
                        entry = {
                            "fingerprint_key": fingerprint_key,
                            "isin": candidate["isin"], "pattern_class": candidate["pattern_class"],
                            "pattern_type": candidate["pattern_type"], "variant": candidate.get("variant"),
                            "state": candidate["state"], "entry_date": entry_date, "entry_price": entry_price,
                            "quality_score": candidate.get("quality_score"),
                            "maturity_score": candidate.get("maturity_score"),
                            "context_score": candidate.get("context_score"),
                            "setup_score": candidate.get("setup_score"),
                            "relative_strength_6m": feature.get("relative_strength_6m", feature.get("relative_strength_percentile")),
                            "market_regime_score": market.get("market_regime_score"),
                            "sector_code": security.get("sector_code"),
                            "candidate_fingerprint": explanation,
                        }
                        self._repository.insert_entry_with_outcome(run_id, entry, outcome)
                        seen.add(fingerprint_key)
                        entries_recorded += 1
                self._repository.update_run(
                    run_id, "RUNNING", last_completed_session=session,
                    sessions_processed=sessions_processed,
                    securities_evaluated=securities_evaluated,
                    entries_recorded=entries_recorded,
                )
            self._repository.update_run(
                run_id, "COMPLETED", sessions_processed=sessions_processed,
                securities_evaluated=securities_evaluated, entries_recorded=entries_recorded,
                completed_at=datetime.now(timezone.utc), duration_ms=round((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            self._repository.update_run(
                run_id, "FAILED", sessions_processed=sessions_processed,
                securities_evaluated=securities_evaluated, entries_recorded=entries_recorded,
                error_message=str(exc)[:2000], completed_at=datetime.now(timezone.utc), duration_ms=round((perf_counter() - started) * 1000),
            )
            raise
        return self.get_run(run_id)

    def resume(self, run_id, requested_by=None):
        run = self._repository.get_run(run_id)
        if run is None: raise LookupError("Backtest run not found")
        if run["status"] == "COMPLETED": raise ValueError("Completed backtest runs do not need resuming")
        from_date = run["requested_from_date"]
        if run.get("last_completed_session") is not None:
            from_date = run["last_completed_session"] + timedelta(days=1)
        if from_date > run["requested_to_date"]: raise ValueError("Backtest has no remaining sessions")
        return self.start({
            "fromDate": from_date, "toDate": run["requested_to_date"],
            "universe": run["universe"], "filters": run["filters"],
            "minimumSampleSize": run["minimum_sample_size"],
            "versions": {"engine": run["engine_version"], "configuration": run["configuration_version"], "feature": run["feature_version"], "adjustment": run["adjustment_version"]},
        }, requested_by, resumed_from_run_id=run_id)

    def get_run(self, run_id):
        run = self._repository.get_run(run_id)
        if run is None:
            raise LookupError("Backtest run not found")
        return {"run": _run_payload(run)}

    def results(self, run_id, query):
        run = self._repository.get_run(run_id)
        if run is None:
            raise LookupError("Backtest run not found")
        page_size = _bounded_int(_one(query, "pageSize"), 50, 10, 100, "pageSize")
        offset = _bounded_int(_one(query, "offset"), 0, 0, 1_000_000, "offset")
        rows = self._repository.list_results(run_id, page_size + 1, offset)
        items = [_result_payload(row) for row in rows[:page_size]]
        all_rows = self._repository.list_results(run_id, 1_000_000, 0)
        return {
            "run": _run_payload(run), "summary": summarize_results(all_rows, int(run["minimum_sample_size"])),
            "items": items, "nextOffset": offset + page_size if len(rows) > page_size else None,
        }


def calculate_outcomes(entry_price, bars):
    entry = _decimal(entry_price)
    future = list(bars)[1:]
    returns, mfe, mae, completeness = {}, {}, {}, {}
    for horizon in HORIZONS:
        window = future[:horizon]
        complete = len(window) >= horizon
        key = str(horizon)
        completeness[key] = {"complete": complete, "availableSessions": len(window)}
        returns[key] = ((_decimal(window[-1]["close_price"]) / entry) - 1) * 100 if complete else None
        mfe[key] = ((max(_decimal(row["high_price"]) for row in window) / entry) - 1) * 100 if window else None
        mae[key] = ((min(_decimal(row["low_price"]) for row in window) / entry) - 1) * 100 if window else None
    days_to = {
        str(threshold): _first_day(future, lambda row, value=threshold: (_decimal(row["high_price"]) / entry - 1) * 100 >= value)
        for threshold in GAIN_THRESHOLDS
    }
    hit_before = {}
    for gain, loss in HIT_RULES:
        gain_day = _first_day(future, lambda row, value=gain: (_decimal(row["high_price"]) / entry - 1) * 100 >= value)
        loss_day = _first_day(future, lambda row, value=loss: (_decimal(row["low_price"]) / entry - 1) * 100 <= -value)
        hit_before[f"plus{gain}BeforeMinus{loss}"] = None if gain_day is None and loss_day is None else gain_day is not None and (loss_day is None or gain_day < loss_day)
    return {"returns_by_horizon": returns, "mfe_by_horizon": mfe, "mae_by_horizon": mae, "days_to_threshold": days_to, "hit_before_loss": hit_before, "completeness": completeness}


def summarize_results(rows, minimum_sample_size):
    summary = {"totalEntries": len(rows), "minimumSampleSize": minimum_sample_size, "horizons": {}, "hitBeforeLoss": {}}
    for horizon in HORIZONS:
        key = str(horizon)
        values = [_nested(row, "returns_by_horizon", key) for row in rows]
        values = [_decimal(value) for value in values if value is not None]
        mfe_values = [_decimal(value) for value in (_nested(row, "mfe_by_horizon", key) for row in rows) if value is not None]
        mae_values = [_decimal(value) for value in (_nested(row, "mae_by_horizon", key) for row in rows) if value is not None]
        summary["horizons"][key] = {
            "sampleCount": len(values), "missingCount": len(rows) - len(values),
            "averageReturnPct": sum(values, Decimal("0")) / len(values) if values else None,
            "medianReturnPct": median(values) if values else None,
            "medianMfePct": median(mfe_values) if mfe_values else None,
            "medianMaePct": median(mae_values) if mae_values else None,
        }
    for gain, loss in HIT_RULES:
        key = f"plus{gain}BeforeMinus{loss}"
        values = [_nested(row, "hit_before_loss", key) for row in rows]
        values = [value for value in values if value is not None]
        summary["hitBeforeLoss"][key] = {"sampleCount": len(values), "probabilityPct": (Decimal(sum(bool(value) for value in values)) / len(values) * 100) if len(values) >= minimum_sample_size else None, "adequateSample": len(values) >= minimum_sample_size}
    return summary


def _request(payload):
    from_date, to_date = _date_value(payload.get("fromDate"), "fromDate"), _date_value(payload.get("toDate"), "toDate")
    if from_date > to_date: raise ValueError("fromDate cannot be after toDate")
    universe = payload.get("universe") or {}
    index_code = str(universe.get("indexCode") or "").strip() or None
    isin = str(universe.get("isin") or "").strip().upper() or None
    if bool(index_code) == bool(isin):
        raise ValueError("universe must contain exactly one of indexCode or isin")
    if isin and not re.fullmatch(r"[A-Z0-9]{12}", isin):
        raise ValueError("universe.isin must be a valid 12-character ISIN")
    versions = payload.get("versions") or {}
    engine, feature, adjustment = (str(versions.get(name) or "").strip() for name in ("engine", "feature", "adjustment"))
    if not all((engine, feature, adjustment)): raise ValueError("engine, feature, and adjustment versions are required")
    configuration = str(versions.get("configuration") or "").strip()
    if not configuration: raise ValueError("configuration version is required")
    minimum = _bounded_int(payload.get("minimumSampleSize"), 30, 1, 10000, "minimumSampleSize")
    return BacktestRequest(from_date, to_date, index_code, isin, _validated_filters(payload.get("filters") or {}), PatternEngineVersions(engine, feature, adjustment), configuration, minimum)


def _matches(candidate, explanation, security, filters):
    state = str(candidate.get("state") or "")
    if state not in ENTRY_STATES: return False
    for key, candidate_key in (("patternClass", "pattern_class"), ("patternType", "pattern_type"), ("variant", "variant")):
        if filters.get(key) and candidate.get(candidate_key) != filters[key]: return False
    if filters.get("sector") and security.get("sector_code") != filters["sector"]: return False
    supporting = set(candidate.get("supporting_pattern_identifiers") or ())
    required = filters.get("requiredSupporting") or ()
    if isinstance(required, str): required = [required]
    if filters.get("stage2"): required = [*required, "TREND-S2"]
    if filters.get("volumeCompression"): required = [*required, "VOL-DRY"]
    if not set(required).issubset(supporting): return False
    feature, market = explanation.get("featureSnapshot") or {}, explanation.get("marketSnapshot") or {}
    rs = feature.get("relative_strength_6m", feature.get("relative_strength_percentile"))
    if filters.get("minRs6m") is not None and (rs is None or _decimal(rs) < _decimal(filters["minRs6m"])): return False
    regime = market.get("market_regime_score")
    if filters.get("minMarketScore") is not None and (regime is None or _decimal(regime) < _decimal(filters["minMarketScore"])): return False
    sector = explanation.get("sectorSnapshot") or {}
    sector_score = sector.get("sector_strength_score")
    if filters.get("minSectorScore") is not None and (sector_score is None or _decimal(sector_score) < _decimal(filters["minSectorScore"])): return False
    compression = feature.get("volume_contraction_ratio")
    if filters.get("maxVolumeCompression") is not None and (compression is None or _decimal(compression) > _decimal(filters["maxVolumeCompression"])): return False
    return True


def _fingerprint_key(candidate):
    stable = {key: candidate.get(key) for key in ("isin", "pattern_type", "variant", "start_date", "pivot_price")}
    return hashlib.sha256(json.dumps(serialize_value(stable), sort_keys=True).encode()).hexdigest()


def _entry_date(candidate):
    measurements = candidate.get("measurements") or {}
    return _as_date(measurements.get("breakout_date") or candidate.get("detected_date"))


def _run_payload(row):
    return {"runId": str(row["id"]), "status": row["status"], "fromDate": row["requested_from_date"], "toDate": row["requested_to_date"], "universe": row["universe"], "filters": row["filters"], "versions": {"engine": row["engine_version"], "configuration": row["configuration_version"], "feature": row["feature_version"], "adjustment": row["adjustment_version"]}, "pointInTimePolicy": row["point_in_time_policy"], "minimumSampleSize": row["minimum_sample_size"], "sessionsProcessed": row.get("sessions_processed", 0), "securitiesEvaluated": row.get("securities_evaluated", 0), "entriesRecorded": row.get("entries_recorded", 0), "lastCompletedSession": row.get("last_completed_session"), "resumedFromRunId": str(row["resumed_from_run_id"]) if row.get("resumed_from_run_id") else None, "durationMs": row.get("duration_ms"), "errorMessage": row.get("error_message"), "createdAt": row.get("created_at"), "completedAt": row.get("completed_at")}


def _result_payload(row):
    return {"entryId": str(row["id"]), "isin": row["isin"], "patternClass": row["pattern_class"], "patternType": row["pattern_type"], "variant": row.get("variant"), "state": row["state"], "entryDate": row["entry_date"], "entryPrice": row["entry_price"], "qualityScore": row.get("quality_score"), "maturityScore": row.get("maturity_score"), "contextScore": row.get("context_score"), "setupScore": row.get("setup_score"), "relativeStrength6m": row.get("relative_strength_6m"), "marketRegimeScore": row.get("market_regime_score"), "sectorCode": row.get("sector_code"), "fingerprint": row["candidate_fingerprint"], "returnsByHorizon": row["returns_by_horizon"], "mfeByHorizon": row["mfe_by_horizon"], "maeByHorizon": row["mae_by_horizon"], "daysToThreshold": row["days_to_threshold"], "hitBeforeLoss": row["hit_before_loss"], "completeness": row["completeness"]}


def _first_day(rows, predicate):
    return next((index for index, row in enumerate(rows, start=1) if predicate(row)), None)
def _nested(row, field, key): return (row.get(field) or {}).get(key)
def _one(query, name): return query.get(name, [None])[-1]
def _date_value(value, name):
    try: return _as_date(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"{name} must be an ISO date") from exc
def _as_date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
def _decimal(value): return value if isinstance(value, Decimal) else Decimal(str(value))
def _bounded_int(value, default, minimum, maximum, name):
    try: result = default if value in (None, "") else int(value)
    except (TypeError, ValueError) as exc: raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= result <= maximum: raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def _validated_filters(value):
    if not isinstance(value, Mapping):
        raise ValueError("filters must be an object")
    allowed = {"patternClass", "patternType", "variant", "sector", "requiredSupporting", "stage2", "volumeCompression", "minRs6m", "minMarketScore", "minSectorScore", "maxVolumeCompression"}
    unknown = set(value) - allowed
    if unknown: raise ValueError(f"Unknown research filter: {sorted(unknown)[0]}")
    result = dict(value)
    for name in ("patternClass", "patternType", "variant", "sector"):
        if name in result and (not isinstance(result[name], str) or not result[name].strip()):
            raise ValueError(f"{name} must be a non-empty string")
    for name in ("stage2", "volumeCompression"):
        if name in result and not isinstance(result[name], bool):
            raise ValueError(f"{name} must be a boolean")
    required = result.get("requiredSupporting")
    if required is not None and not isinstance(required, (str, list, tuple)):
        raise ValueError("requiredSupporting must be a string or list")
    for name in ("minRs6m", "minMarketScore", "minSectorScore"):
        if name in result:
            score = _decimal(result[name])
            if not 0 <= score <= 100: raise ValueError(f"{name} must be between 0 and 100")
            result[name] = score
    if "maxVolumeCompression" in result:
        ratio = _decimal(result["maxVolumeCompression"])
        if ratio < 0: raise ValueError("maxVolumeCompression must be zero or greater")
        result["maxVolumeCompression"] = ratio
    return result
