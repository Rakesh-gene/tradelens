"""Asynchronous, resumable case-study build orchestration."""
from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
import re
from threading import Lock, Thread

from pattern_engine.case_study_selection import SELECTION_POLICY_VERSION, select_representative_cases
from pattern_engine.enums import SETUP_PATTERN_TYPES
from pattern_engine.positional_performance import calculate_positional_performance, preferred_forward_return
from pattern_engine.trade_simulation import SwingTradePolicy, simulate_swing_trade

ACTIVE_ENTRY_STATES = {"TRIGGERED", "CONFIRMED"}
TIMEFRAMES = {"1D", "1W", "1M"}
TRADE_DIRECTIONS = {"BULLISH", "BEARISH", "NEUTRAL"}
LOOKBACK_MONTHS = {"3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60}

class CaseStudyPipeline:
    def __init__(self, repository, research_service=None, *, versions=None, configuration_version=None):
        self._repository = repository
        self._research_service = research_service
        self._versions = versions
        self._configuration_version = configuration_version
        self._active = set()
        self._active_lock = Lock()
        self._repository.recover_interrupted_runs()

    def start(self, payload, requested_by=None):
        request = _request(payload)
        if self._research_service is None or self._versions is None or not self._configuration_version:
            raise RuntimeError("Case-study builds are not configured")
        context = self._repository.resolve_stock_build_context(request["isin"], self._versions.adjustment)
        if context is None:
            raise LookupError("The selected stock has no adjusted history available")
        to_date = _date(context["data_as_of"])
        from_date = _subtract_months(to_date, LOOKBACK_MONTHS[request["lookback"]])
        policy = SwingTradePolicy()
        run_id = self._repository.create_run({
            "requested_from_date": from_date, "requested_to_date": to_date,
            "universe": {"isin": request["isin"], "symbol": context.get("symbol"), "companyName": context.get("company_name"), "lookback": request["lookback"]},
            "source_backtest_run_id": None,
            "requested_pattern_types": list(SETUP_PATTERN_TYPES), "requested_timeframes": ["1D", "1W", "1M"],
            "engine_version": self._versions.engine, "configuration_version": self._configuration_version,
            "feature_version": self._versions.feature, "adjustment_version": self._versions.adjustment,
            "trade_policy_version": policy.version, "selection_policy_version": SELECTION_POLICY_VERSION,
            "trade_policy_inputs": policy.inputs(), "selection_policy_inputs": {"basis": "forwardStockReturn", "horizons": ["3M", "6M", "1Y"], "representatives": ["HIGHEST_FORWARD_RETURN", "MEDIAN_FORWARD_RETURN", "LOWEST_FORWARD_RETURN", "FIRST_INCOMPLETE_FORWARD_WINDOW"]},
            "point_in_time_policy": {"sessionReplay": True, "nextSessionEntry": True, "futureBarsUsedForOutcomesOnly": True},
            "survivorship_bias_policy": {"explicitSecurity": True}, "requested_by": requested_by,
        })
        self._start_worker(run_id)
        return self.get(run_id)

    def _start_worker(self, run_id):
        with self._active_lock:
            if run_id in self._active: raise ValueError("Case-study run is already active")
            self._active.add(run_id)
        Thread(target=self._run_guarded, args=(run_id,), daemon=True).start()

    def _run_guarded(self, run_id):
        try:
            self._prepare_source(run_id)
            self._run(run_id)
        except Exception as exc:
            self._repository.update_run(run_id, status="FAILED", failure_summary={"pipeline": str(exc)[:1000]}, completed_at=datetime.now(timezone.utc))
        finally:
            with self._active_lock: self._active.discard(run_id)

    def _prepare_source(self, run_id):
        run = self._repository.get_run(run_id)
        if run is None: raise LookupError("Case-study run not found")
        if run.get("source_backtest_run_id"):
            previous = self._research_service.get_run(str(run["source_backtest_run_id"]))["run"] if self._research_service else None
            if previous and previous["status"] == "COMPLETED": return
            # An interrupted replay is not complete point-in-time evidence.
            # Restart it as a new source run rather than building from a prefix.
            self._repository.update_run(run_id, source_backtest_run_id=None)
        if self._research_service is None: raise RuntimeError("Historical replay is not configured")
        self._repository.update_run(run_id, status="RUNNING", started_at=run.get("started_at") or datetime.now(timezone.utc), completed_at=None)
        source = self._research_service.start({
            "fromDate": run["requested_from_date"], "toDate": run["requested_to_date"],
            "universe": {"isin": run["universe"]["isin"]}, "filters": {},
            "versions": {
                "engine": run["engine_version"], "configuration": run["configuration_version"],
                "feature": run["feature_version"], "adjustment": run["adjustment_version"],
            },
        }, run.get("requested_by"), on_run_created=lambda source_id: self._repository.update_run(run_id, source_backtest_run_id=source_id))
        source_run = source["run"]
        if source_run["status"] != "COMPLETED": raise RuntimeError("Historical replay did not complete")
        self._repository.update_run(run_id, source_backtest_run_id=source_run["runId"])

    def _run(self, run_id):
        run = self._repository.get_run(run_id)
        if run is None: raise LookupError("Case-study run not found")
        self._repository.update_run(run_id, status="RUNNING", started_at=run.get("started_at") or datetime.now(timezone.utc), completed_at=None)
        policy = _policy(run.get("trade_policy_inputs") or {})
        entries = self._repository.list_source_entries(str(run["source_backtest_run_id"]))
        entries = [row for row in entries if _eligible(row, run)]
        by_security = defaultdict(list)
        for row in entries: by_security[str(row["isin"])].append(row)
        selected_isin = str((run.get("universe") or {}).get("isin") or "")
        if selected_isin: by_security.setdefault(selected_isin, [])
        simulated, failures = [], {}
        for isin in sorted(by_security):
            try:
                security_simulations = [self._simulate(entry, run, policy) for entry in by_security[isin]]
                simulated.extend(security_simulations)
                self._repository.record_item(run_id, isin, "COMPLETED")
            except Exception as exc:
                failures[isin] = str(exc)[:1000]
                self._repository.record_item(run_id, isin, "FAILED", error_message=failures[isin])

        recorded_by_isin = defaultdict(int)
        selected_by_security = defaultdict(list)
        for selected in select_representative_cases(simulated): selected_by_security[selected["isin"]].append(selected)
        for isin in sorted(selected_by_security):
            try:
                for selected in selected_by_security[isin]:
                    case_id = self._repository.add_case(_case_values(run_id, run, selected))
                    if case_id: recorded_by_isin[isin] += 1
            except Exception as exc:
                failures[isin] = str(exc)[:1000]
                self._repository.record_item(run_id, isin, "FAILED", recorded_by_isin[isin], failures[isin])
        for isin in sorted(by_security):
            if isin not in failures: self._repository.record_item(run_id, isin, "COMPLETED", recorded_by_isin[isin])
        status = "PARTIAL" if failures else "COMPLETED"
        self._repository.update_run(
            run_id, status=status, securities_total=len(by_security),
            securities_completed=len(by_security) - len(failures), securities_failed=len(failures),
            cases_recorded=sum(recorded_by_isin.values()), failure_summary=failures,
            completed_at=datetime.now(timezone.utc),
        )

    def _simulate(self, entry, run, policy):
        fingerprint = entry.get("candidate_fingerprint") or {}
        candidate = fingerprint.get("candidate") or fingerprint
        signal_date = _date(candidate.get("trigger_date") or candidate.get("detected_date") or entry["entry_date"])
        bars = self._repository.load_trade_bars(entry["isin"], signal_date, run["adjustment_version"], 252)
        direction = str(candidate.get("direction") or "NEUTRAL").upper()
        # A neutral setup still has meaningful forward stock performance. The
        # legacy trade simulation is secondary lineage and models a long stock.
        trade_direction = "BULLISH" if direction == "NEUTRAL" else direction
        trade = simulate_swing_trade(signal_date=signal_date, bars=bars, invalidation_price=candidate.get("invalidation_price"), pivot_price=candidate.get("pivot_price"), direction=trade_direction, policy=policy)
        performance = calculate_positional_performance(signal_date=signal_date, bars=bars)
        return {
            "source": entry, "candidate": candidate, "fingerprint": fingerprint, "trade": trade, "positional_performance": performance,
            "pattern_type": entry["pattern_type"], "variant": entry.get("variant"),
            "timeframe": str(candidate.get("timeframe") or "1D"), "direction": direction,
            "market_regime": _regime(entry.get("market_regime_score")),
            "sector_context": _regime((fingerprint.get("sectorSnapshot") or {}).get("sector_strength_score")),
            "net_r_multiple": trade.get("net_r_multiple"), "entry_date": trade.get("entry_date"),
            "status": trade.get("status"), "exit_reason": trade.get("exit_reason"), "ambiguous": trade.get("ambiguous", False),
            "forward_return_pct": preferred_forward_return(performance),
            "isin": str(entry["isin"]), "replay_fingerprint": entry["fingerprint_key"],
        }

    def get(self, run_id):
        row = self._repository.get_run(run_id)
        if row is None: raise LookupError("Case-study run not found")
        payload = _run_payload(row)
        source_id = row.get("source_backtest_run_id")
        source = self._research_service.get_run(str(source_id))["run"] if source_id and self._research_service is not None else None
        if row["status"] in {"COMPLETED", "PARTIAL"}:
            payload["stage"], payload["progressPct"] = "COMPLETED", 100
        elif row["status"] == "FAILED":
            payload["stage"], payload["progressPct"] = "FAILED", None
        elif source and source["status"] == "COMPLETED":
            payload["stage"], payload["progressPct"] = "BUILDING_CASES", 90
        elif source:
            payload["stage"] = "REPLAYING_HISTORY"
            last = source.get("lastCompletedSession")
            from_date, to_date = row["requested_from_date"], row["requested_to_date"]
            payload["progressPct"] = min(89, max(0, round(90 * (_date(last) - from_date).days / max(1, (to_date - from_date).days)))) if last else 0
        else:
            payload["stage"], payload["progressPct"] = "PREPARING_HISTORY", 0
        payload["sessionsProcessed"] = source.get("sessionsProcessed", 0) if source else 0
        payload["lastCompletedSession"] = source.get("lastCompletedSession") if source else None
        payload["sourceEntriesRecorded"] = source.get("entriesRecorded", 0) if source else 0
        payload["caseStudyIds"] = self._repository.list_case_ids(run_id)
        return {"run": payload}

    def latest(self, requested_by):
        run_id = self._repository.latest_run_id(requested_by)
        return self.get(run_id) if run_id else {"run": None}

    def items(self, run_id, query):
        if self._repository.get_run(run_id) is None: raise LookupError("Case-study run not found")
        page_size = _bounded_int(_one(query, "pageSize"), 50, 1, 100)
        offset = _bounded_int(_one(query, "offset"), 0, 0, 1_000_000)
        rows = self._repository.list_run_items(run_id, page_size + 1, offset)
        return {"items": [{"isin": row["isin"], "status": row["status"], "casesRecorded": row.get("cases_recorded", 0), "errorMessage": row.get("error_message"), "updatedAt": row.get("updated_at")} for row in rows[:page_size]], "nextOffset": offset + page_size if len(rows) > page_size else None}

    def resume(self, run_id):
        row = self._repository.get_run(run_id)
        if row is None: raise LookupError("Case-study run not found")
        if row["status"] in {"PENDING", "RUNNING"}: raise ValueError("Case-study run is already active")
        if row["status"] == "COMPLETED": raise ValueError("Completed case-study runs do not need resuming")
        self._start_worker(run_id)
        return self.get(run_id)

def _request(payload):
    if not isinstance(payload, dict): raise ValueError("request body must be an object")
    unknown = set(payload) - {"isin", "lookback"}
    if unknown: raise ValueError(f"Unknown case-study build field: {sorted(unknown)[0]}")
    isin = str(payload.get("isin") or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{12}", isin): raise ValueError("isin must be a valid 12-character ISIN")
    lookback = str(payload.get("lookback") or "").strip().upper()
    if lookback not in LOOKBACK_MONTHS: raise ValueError("lookback must be one of 3M, 6M, 1Y, 3Y, or 5Y")
    return {"isin": isin, "lookback": lookback}

def _policy(values):
    names = {"referenceCapital": "reference_capital", "riskBudgetPct": "risk_budget_pct", "maximumEntryExtensionPct": "maximum_entry_extension_pct", "targetRMultiple": "target_r_multiple", "timeExitSessions": "time_exit_sessions", "roundTripCostPct": "round_trip_cost_pct", "fixedCost": "fixed_cost"}
    kwargs = {}
    for external, internal in names.items():
        value = values.get(external, values.get(internal))
        if value is not None: kwargs[internal] = int(value) if internal == "time_exit_sessions" else Decimal(str(value))
    return SwingTradePolicy(**kwargs)

def _eligible(row, run):
    candidate = (row.get("candidate_fingerprint") or {}).get("candidate") or {}
    detected = _date(candidate.get("trigger_date") or candidate.get("detected_date") or row["entry_date"])
    timeframe = str(candidate.get("timeframe") or "1D")
    direction = str(candidate.get("direction") or "BULLISH").upper()
    requested_types = set(run.get("requested_pattern_types") or SETUP_PATTERN_TYPES)
    return row.get("state") in ACTIVE_ENTRY_STATES and direction in TRADE_DIRECTIONS and run["requested_from_date"] <= detected <= run["requested_to_date"] and timeframe in set(run["requested_timeframes"]) and row["pattern_type"] in set(SETUP_PATTERN_TYPES) and row["pattern_type"] in requested_types

def _case_values(run_id, run, selected):
    source, candidate, fingerprint, trade = selected["source"], selected["candidate"], selected["fingerprint"], selected["trade"]
    return {
        "case_study_run_id": run_id, "source_backtest_run_id": str(run["source_backtest_run_id"]),
        "source_backtest_entry_id": source["id"], "replay_fingerprint": source["fingerprint_key"],
        "isin": source["isin"], "historical_symbol": source.get("historical_symbol"),
        "historical_company_name": source.get("historical_company_name"), "pattern_class": source["pattern_class"],
        "pattern_type": source["pattern_type"], "variant": source.get("variant"), "pattern_group": candidate.get("pattern_group"), "direction": selected["direction"],
        "timeframe": selected["timeframe"], "lifecycle_state": source["state"],
        "pattern_start_date": candidate.get("start_date"), "detection_date": _date(candidate.get("detected_date") or source["entry_date"]),
        "trigger_date": candidate.get("trigger_date") or source["entry_date"], "confirmation_date": candidate.get("confirmation_date"),
        "entry_date": (selected.get("positional_performance") or {}).get("entryDate") or trade.get("entry_date"),
        "entry_price": (selected.get("positional_performance") or {}).get("entryPrice") or trade.get("entry_price"),
        **{key: trade.get(key) for key in ("exit_date", "stop_price", "target_price", "exit_price")},
        "pivot_price": candidate.get("pivot_price"), "support_price": candidate.get("support_price"), "invalidation_price": candidate.get("invalidation_price"),
        "measurements": candidate.get("measurements") or {}, "supporting_evidence": candidate.get("supporting_pattern_identifiers") or [],
        "context": {"market": fingerprint.get("marketSnapshot") or {}, "sector": fingerprint.get("sectorSnapshot") or {}, "features": fingerprint.get("featureSnapshot") or {}},
        "exit_reason": trade["exit_reason"], "completeness": {"status": trade["status"], "availableSessions": trade.get("available_sessions")},
        "ambiguity": {"ambiguous": trade.get("ambiguous", False), "sameSessionPolicy": trade["same_session_policy"]},
        "lineage": {"engineVersion": run["engine_version"], "configurationVersion": run["configuration_version"], "featureVersion": run["feature_version"], "adjustmentVersion": run["adjustment_version"], "tradePolicyVersion": run["trade_policy_version"], "selectionPolicyVersion": run["selection_policy_version"]},
        "selection_policy_version": run["selection_policy_version"], "selection_reason": selected["selection_reason"],
        "sector_code": source.get("sector_code"), "setup_score": source.get("setup_score"), "market_regime": selected["market_regime"], "sector_context": selected["sector_context"],
        "fixed_horizon_outcomes": {"positionalPerformance": selected.get("positional_performance") or {}, "shortSessionResearch": {"returns": source.get("returns_by_horizon") or {}, "mfe": source.get("mfe_by_horizon") or {}, "mae": source.get("mae_by_horizon") or {}}},
        "horizon_completeness": source.get("horizon_completeness") or {}, "trade": trade,
    }

def _run_payload(row):
    universe = row.get("universe") or {}
    return {"runId": str(row["id"]), "status": row["status"], "stock": {"isin": universe.get("isin"), "symbol": universe.get("symbol"), "name": universe.get("companyName")}, "lookback": universe.get("lookback"), "fromDate": row["requested_from_date"], "toDate": row["requested_to_date"], "tradePolicyVersion": row["trade_policy_version"], "selectionPolicyVersion": row["selection_policy_version"], "securitiesTotal": row.get("securities_total", 0), "securitiesCompleted": row.get("securities_completed", 0), "securitiesFailed": row.get("securities_failed", 0), "casesRecorded": row.get("cases_recorded", 0), "failureSummary": row.get("failure_summary") or {}, "createdAt": row.get("created_at"), "startedAt": row.get("started_at"), "completedAt": row.get("completed_at")}

def _subtract_months(value, months):
    month_index = value.year * 12 + value.month - 1 - months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))
def _regime(value):
    if value is None: return "UNKNOWN"
    score = Decimal(str(value)); return "STRONG" if score >= 67 else "WEAK" if score < 34 else "NEUTRAL"
def _one(query, name): return query.get(name, [None])[-1]
def _bounded_int(value, default, minimum, maximum):
    result = default if value in (None, "") else int(value)
    if not minimum <= result <= maximum: raise ValueError("pagination value is out of range")
    return result
def _date(value): return value if isinstance(value, date) else date.fromisoformat(str(value))
