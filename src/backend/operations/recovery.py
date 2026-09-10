"""Dependency-ordered rebuilds and detector performance diagnostics."""

from __future__ import annotations

from datetime import date
from time import perf_counter

from data_pipeline.adjustments import AdjustmentRequest, AdjustmentService
from pattern_engine.features import FeatureService
from pattern_engine.runner import PatternEngineVersions
from pattern_engine.swings import SwingZoneService


class RecoveryService:
    def __init__(self, market_repository, pattern_runner, configuration, *, logger=None) -> None:
        self._market = market_repository
        self._runner = pattern_runner
        self._configuration = configuration
        self._logger = logger

    def rebuild_security(self, isin, from_date, to_date, versions, *, dry_run=False):
        if from_date > to_date: raise ValueError("from_date cannot be after to_date")
        if dry_run:
            return {"isin": isin, "fromDate": from_date, "toDate": to_date, "versions": versions, "dryRun": True}
        _, latest_raw_date = self._market.get_raw_bar_date_range(isin)
        if latest_raw_date is None:
            raise ValueError("No imported trading bars are available for this security")
        effective_to_date = min(to_date, latest_raw_date)
        if effective_to_date < from_date:
            raise ValueError("No imported trading bars are available within the requested range")
        started = perf_counter()
        settings = self._configuration.section("adjustments")
        adjusted = AdjustmentService(self._market).rebuild(AdjustmentRequest(
            isin, from_date, effective_to_date, versions.adjustment,
            cash_dividend_policy=str(settings["cash_dividend_policy"]),
            source_mode=str(settings["source_mode"]),
        ))
        FeatureService(self._market).rebuild(
            isin, from_date, effective_to_date, adjusted.adjustment_version, versions.feature,
            changed_from_date=from_date,
            benchmark_bars=(self._market.load_benchmark_snapshot(from_date, effective_to_date).get("bars") or ()),
        )
        SwingZoneService(self._market).rebuild(
            isin, from_date, effective_to_date, adjusted.adjustment_version,
            versions.feature, adjusted.adjustment_version, as_of=effective_to_date,
        )
        effective_versions = PatternEngineVersions(versions.engine, versions.feature, adjusted.adjustment_version)
        report = self._runner.run_security(isin, effective_to_date, effective_versions, initiated_by="recovery")
        failures = [
            {
                "isin": outcome.isin,
                "asOf": outcome.as_of_date,
                "reason": outcome.reason or "Pattern scan failed",
            }
            for outcome in getattr(report, "outcomes", ())
            if outcome.status == "FAILED"
        ]
        result = {"isin": isin, "asOf": effective_to_date, "adjustmentVersion": adjusted.adjustment_version, "runId": report.run_id, "status": report.status.value, "metrics": report.metrics, "failures": failures, "durationMs": round((perf_counter() - started) * 1000)}
        if self._logger: self._logger.emit("security_rebuild_completed", run_id=report.run_id, job_type="PATTERN_SCAN", isin=isin, requested_from_date=from_date, requested_to_date=to_date, duration_ms=result["durationMs"], row_count=report.metrics.get("candidatesDetected"), source_status=result["status"])
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
