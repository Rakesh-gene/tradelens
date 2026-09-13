"""Point-in-time orchestration and incremental execution for the pattern engine."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from time import perf_counter

from pattern_engine.base_detectors import detect_primary_bases
from pattern_engine.breakout_detectors import detect_breakouts
from pattern_engine.configuration import PatternEngineConfiguration
from pattern_engine.enums import ImportJobType, ImportStatus, SwingType, ZoneType
from pattern_engine.failure_detectors import detect_failures
from pattern_engine.harmonic_detectors import detect_harmonic_patterns
from pattern_engine.lifecycle import PatternLifecycleService
from pattern_engine.models import DetectionContext, PatternCandidate, PriceZone, SwingPoint, serialize_value
from pattern_engine.pullback_detectors import detect_pullbacks
from pattern_engine.reversal_detectors import detect_reversal_patterns
from pattern_engine.scoring import score_candidate
from pattern_engine.supporting_detectors import detect_supporting_patterns


_D = Decimal


class PatternScanMode(StrEnum):
    DEBUG = "DEBUG"
    CHANGED = "CHANGED"
    UNIVERSE = "UNIVERSE"
    REPLAY = "REPLAY"


@dataclass(frozen=True, slots=True)
class PatternEngineVersions:
    engine: str
    feature: str
    adjustment: str


@dataclass(frozen=True, slots=True)
class ScanTarget:
    security: Mapping[str, object]
    as_of_date: date
    timeframes: tuple[str, ...] = ('1D',)


@dataclass(frozen=True, slots=True)
class SecurityScanOutcome:
    isin: str
    as_of_date: date
    status: str
    reason: str | None
    stage_decisions: tuple[Mapping[str, object], ...]
    candidates: tuple[Mapping[str, object], ...]
    patterns_created: int = 0
    patterns_updated: int = 0
    events_emitted: int = 0


@dataclass(frozen=True, slots=True)
class PatternScanReport:
    run_id: str
    mode: PatternScanMode
    status: ImportStatus
    metrics: Mapping[str, object]
    outcomes: tuple[SecurityScanOutcome, ...]


class PatternDataSource(Protocol):
    def list_eligible_securities(self) -> list[dict[str, object]]: ...
    def list_affected_security_dates(self, run_id: str) -> list[dict[str, object]]: ...
    def load_adjusted_bars(self, isin: str, from_date: date, to_date: date, adjustment_version: str) -> list[dict[str, object]]: ...
    def load_technical_features(self, isin: str, from_date: date, to_date: date, feature_version: str) -> list[dict[str, object]]: ...
    def load_swing_points(self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None) -> list[dict[str, object]]: ...
    def load_price_zones(self, isin: str, from_date: date, to_date: date, feature_version: str, *, as_of: date | None = None) -> list[dict[str, object]]: ...
    def load_benchmark_snapshot(self, from_date: date, as_of_date: date) -> dict[str, object]: ...
    def load_sector_snapshot(self, isin: str, as_of_date: date) -> dict[str, object] | None: ...


class PatternRunRepository(Protocol):
    def create_import_run(self, job_type, initiated_by, **values) -> str: ...
    def update_import_run(self, run_id, status, **values) -> None: ...
    def update_pattern_scan_metrics(self, run_id: str, metrics: Mapping[str, object]) -> None: ...
    def record_pattern_scan_failure(self, failure: Mapping[str, object]) -> None: ...


class PatternRepository(Protocol):
    def load_active_patterns(self, isin: str, pattern_type: str | None = None) -> list[dict[str, object]]: ...
    def security_transaction(self, isin: str): ...


class PatternEngineRunner:
    """Run all detector stages in dependency order and isolate each security."""

    def __init__(
        self,
        data_source: PatternDataSource,
        pattern_repository: PatternRepository,
        run_repository: PatternRunRepository,
        configuration: PatternEngineConfiguration,
    ) -> None:
        self._data = data_source
        self._patterns = pattern_repository
        self._runs = run_repository
        self._configuration = configuration

    def run_security(
        self, isin: str, as_of_date: date, versions: PatternEngineVersions,
        *, dry_run: bool = False, initiated_by: str = "manual",
        timeframes: Sequence[str] = ('1D',),
    ) -> PatternScanReport:
        security = next(
            (row for row in self._data.list_eligible_securities() if str(row.get("isin")) == isin),
            {"isin": isin},
        )
        return self._run(
            PatternScanMode.DEBUG, (ScanTarget(security, as_of_date, tuple(timeframes)),), versions,
            dry_run=dry_run, initiated_by=initiated_by,
        )

    def invalidate_security(self, isin: str, as_of_date: date, reason: str) -> int:
        with self._patterns.security_transaction(isin) as repository:
            lifecycle = PatternLifecycleService(repository, self._configuration)
            return len(lifecycle.invalidate_active(isin, as_of_date, reason))

    def run_changed(
        self, source_run_id: str, versions: PatternEngineVersions,
        *, as_of_date: date | None = None, dry_run: bool = False,
        initiated_by: str = "scheduler",
    ) -> PatternScanReport:
        securities = {str(row["isin"]): row for row in self._data.list_eligible_securities()}
        targets = tuple(
            ScanTarget(
                securities.get(str(row["isin"]), {"isin": str(row["isin"])}),
                as_of_date or _as_date(row["latest_affected_date"]),
            )
            for row in self._data.list_affected_security_dates(source_run_id)
        )
        return self._run(
            PatternScanMode.CHANGED, targets, versions, dry_run=dry_run,
            initiated_by=initiated_by, source_run_id=source_run_id,
        )

    def run_universe(
        self, as_of_date: date, versions: PatternEngineVersions,
        *, dry_run: bool = False, initiated_by: str = "scheduler",
    ) -> PatternScanReport:
        targets = tuple(ScanTarget(row, as_of_date) for row in self._data.list_eligible_securities())
        return self._run(
            PatternScanMode.UNIVERSE, targets, versions,
            dry_run=dry_run, initiated_by=initiated_by,
        )

    def replay(
        self, isins: Sequence[str], from_date: date, to_date: date,
        versions: PatternEngineVersions, *, initiated_by: str = "manual",
    ) -> PatternScanReport:
        if from_date > to_date:
            raise ValueError("Replay from_date cannot be after to_date")
        securities = {str(row["isin"]): row for row in self._data.list_eligible_securities()}
        targets = []
        for isin in isins:
            bars = self._data.load_adjusted_bars(isin, from_date, to_date, versions.adjustment)
            targets.extend(
                ScanTarget(securities.get(isin, {"isin": isin}), _row_date(bar))
                for bar in bars
            )
        return self._run(
            PatternScanMode.REPLAY, tuple(targets), versions, dry_run=True,
            initiated_by=initiated_by, requested_from=from_date, requested_to=to_date,
        )

    def evaluate_replay_target(self, security, as_of_date, versions):
        """Evaluate one historical security/session without run or live writes."""

        return self._scan_target(ScanTarget(security, as_of_date), versions, dry_run=True)

    def _run(
        self, mode, targets, versions, *, dry_run, initiated_by,
        source_run_id=None, requested_from=None, requested_to=None,
    ):
        run_started = perf_counter()
        if any(not str(value).strip() for value in (versions.engine, versions.feature, versions.adjustment)):
            raise ValueError("Engine, feature, and adjustment versions are required")
        unique_isins = {
            str(target.security.get("isin") or "") for target in targets
            if target.security.get("isin")
        }
        configuration = {
            "patternEngine": serialize_value(self._configuration.sections),
            "mode": mode.value, "dryRun": dry_run, "sourceRunId": source_run_id,
            "versions": serialize_value(versions),
        }
        dates = [target.as_of_date for target in targets]
        run_id = self._runs.create_import_run(
            ImportJobType.PATTERN_SCAN, initiated_by,
            requested_from_date=requested_from or (min(dates) if dates else None),
            requested_to_date=requested_to or (max(dates) if dates else None),
            configuration=configuration, securities_total=len(unique_isins),
        )
        self._runs.update_import_run(run_id, ImportStatus.RUNNING)
        outcomes = []
        failures = 0
        for target in targets:
            try:
                outcomes.append(self._scan_target(target, versions, dry_run=dry_run))
            except Exception as exc:
                failures += 1
                outcome = SecurityScanOutcome(
                    str(target.security.get("isin") or ""), target.as_of_date,
                    "FAILED", str(exc), (), (),
                )
                outcomes.append(outcome)
                self._runs.record_pattern_scan_failure({
                    "run_id": run_id, "isin": outcome.isin,
                    "as_of_date": target.as_of_date, "stage": getattr(exc, "stage", "orchestration"),
                    "error_type": type(exc).__name__, "error_message": str(exc)[:2000],
                })
        completed = sum(outcome.status == "COMPLETED" for outcome in outcomes)
        skipped = sum(outcome.status == "SKIPPED" for outcome in outcomes)
        failed_isins = {outcome.isin for outcome in outcomes if outcome.status == "FAILED"}
        completed_isins = {
            outcome.isin for outcome in outcomes
            if outcome.status in {"COMPLETED", "SKIPPED"} and outcome.isin not in failed_isins
        }
        metrics = {
            "mode": mode.value, "dryRun": dry_run, "targets": len(targets),
            "securitiesTotal": len(unique_isins),
            "securitiesCompleted": len(completed_isins), "targetsCompleted": completed,
            "targetsSkipped": skipped, "securitiesFailed": len(failed_isins),
            "candidatesDetected": sum(len(outcome.candidates) for outcome in outcomes),
            "patternsCreated": sum(outcome.patterns_created for outcome in outcomes),
            "patternsUpdated": sum(outcome.patterns_updated for outcome in outcomes),
            "eventsEmitted": sum(outcome.events_emitted for outcome in outcomes),
        }
        stage_metrics = {}
        for outcome in outcomes:
            for decision in outcome.stage_decisions:
                if decision.get("durationMs") is not None:
                    stage = str(decision.get("stage"))
                    stage_metrics[stage] = stage_metrics.get(stage, 0) + int(decision["durationMs"])
        metrics["stageDurationsMs"] = stage_metrics
        metrics["durationMs"] = round((perf_counter() - run_started) * 1000)
        status = (
            ImportStatus.FAILED if failures and not completed and not skipped
            else ImportStatus.PARTIAL if failures else ImportStatus.COMPLETED
        )
        self._runs.update_pattern_scan_metrics(run_id, metrics)
        self._runs.update_import_run(
            run_id, status, securities_total=len(unique_isins),
            securities_completed=len(completed_isins), securities_failed=len(failed_isins),
            rows_downloaded=metrics["candidatesDetected"],
            rows_inserted=metrics["patternsCreated"], rows_updated=metrics["patternsUpdated"],
            rows_rejected=failures,
            error_summary=f"{failures} security scan(s) failed" if failures else None,
            duration_ms=metrics["durationMs"], stage_metrics=stage_metrics,
        )
        return PatternScanReport(run_id, mode, status, metrics, tuple(outcomes))

    def _scan_target(self, target, versions, *, dry_run):
        security, as_of = target.security, target.as_of_date
        isin = str(security.get("isin") or "")
        if not isin:
            raise ValueError("Scan target requires an ISIN")
        from_date = _years_before(as_of, int(self._configuration.section("data")["initial_history_years"]))
        bars = sorted(
            (row for row in self._data.load_adjusted_bars(isin, from_date, as_of, versions.adjustment) if _row_date(row) <= as_of),
            key=_row_date,
        )
        if not bars and ":" not in versions.adjustment:
            resolver = getattr(self._data, "resolve_adjustment_version", None)
            resolved = resolver(isin, as_of, versions.adjustment) if resolver else None
            if resolved:
                versions = PatternEngineVersions(
                    versions.engine, versions.feature, resolved
                )
                bars = sorted(
                    (row for row in self._data.load_adjusted_bars(
                        isin, from_date, as_of, resolved
                    ) if _row_date(row) <= as_of),
                    key=_row_date,
                )
        features = sorted(
            (row for row in self._data.load_technical_features(isin, from_date, as_of, versions.feature) if _row_date(row) <= as_of),
            key=_row_date,
        )
        eligibility = self._eligibility_decisions(bars, features, as_of)
        failed_rules = [decision["rule"] for decision in eligibility if not decision["passed"]]
        if failed_rules:
            return SecurityScanOutcome(
                isin, as_of, "SKIPPED", ", ".join(failed_rules),
                ({"stage": "eligibility", "decisions": eligibility},), (),
            )
        swings = tuple(_swing(row) for row in self._data.load_swing_points(
            isin, from_date, as_of, versions.feature, as_of=as_of
        ))
        zones = tuple(_zone(row) for row in self._data.load_price_zones(
            isin, from_date, as_of, versions.feature, as_of=as_of
        ))
        benchmark = _with_market_regime(self._data.load_benchmark_snapshot(from_date, as_of))
        sector = self._data.load_sector_snapshot(isin, as_of)
        current_feature = features[-1]
        context = DetectionContext(as_of, benchmark, sector, (), self._configuration.version)
        decisions = [{"stage": "eligibility", "decisions": eligibility}]
        explanations = []
        created = updated = emitted = 0
        observed_pattern_ids: set[str] = set()
        transaction = nullcontext(self._patterns) if dry_run else self._patterns.security_transaction(isin)
        with transaction as repository:
            lifecycle = PatternLifecycleService(repository, self._configuration)
            if not dry_run:
                rebased = lifecycle.invalidate_lineage_mismatches(
                    isin,
                    as_of,
                    engine_version=versions.engine,
                    feature_version=versions.feature,
                    adjustment_version=versions.adjustment,
                )
                updated += len(rebased)
                emitted += len(rebased)
                decisions.append({
                    "stage": "lineage_reconciliation",
                    "invalidated": len(rebased),
                })
            # Historical/dry evaluation must not leak today's live instances
            # into a replay date. Same-session bases are added below.
            active = [] if dry_run else _normalize_instances(repository.load_active_patterns(isin))

            stage_started = perf_counter()
            supporting = detect_supporting_patterns(
                security, bars, features, swings, zones, context, self._configuration
            )
            context = DetectionContext(
                as_of, benchmark, sector,
                tuple(sorted({candidate.pattern_type for candidate in supporting})),
                self._configuration.version,
            )
            stage_candidates = (("supporting", supporting),)
            for stage, candidates in stage_candidates:
                counts = self._process_stage(
                    stage, candidates, current_feature, bars, context, lifecycle,
                    versions, dry_run, decisions, explanations, observed_pattern_ids,
                )
                created += counts[0]; updated += counts[1]; emitted += counts[2]
            decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)

            stage_started = perf_counter()
            bases = detect_primary_bases(
                security, bars, features, swings, zones, context, self._configuration
            )
            counts = self._process_stage("bases", bases, current_feature, bars, context, lifecycle, versions, dry_run, decisions, explanations, observed_pattern_ids)
            created += counts[0]; updated += counts[1]; emitted += counts[2]
            decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)
            active = _normalize_instances(repository.load_active_patterns(isin)) if not dry_run else active + list(bases)

            for timeframe in target.timeframes:
                stage_started = perf_counter()
                reversals = detect_reversal_patterns(
                    security, bars, swings, context, self._configuration,
                    timeframe=timeframe,
                )
                counts = self._process_stage(
                    f'reversals_{timeframe}', reversals, current_feature, bars,
                    context, lifecycle, versions, dry_run, decisions, explanations,
                    observed_pattern_ids,
                )
                created += counts[0]; updated += counts[1]; emitted += counts[2]
                decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)

                stage_started = perf_counter()
                harmonics = detect_harmonic_patterns(
                    security, bars, swings, context, self._configuration,
                    timeframe=timeframe,
                )
                counts = self._process_stage(
                    f'harmonics_{timeframe}', harmonics, current_feature, bars,
                    context, lifecycle, versions, dry_run, decisions, explanations,
                    observed_pattern_ids,
                )
                created += counts[0]; updated += counts[1]; emitted += counts[2]
                decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)

            stage_started = perf_counter()
            breakouts = detect_breakouts(
                security, bars, features, zones, context, self._configuration,
                [source for source in active if str(_field(source, "pattern_type")).startswith("BASE-")],
            )
            counts = self._process_stage("breakouts", breakouts, current_feature, bars, context, lifecycle, versions, dry_run, decisions, explanations, observed_pattern_ids)
            created += counts[0]; updated += counts[1]; emitted += counts[2]
            decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)
            active = _normalize_instances(repository.load_active_patterns(isin)) if not dry_run else active + list(breakouts)

            stage_started = perf_counter()
            pullbacks = detect_pullbacks(
                security, bars, features, swings,
                [source for source in active if str(_field(source, "pattern_type")).startswith("BRK-")],
                context, self._configuration,
            )
            counts = self._process_stage("pullbacks", pullbacks, current_feature, bars, context, lifecycle, versions, dry_run, decisions, explanations, observed_pattern_ids)
            created += counts[0]; updated += counts[1]; emitted += counts[2]
            decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)
            active = _normalize_instances(repository.load_active_patterns(isin)) if not dry_run else active + list(pullbacks)

            stage_started = perf_counter()
            failures = detect_failures(
                security, bars, features, swings, active, context, self._configuration
            )
            counts = self._process_stage("failures", failures, current_feature, bars, context, lifecycle, versions, dry_run, decisions, explanations, observed_pattern_ids)
            created += counts[0]; updated += counts[1]; emitted += counts[2]
            decisions[-1]["durationMs"] = round((perf_counter() - stage_started) * 1000)
            if not dry_run:
                expirations = lifecycle.expire_stale(
                    isin,
                    as_of,
                    [_row_date(bar) for bar in bars],
                    observed_pattern_ids=observed_pattern_ids,
                )
                updated += len(expirations)
                emitted += sum(result.event_type is not None for result in expirations)
                decisions.append({"stage": "expiry", "expired": len(expirations)})
                reconciled = lifecycle.reconcile_unobserved(
                    isin, as_of, observed_pattern_ids, target.timeframes
                )
                updated += len(reconciled)
                emitted += sum(result.event_type is not None for result in reconciled)
                decisions.append({
                    "stage": "active_reconciliation",
                    "expired": sum(result.action == "expired" for result in reconciled),
                    "invalidated": sum(result.action == "invalidated" for result in reconciled),
                })
        return SecurityScanOutcome(
            isin, as_of, "COMPLETED", None, tuple(decisions), tuple(explanations),
            created, updated, emitted,
        )

    def _process_stage(
        self, stage, candidates, feature, bars, context, lifecycle, versions,
        dry_run, decisions, explanations, observed_pattern_ids,
    ):
        decisions.append({
            "stage": stage, "candidateCount": len(candidates),
            "emittedTypes": [candidate.pattern_type for candidate in candidates],
        })
        created = updated = events = 0
        close = bars[-1].get("close_price")
        for candidate in candidates:
            if stage != "supporting":
                candidate = replace(
                    candidate,
                    supporting_pattern_identifiers=tuple(sorted({
                        *candidate.supporting_pattern_identifiers,
                        *context.supporting_pattern_identifiers,
                    })),
                )
            scored = score_candidate(
                candidate, feature, context, self._configuration,
                close_price=close, history_sessions=len(bars),
            )
            scored_candidate = replace(
                scored.candidate,
                measurements={
                    **scored.candidate.measurements,
                    "scoring": {
                        "context_inputs": scored.context.normalized_inputs,
                        "context_contributions": scored.context.contributions,
                        "setup_inputs": scored.setup.normalized_inputs,
                        "setup_contributions": scored.setup.contributions,
                        "maturity_band": scored.maturity_band,
                    },
                },
            )
            explanation = {
                "stage": stage, "candidate": scored_candidate.to_dict(),
                "contextComponents": serialize_value(scored.context.contributions),
                "setupComponents": serialize_value(scored.setup.contributions),
                "featureSnapshot": serialize_value(feature),
                "marketSnapshot": serialize_value(context.benchmark_snapshot),
                "sectorSnapshot": serialize_value(context.sector_snapshot),
                "maturityBand": scored.maturity_band,
                "ruleDecision": "EMITTED",
            }
            explanations.append(explanation)
            if dry_run:
                continue
            result = lifecycle.apply_candidate(
                scored_candidate, engine_version=versions.engine,
                feature_version=versions.feature, adjustment_version=versions.adjustment,
            )
            observed_pattern_ids.add(str(result.instance["id"]))
            created += result.action == "created"
            updated += result.action == "updated"
            events += result.event_type is not None
        return int(created), int(updated), int(events)

    def _eligibility_decisions(self, bars, features, as_of):
        engine_minimum = int(self._configuration.section("engine")["minimum_history_sessions"])
        liquidity = self._configuration.section("liquidity")
        current = features[-1] if features and _row_date(features[-1]) == as_of else None
        latest_bar = bars[-1] if bars and _row_date(bars[-1]) == as_of else None
        return [
            {"rule": "as_of_adjusted_bar_available", "passed": latest_bar is not None},
            {"rule": "minimum_history_sessions", "passed": len(bars) >= engine_minimum,
             "actual": len(bars), "required": engine_minimum},
            {"rule": "as_of_feature_available", "passed": current is not None},
            {"rule": "minimum_close_price", "passed": latest_bar is not None and _number(latest_bar.get("close_price")) >= _number(liquidity["minimum_close_price"])},
            {"rule": "median_traded_value_20", "passed": current is not None and current.get("median_traded_value_20") is not None and _number(current.get("median_traded_value_20")) >= _number(liquidity["median_traded_value_20"])},
            {"rule": "median_volume_20", "passed": current is not None and current.get("median_volume_20") is not None and _number(current.get("median_volume_20")) >= _number(liquidity["median_volume_20"])},
        ]


def _normalize_instances(instances):
    return [{**row, "pattern_instance_id": row.get("pattern_instance_id") or row.get("id")} for row in instances]


def _with_market_regime(snapshot):
    result = dict(snapshot or {})
    if result.get("market_regime_score") is not None:
        return result
    bars = sorted(result.get("bars") or (), key=_row_date)
    closes = [_number(row.get("close_price")) for row in bars]
    if len(closes) < 200:
        result["market_regime_score"] = _D("0")
        return result
    latest = closes[-1]
    sma20 = sum(closes[-20:], _D("0")) / 20
    sma50 = sum(closes[-50:], _D("0")) / 50
    sma200 = sum(closes[-200:], _D("0")) / 200
    prior20 = sum(closes[-21:-1], _D("0")) / 20
    prior50 = sum(closes[-51:-1], _D("0")) / 50
    conditions = (latest > sma20, latest > sma50, latest > sma200, sma20 > prior20, sma50 > prior50)
    result.update({
        "market_regime_score": _D(sum(conditions)) / len(conditions) * 100,
        "sma_20": sma20, "sma_50": sma50, "sma_200": sma200,
        "sma_20_slope_positive": sma20 > prior20,
        "sma_50_slope_positive": sma50 > prior50,
    })
    return result


def _swing(row):
    return SwingPoint(
        str(row.get("id")) if row.get("id") is not None else None, str(row["isin"]),
        _as_date(row["pivot_date"]), _as_date(row["confirmation_date"]),
        SwingType(str(row["swing_type"])), _number(row["price"]),
        _optional_number(row.get("natr_14", row.get("natr"))),
        _optional_number(row.get("move_size_pct")), bool(row.get("is_meaningful")),
    )


def _zone(row):
    source_ids = row.get("source_swing_ids") or ()
    return PriceZone(
        str(row.get("id")) if row.get("id") is not None else None, str(row["isin"]),
        ZoneType(str(row["zone_type"])), _as_date(row["start_date"]), _as_date(row["end_date"]),
        _number(row["median_price"]), _number(row["tolerance_pct"]),
        _number(row["dispersion_pct"]), tuple(str(value) for value in source_ids),
        int(row["test_count"]), _optional_number(row.get("breakout_buffer_pct")) or _D("0"),
        _optional_date(row.get("last_test_date")), _optional_date(row.get("confirmation_date")),
    )


def _years_before(value, years):
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _field(value, name):
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name, None)


def _row_date(row):
    return _as_date(row["trading_date"])


def _as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _optional_date(value):
    return None if value is None else _as_date(value)


def _number(value):
    return value if isinstance(value, Decimal) else _D(str(value or 0))


def _optional_number(value):
    return None if value is None else _number(value)
