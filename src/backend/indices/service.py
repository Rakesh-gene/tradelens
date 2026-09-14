"""Ten-year NSE index pipeline and authenticated index read model."""

from __future__ import annotations

from datetime import date, datetime, timezone

from data_pipeline.benchmark_history import BenchmarkHistoryService
from pattern_engine.enums import ImportJobType, ImportStatus
from pattern_engine.runner import PatternEngineVersions
from pattern_engine.sector_rotation import VERSION, zone


class IndexPipelineService:
    def __init__(self, indices, market, nse_client, recovery, configuration) -> None:
        self._indices, self._market, self._client = indices, market, nse_client
        self._recovery, self._configuration = recovery, configuration

    def run(self, from_date: date, to_date: date, *, initiated_by: str = "scheduler", codes=None):
        targets = [row for row in self._indices.list_enabled() if not codes or row["code"] in set(codes)]
        run_id = self._market.create_import_run(
            ImportJobType.INDEX_PIPELINE, initiated_by,
            requested_from_date=from_date, requested_to_date=to_date,
            configuration={"historyYears": 10, "engineVersion": self._configuration.version},
            securities_total=len(targets),
        )
        self._market.update_import_run(run_id, ImportStatus.RUNNING)
        completed = failed = downloaded = written = 0
        errors = []
        settings = self._configuration.section("adjustments")
        versions = PatternEngineVersions(
            self._configuration.version, self._configuration.version,
            str(settings["methodology_version"]),
        )
        try:
            downloaded += BenchmarkHistoryService(
                self._market, self._client, index_names=("NIFTY 500",)
            ).ensure_history(from_date, to_date)
        except Exception as error:
            errors.append(f"NIFTY 500 benchmark: {str(error)[:500]}")
        for target in targets:
            try:
                history = BenchmarkHistoryService(
                    self._market, self._client, index_names=(str(target["code"]),)
                )
                downloaded += history.ensure_history(from_date, to_date)
                written += self._indices.sync_bars_to_engine(
                    str(target["code"]), str(target["engine_isin"]), from_date, to_date
                )
                rebuilt = self._recovery.rebuild_security(
                    str(target["engine_isin"]), from_date, to_date, versions,
                    timeframes=("1D", "1W", "1M"), instrument_type="INDEX",
                )
                if rebuilt.get("status") not in {"COMPLETED", "PARTIAL"}:
                    raise RuntimeError(f"Pattern scan finished with {rebuilt.get('status')}")
                completed += 1
            except Exception as error:
                failed += 1
                errors.append(f"{target['code']}: {str(error)[:500]}")
        quadrant_events = 0
        try:
            quadrant_events = self._indices.reconcile_quadrants(to_date)
        except Exception as error:
            errors.append(f"Index quadrant reconciliation: {str(error)[:500]}")
        status = ImportStatus.PARTIAL if completed and (failed or errors) else ImportStatus.FAILED if failed or errors else ImportStatus.COMPLETED
        self._market.update_import_run(
            run_id, status, securities_total=len(targets), securities_completed=completed,
            securities_failed=failed, rows_downloaded=downloaded, rows_inserted=written,
            rows_rejected=failed, error_summary="; ".join(errors[:20]) or None,
            finished_at=datetime.now(timezone.utc),
        )
        return {"runId": run_id, "status": status.value, "completed": completed,
                "failed": failed, "rowsDownloaded": downloaded,
                "quadrantEvents": quadrant_events, "errors": errors}


class IndexQueryService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def list(self):
        rows = self._repository.overview_rows()
        items = [self._item(row) for row in rows]
        dates = [row.get("data_as_of") for row in rows if row.get("data_as_of")]
        data_as_of = max(dates, default=None)
        categories = []
        for category in ("BROAD_MARKET", "SECTORAL", "THEMATIC"):
            grouped = [item for item in items if item["category"] == category]
            categories.append({"id": category, "count": len(grouped), "items": grouped})
        return {
            "dataAsOf": data_as_of, "generatedAt": datetime.now(timezone.utc),
            "engineVersion": self._engine_version(rows), "configurationVersion": self._engine_version(rows),
            "isStale": data_as_of is None or (date.today() - data_as_of).days > 3,
            "count": len(items), "items": items, "categories": categories,
            "activity": [self._event(row) for row in self._repository.list_recent_events(30)],
            "methodology": "Index patterns use the same versioned daily, weekly and monthly detector pipeline as equities. Relative strength is measured against NIFTY 500. Quadrant X is 3-month RS; Y is 1-month RS minus one-third of 3-month RS.",
        }

    @staticmethod
    def _event(row):
        base = {
            "eventId": row.get("event_id"), "activityType": row.get("activity_type"),
            "eventType": row.get("event_type"), "effectiveDate": row.get("effective_date"),
            "index": {"code": row.get("index_code"), "name": row.get("index_name"),
                      "engineSecurityId": row.get("engine_isin")},
        }
        if row.get("activity_type") == "QUADRANT":
            return {**base, "previousZone": row.get("previous_state"),
                    "newZone": row.get("new_state"), "strength": row.get("strength"),
                    "momentum": row.get("momentum"),
                    "methodologyVersion": row.get("methodology_version")}
        return {**base, "patternInstanceId": row.get("pattern_instance_id"),
                "previousState": row.get("previous_state"), "newState": row.get("new_state"),
                "patternType": row.get("pattern_type"), "variant": row.get("variant")}

    @staticmethod
    def _engine_version(rows):
        return next((row.get("engine_version") for row in rows if row.get("engine_version")), VERSION)

    @staticmethod
    def _item(row):
        close, previous = row.get("last_close"), row.get("previous_close")
        change = None if close is None or previous in (None, 0) else (float(close) - float(previous)) / float(previous) * 100
        rs1, rs3 = row.get("relative_strength_1m"), row.get("relative_strength_3m")
        momentum = None if rs1 is None or rs3 is None else float(rs1) - float(rs3) / 3
        pivot = row.get("pivot_price")
        distance = None if close is None or pivot in (None, 0) else (float(close) - float(pivot)) / float(pivot) * 100
        return {
            "code": row.get("code"), "name": row.get("name"), "category": row.get("category"),
            "engineSecurityId": row.get("engine_isin"), "dataAsOf": row.get("data_as_of"),
            "lastClose": close, "dailyChangePct": change,
            "trend": {"aboveEma20": _above(close, row.get("ema_20")),
                      "aboveSma50": _above(close, row.get("sma_50")),
                      "aboveSma200": _above(close, row.get("sma_200"))},
            "relativeStrength1m": rs1, "relativeStrength3m": rs3,
            "relativeStrength6m": row.get("relative_strength_6m"),
            "relativeStrength12m": row.get("relative_strength_12m"),
            "distanceTo52WeekHighPct": row.get("distance_to_52_week_high_pct"),
            "rotation": {"strength": rs3, "momentum": momentum, "zone": zone(rs3, momentum),
                         "methodologyVersion": VERSION},
            "primarySetup": None if not row.get("pattern_id") else {
                "patternInstanceId": row.get("pattern_id"), "patternType": row.get("pattern_type"),
                "variant": row.get("variant"), "state": row.get("state"),
                "setupScore": row.get("setup_score"), "pivotPrice": pivot,
                "supportPrice": row.get("support_price"), "invalidationPrice": row.get("invalidation_price"),
                "distanceToPivotPct": distance,
            },
        }


def _above(price, average):
    return None if price is None or average is None else float(price) >= float(average)
