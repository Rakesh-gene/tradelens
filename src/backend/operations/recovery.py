"""Dependency-ordered rebuilds and detector performance diagnostics."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from time import perf_counter

from data_pipeline.adjustments import (
    AdjustmentRequest, AdjustmentService, CorporateActionAdjustmentError,
)
from pattern_engine.features import FeatureService
from pattern_engine.runner import PatternEngineVersions
from pattern_engine.swings import SwingZoneService


class RecoveryService:
    def __init__(self, market_repository, pattern_runner, configuration, *, logger=None) -> None:
        self._market = market_repository
        self._runner = pattern_runner
        self._configuration = configuration
        self._logger = logger

    def rebuild_security(
        self, isin, from_date, to_date, versions, *, dry_run=False,
        timeframes=('1D',),
    ):
        if from_date > to_date: raise ValueError("from_date cannot be after to_date")
        if dry_run:
            return {"isin": isin, "fromDate": from_date, "toDate": to_date, "versions": versions, "dryRun": True}
        prepared = self.prepare_security(isin, from_date, to_date, versions)
        prepared['timeframes'] = tuple(timeframes)
        return self.scan_prepared_security(prepared)

    def prepare_security(self, isin, from_date, to_date, versions):
        """Rebuild derived data without scanning, enabling a universe context barrier."""

        if from_date > to_date:
            raise ValueError("from_date cannot be after to_date")
        _, latest_raw_date = self._market.get_raw_bar_date_range(isin)
        if latest_raw_date is None:
            raise ValueError("No imported trading bars are available for this security")
        effective_to_date = min(to_date, latest_raw_date)
        if effective_to_date < from_date:
            raise ValueError("No imported trading bars are available within the requested range")
        started = perf_counter()
        settings = self._configuration.section("adjustments")
        try:
            adjusted = AdjustmentService(self._market).rebuild(AdjustmentRequest(
                isin, from_date, effective_to_date, versions.adjustment,
                cash_dividend_policy=str(settings["cash_dividend_policy"]),
                source_mode=str(settings["source_mode"]),
                maximum_ex_date_jump_pct=Decimal(str(
                    settings.get("maximum_adjusted_ex_date_jump_pct", 35)
                )),
            ))
        except CorporateActionAdjustmentError as error:
            invalidator = getattr(self._runner, "invalidate_security", None)
            if invalidator is not None:
                invalidator(
                    isin, effective_to_date,
                    f"CORPORATE_ACTION_DATA_QUALITY: {error}",
                )
            raise
        FeatureService(self._market).rebuild(
            isin, from_date, effective_to_date, adjusted.adjustment_version, versions.feature,
            changed_from_date=from_date,
            benchmark_bars=(self._market.load_benchmark_snapshot(from_date, effective_to_date).get("bars") or ()),
        )
        SwingZoneService(self._market).rebuild(
            isin, from_date, effective_to_date, adjusted.adjustment_version,
            versions.feature, adjusted.adjustment_version, as_of=effective_to_date,
        )
        return {
            "isin": isin, "fromDate": from_date, "toDate": to_date,
            "asOf": effective_to_date, "adjustmentVersion": adjusted.adjustment_version,
            "versions": PatternEngineVersions(
                versions.engine, versions.feature, adjusted.adjustment_version
            ),
            "prepareDurationMs": round((perf_counter() - started) * 1000),
        }

    def scan_prepared_security(self, prepared):
        """Scan a prepared security after cross-sectional sector context exists."""

        started = perf_counter()
        isin = prepared["isin"]
        effective_to_date = prepared["asOf"]
        run_options = {'initiated_by': 'recovery'}
        timeframes = tuple(prepared.get('timeframes') or ('1D',))
        if timeframes != ('1D',):
            run_options['timeframes'] = timeframes
        report = self._runner.run_security(
            isin, effective_to_date, prepared["versions"], **run_options,
        )
        failures = [
            {
                "isin": outcome.isin,
                "asOf": outcome.as_of_date,
                "reason": outcome.reason or "Pattern scan failed",
            }
            for outcome in getattr(report, "outcomes", ())
            if outcome.status == "FAILED"
        ]
        result = {"isin": isin, "asOf": effective_to_date, "adjustmentVersion": prepared["adjustmentVersion"], "runId": report.run_id, "status": report.status.value, "metrics": report.metrics, "failures": failures, "durationMs": prepared.get("prepareDurationMs", 0) + round((perf_counter() - started) * 1000)}
        if self._logger: self._logger.emit("security_rebuild_completed", run_id=report.run_id, job_type="PATTERN_SCAN", isin=isin, requested_from_date=prepared["fromDate"], requested_to_date=prepared["toDate"], duration_ms=result["durationMs"], row_count=report.metrics.get("candidatesDetected"), source_status=result["status"])
        return result

    def explain(self, security, as_of_date, versions, *, pattern_type=None):
        outcome = self._runner.evaluate_replay_target(security, as_of_date, versions)
        candidates = list(outcome.candidates)
        if pattern_type: candidates = [item for item in candidates if (item.get("candidate") or {}).get("pattern_type") == pattern_type]
        return {"isin": security["isin"], "asOf": as_of_date, "status": outcome.status, "reason": outcome.reason, "stageDecisions": outcome.stage_decisions, "candidates": candidates}

    def benchmark(self, securities, as_of_date, versions, *, maximum=100):
        selected = list(securities)[:maximum]
        started = perf_counter(); completed = failed = candidates = 0
        for security in selected:
            try:
                outcome = self._runner.evaluate_replay_target(security, as_of_date, versions)
                completed += outcome.status in {"COMPLETED", "SKIPPED"}
                candidates += len(outcome.candidates)
            except Exception:
                failed += 1
        elapsed = perf_counter() - started
        return {"asOf": as_of_date, "securities": len(selected), "completed": int(completed), "failed": failed, "candidates": candidates, "durationMs": round(elapsed * 1000), "securitiesPerSecond": len(selected) / elapsed if elapsed else None}
