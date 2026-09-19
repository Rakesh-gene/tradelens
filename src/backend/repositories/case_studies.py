"""Persistence for immutable, published case-study evidence."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from pattern_engine.models import serialize_value
from pattern_engine.enums import SETUP_PATTERN_TYPES


class InMemoryCaseStudyRepository:
    def __init__(self, cases=(), source_entries=(), bars=None, source_runs=None, securities=None):
        self.cases = [dict(row) for row in cases]
        self.runs = {}
        self.source_entries = [dict(row) for row in source_entries]
        self.source_runs = dict(source_runs or {})
        self.bars = bars or {}
        self.securities = dict(securities or {})
        self.items = {}
    def list_cases(self, filters, limit, offset):
        rows = [row for row in self.cases if row.get("pattern_type") in SETUP_PATTERN_TYPES and _matches(row, filters)]
        sort_fields = {"detectionDate": "detection_date", "entryDate": "entry_date", "netPnl": "net_pnl", "netReturnPct": "net_return_pct", "netRMultiple": "net_r_multiple", "setupScore": "setup_score"}
        field = sort_fields.get(filters.get("sort"), "detection_date")
        rows.sort(key=lambda row: (row.get(field) is not None, row.get(field), str(row.get("id"))), reverse=filters.get("directionOrder", "desc") == "desc")
        return [dict(row) for row in rows[offset:offset + limit + 1]]
    def get_case(self, case_id): return next((dict(row) for row in self.cases if str(row["id"]) == case_id), None)
    def list_review_cases(self, status, limit, offset):
        rows = [dict(row) for row in self.cases if row.get("review_status", "PENDING") == status]
        rows.sort(key=lambda row: (row.get("created_at", ""), str(row.get("id"))), reverse=True)
        return rows[offset:offset + limit + 1]
    def set_review_status(self, case_id, status):
        row = next((row for row in self.cases if str(row["id"]) == str(case_id)), None)
        if row is None: return None
        row["review_status"] = status
        return dict(row)
    def delete_case(self, case_id):
        for index, row in enumerate(self.cases):
            if str(row["id"]) == str(case_id):
                self.cases.pop(index)
                return {"id": str(case_id)}
        return None
    def facets(self):
        return {key: sorted({str(row[key]) for row in self.cases if row.get(key) is not None}) for key in ("isin", "sector_code", "pattern_class", "pattern_type", "variant", "timeframe", "direction", "exit_reason", "market_regime")}
    def create_run(self, values):
        run_id = str(uuid4()); self.runs[run_id] = {"id": run_id, "status": "PENDING", "created_at": datetime.now(timezone.utc), **dict(values)}; return run_id
    def update_run(self, run_id, **values): self.runs[run_id].update(values)
    def get_run(self, run_id): return dict(self.runs[run_id]) if run_id in self.runs else None
    def latest_run_id(self, requested_by):
        rows = [row for row in self.runs.values() if str(row.get("requested_by")) == str(requested_by)]
        return str(max(rows, key=lambda row: row["created_at"])["id"]) if rows else None
    def get_source_run(self, run_id):
        if run_id in self.source_runs: return dict(self.source_runs[run_id])
        return {"id": run_id, "status": "COMPLETED"} if self.list_source_entries(run_id) else None
    def resolve_stock_build_context(self, isin, adjustment_version):
        rows = self.bars.get(isin, ())
        if not rows and isin not in self.securities: return None
        security = dict(self.securities.get(isin) or {"isin": isin, "symbol": isin, "company_name": isin})
        dated = [row["trading_date"] for row in rows if row.get("trading_date") is not None]
        return {**security, "data_as_of": max(dated) if dated else date.today()}
    def list_case_ids(self, run_id):
        return [str(row["id"]) for row in self.cases if str(row.get("case_study_run_id")) == str(run_id)]
    def add_case(self, case):
        item = dict(case)
        duplicate = next((row for row in self.cases if row.get("case_study_run_id") == item.get("case_study_run_id") and row.get("replay_fingerprint") == item.get("replay_fingerprint") and row.get("selection_reason") == item.get("selection_reason")), None)
        if duplicate: return duplicate["id"]
        item.update(item.get("trade") or {})
        item["direction"] = case["direction"]
        item["fixed_horizon_outcomes"] = item.get("fixed_horizon_outcomes", {})
        item["policy_inputs"] = (item.get("trade") or {}).get("policy_inputs", {})
        item.setdefault("id", str(uuid5(NAMESPACE_URL, f"tradelens:{item.get('case_study_run_id')}:{item.get('replay_fingerprint')}:{item.get('selection_reason')}"))); self.cases.append(item); return item["id"]
    def list_source_entries(self, run_id): return [dict(row) for row in self.source_entries if str(row.get("backtest_run_id")) == str(run_id)]
    def load_trade_bars(self, isin, signal_date, adjustment_version, limit): return [dict(row) for row in self.bars.get(isin, ()) if str(row["trading_date"]) > str(signal_date)][:limit]
    def record_item(self, run_id, isin, status, cases_recorded=0, error_message=None): self.items[(run_id, isin)] = {"isin": isin, "status": status, "cases_recorded": cases_recorded, "error_message": error_message}
    def list_run_items(self, run_id, limit, offset): return [dict(row) for (item_run, _), row in sorted(self.items.items()) if item_run == run_id][offset:offset + limit]
    def load_chart_bars(self, isin, start, end, adjustment_version): return [dict(row) for row in self.bars.get(isin, ()) if start <= row["trading_date"] <= end]
    def recover_interrupted_runs(self):
        for row in self.runs.values():
            if row["status"] in {"PENDING", "RUNNING"}: row.update(status="FAILED", failure_summary={"pipeline": "Build interrupted before completion"})


class PostgresCaseStudyRepository:
    """Small SQL repository; service owns browser contract and validation."""
    def __init__(self, dsn):
        import psycopg
        self._dsn, self._psycopg = dsn, psycopg
    def _fetch(self, sql, values=()):
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, values); columns = [column.name for column in cursor.description]; return [dict(zip(columns, row)) for row in cursor.fetchall()]
    def create_run(self, values):
        run_id = str(uuid4())
        json_fields = {"universe", "requested_pattern_types", "requested_timeframes", "point_in_time_policy", "survivorship_bias_policy", "failure_summary", "trade_policy_inputs", "selection_policy_inputs"}
        columns = tuple(values)
        placeholders = [f"%({name})s" + ("::jsonb" if name in json_fields else "") for name in columns]
        parameters = {"id": run_id, **{name: json.dumps(serialize_value(value)) if name in json_fields else value for name, value in values.items()}}
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"INSERT INTO case_study_runs (id, status, {', '.join(columns)}) VALUES (%(id)s, 'PENDING', {', '.join(placeholders)})", parameters)
            connection.commit()
        return run_id
    def update_run(self, run_id, **values):
        json_fields = {"failure_summary"}
        parameters = {"id": run_id, **{name: json.dumps(serialize_value(value)) if name in json_fields else value for name, value in values.items()}}
        assignments = [f"{name} = %({name})s" + ("::jsonb" if name in json_fields else "") for name in values]
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE case_study_runs SET {', '.join(assignments)}, updated_at = NOW() WHERE id = %(id)s", parameters)
                if cursor.rowcount != 1: raise LookupError("Case-study run not found")
            connection.commit()
    def get_run(self, run_id):
        rows = self._fetch("SELECT * FROM case_study_runs WHERE id = %s", (run_id,)); return rows[0] if rows else None
    def latest_run_id(self, requested_by):
        rows = self._fetch("SELECT id FROM case_study_runs WHERE requested_by = %s ORDER BY created_at DESC, id DESC LIMIT 1", (requested_by,))
        return str(rows[0]["id"]) if rows else None
    def get_source_run(self, run_id):
        rows = self._fetch("SELECT id, status, engine_version, configuration_version, feature_version, adjustment_version FROM backtest_runs WHERE id = %s", (run_id,)); return rows[0] if rows else None
    def resolve_stock_build_context(self, isin, adjustment_version):
        rows = self._fetch(
            """SELECT equity.isin, equity.symbol, equity.company_name,
                      MAX(bar.trading_date) AS data_as_of
               FROM nse_equities equity
               JOIN adjusted_daily_bars bar ON bar.isin = equity.isin
                AND (bar.adjustment_version = %s OR bar.adjustment_version LIKE %s::text || ':%%')
               WHERE equity.isin = %s AND equity.series = 'EQ'
               GROUP BY equity.isin, equity.symbol, equity.company_name""",
            (adjustment_version, adjustment_version, isin),
        )
        return rows[0] if rows else None
    def list_case_ids(self, run_id):
        return [str(row["id"]) for row in self._fetch(
            "SELECT id FROM case_studies WHERE case_study_run_id = %s ORDER BY detection_date, id",
            (run_id,),
        )]
    def recover_interrupted_runs(self):
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE case_study_runs SET status = 'FAILED', failure_summary = '{\"pipeline\": \"Build interrupted before completion\"}'::jsonb, completed_at = NOW(), updated_at = NOW() WHERE status IN ('PENDING', 'RUNNING')")
            connection.commit()
    def list_cases(self, filters, limit, offset):
        clauses, values = ["case_study.review_status = 'REVIEWED'", "case_study.pattern_type = ANY(%s)"], [list(SETUP_PATTERN_TYPES)]
        columns = {"isin": "case_study.isin", "sector": "case_study.sector_code", "patternClass": "case_study.pattern_class", "patternType": "case_study.pattern_type", "variant": "case_study.variant", "timeframe": "case_study.timeframe", "direction": "case_study.direction", "exitReason": "case_study.exit_reason", "marketRegime": "case_study.market_regime"}
        for name, column in columns.items():
            if filters.get(name): clauses.append(f"{column} = %s"); values.append(filters[name])
        if filters.get("q"):
            clauses.append("(case_study.historical_symbol ILIKE %s OR case_study.historical_company_name ILIKE %s OR case_study.isin ILIKE %s)")
            term = f"%{filters['q']}%"; values.extend((term, term, term))
        if filters.get("fromDate"): clauses.append("case_study.detection_date >= %s"); values.append(filters["fromDate"])
        if filters.get("toDate"): clauses.append("case_study.detection_date <= %s"); values.append(filters["toDate"])
        if filters.get("minSetupScore") is not None: clauses.append("case_study.setup_score >= %s"); values.append(filters["minSetupScore"])
        outcome = filters.get("outcome")
        if outcome == "PROFITABLE": clauses.append("result.net_pnl > 0")
        elif outcome == "LOSING": clauses.append("result.net_pnl < 0")
        elif outcome == "SKIPPED": clauses.append("case_study.completeness->>'status' = 'SKIPPED'")
        elif outcome == "AMBIGUOUS": clauses.append("(case_study.ambiguity->>'ambiguous')::boolean IS TRUE")
        elif outcome == "INCOMPLETE": clauses.append("case_study.completeness->>'status' = 'INCOMPLETE'")
        values.extend([limit + 1, offset])
        sort_columns = {"detectionDate": "case_study.detection_date", "entryDate": "case_study.entry_date", "netPnl": "result.net_pnl", "netReturnPct": "result.net_return_pct", "netRMultiple": "result.net_r_multiple", "setupScore": "case_study.setup_score"}
        sort_column = sort_columns.get(filters.get("sort"), "case_study.detection_date")
        direction = "ASC" if filters.get("directionOrder") == "asc" else "DESC"
        return self._fetch(f"SELECT case_study.*, result.quantity, result.fixed_horizon_outcomes FROM case_studies case_study LEFT JOIN case_study_trade_results result ON result.case_study_id = case_study.id WHERE {' AND '.join(clauses)} ORDER BY {sort_column} {direction} NULLS LAST, case_study.id {direction} LIMIT %s OFFSET %s", values)
    def get_case(self, case_id):
        rows = self._fetch("""SELECT case_study.*, result.quantity, result.deployed_capital,
                    result.initial_risk, result.gross_pnl, result.costs, result.net_pnl,
                    result.gross_return_pct, result.net_return_pct, result.gross_r_multiple,
                    result.net_r_multiple, result.mfe_pct, result.mae_pct,
                    result.fixed_horizon_outcomes, result.completeness AS horizon_completeness,
                    result.target_touch_date, result.stop_touch_date, result.same_session_policy,
                    result.duration_sessions, result.policy_inputs,
                    run.requested_to_date AS study_data_as_of
               FROM case_studies case_study
               JOIN case_study_runs run ON run.id = case_study.case_study_run_id
               LEFT JOIN case_study_trade_results result ON result.case_study_id = case_study.id
               WHERE case_study.id = %s""", (case_id,)); return rows[0] if rows else None
    def list_review_cases(self, status, limit, offset):
        return self._fetch("""SELECT case_study.*, result.quantity, result.net_pnl,
                    result.net_return_pct, result.net_r_multiple, result.fixed_horizon_outcomes,
                    run.requested_to_date AS study_data_as_of
               FROM case_studies case_study
               JOIN case_study_runs run ON run.id = case_study.case_study_run_id
               LEFT JOIN case_study_trade_results result ON result.case_study_id = case_study.id
               WHERE case_study.review_status = %s
               ORDER BY case_study.created_at DESC, case_study.id DESC
               LIMIT %s OFFSET %s""", (status, limit + 1, offset))
    def set_review_status(self, case_id, status):
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE case_studies SET review_status = %s WHERE id = %s RETURNING id", (status, case_id))
                row = cursor.fetchone()
            connection.commit()
        return self.get_case(str(row[0])) if row else None
    def delete_case(self, case_id):
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM case_study_trade_results WHERE case_study_id = %s", (case_id,))
                cursor.execute("DELETE FROM case_studies WHERE id = %s RETURNING id, case_study_run_id", (case_id,))
                row = cursor.fetchone()
                if row is not None:
                    cursor.execute("UPDATE case_study_runs SET cases_recorded = GREATEST(cases_recorded - 1, 0), updated_at = NOW() WHERE id = %s", (row[1],))
            connection.commit()
        return {"id": str(row[0])} if row else None
    def facets(self):
        rows = self._fetch("SELECT array_remove(array_agg(DISTINCT isin), NULL) AS stocks, array_remove(array_agg(DISTINCT pattern_class), NULL) AS pattern_classes, array_remove(array_agg(DISTINCT pattern_type), NULL) AS pattern_types, array_remove(array_agg(DISTINCT variant), NULL) AS variants, array_remove(array_agg(DISTINCT timeframe), NULL) AS timeframes, array_remove(array_agg(DISTINCT direction), NULL) AS directions, array_remove(array_agg(DISTINCT exit_reason), NULL) AS exit_reasons, array_remove(array_agg(DISTINCT sector_code), NULL) AS sectors, array_remove(array_agg(DISTINCT market_regime), NULL) AS market_regimes FROM case_studies")
        return rows[0] if rows else {}
    def list_source_entries(self, run_id):
        return self._fetch("""SELECT entry.*, equity.symbol AS historical_symbol,
                    equity.company_name AS historical_company_name,
                    run.engine_version, run.configuration_version,
                    run.feature_version, run.adjustment_version,
                    outcome.returns_by_horizon, outcome.mfe_by_horizon,
                    outcome.mae_by_horizon, outcome.completeness AS horizon_completeness
               FROM backtest_entries entry
               JOIN backtest_runs run ON run.id = entry.backtest_run_id
               JOIN nse_equities equity ON equity.isin = entry.isin
               LEFT JOIN backtest_outcomes outcome ON outcome.backtest_entry_id = entry.id
               WHERE entry.backtest_run_id = %s
               ORDER BY entry.isin, entry.entry_date, entry.id""", (run_id,))
    def load_trade_bars(self, isin, signal_date, adjustment_version, limit):
        return self._fetch("""WITH selected_version AS (
                    SELECT adjustment_version FROM adjusted_daily_bars
                    WHERE isin = %s AND (adjustment_version = %s OR adjustment_version LIKE %s::text || ':%%')
                    GROUP BY adjustment_version
                    ORDER BY CASE WHEN adjustment_version = %s THEN 0 ELSE 1 END, MAX(generated_at) DESC LIMIT 1)
                SELECT trading_date, open_price, high_price, low_price, close_price
                FROM adjusted_daily_bars WHERE isin = %s AND trading_date > %s
                  AND adjustment_version = (SELECT adjustment_version FROM selected_version)
                ORDER BY trading_date LIMIT %s""", (isin, adjustment_version, adjustment_version, adjustment_version, isin, signal_date, limit))
    def record_item(self, run_id, isin, status, cases_recorded=0, error_message=None):
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor: cursor.execute("INSERT INTO case_study_run_items (case_study_run_id, isin, status, cases_recorded, error_message) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (case_study_run_id, isin) DO UPDATE SET status = EXCLUDED.status, cases_recorded = EXCLUDED.cases_recorded, error_message = EXCLUDED.error_message, updated_at = NOW()", (run_id, isin, status, cases_recorded, error_message))
            connection.commit()
    def list_run_items(self, run_id, limit, offset):
        return self._fetch("SELECT isin, status, cases_recorded, error_message, updated_at FROM case_study_run_items WHERE case_study_run_id = %s ORDER BY isin LIMIT %s OFFSET %s", (run_id, limit, offset))
    def add_case(self, case):
        values, trade = dict(case), dict(case["trade"])
        case_id = str(uuid5(NAMESPACE_URL, f"tradelens:{values['case_study_run_id']}:{values['replay_fingerprint']}:{values['selection_reason']}"))
        json_value = lambda value: json.dumps(serialize_value(value), sort_keys=True)
        with self._psycopg.connect(self._dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO case_studies (
                    id, case_study_run_id, source_backtest_run_id, source_backtest_entry_id,
                    replay_fingerprint, isin, historical_symbol, historical_company_name,
                    pattern_class, pattern_type, variant, pattern_group, direction, timeframe, lifecycle_state,
                    pattern_start_date, detection_date, trigger_date, confirmation_date,
                    entry_date, exit_date, entry_price, stop_price, target_price, exit_price,
                    pivot_price, support_price, invalidation_price, measurements, supporting_evidence,
                    context, exit_reason, completeness, ambiguity, lineage,
                    selection_policy_version, selection_reason, sector_code, setup_score,
                    market_regime, sector_context)
                VALUES (
                    %(id)s, %(case_study_run_id)s, %(source_backtest_run_id)s,
                    %(source_backtest_entry_id)s, %(replay_fingerprint)s, %(isin)s,
                    %(historical_symbol)s, %(historical_company_name)s, %(pattern_class)s,
                    %(pattern_type)s, %(variant)s, %(pattern_group)s, %(direction)s, %(timeframe)s,
                    %(lifecycle_state)s, %(pattern_start_date)s, %(detection_date)s,
                    %(trigger_date)s, %(confirmation_date)s, %(entry_date)s, %(exit_date)s,
                    %(entry_price)s, %(stop_price)s, %(target_price)s, %(exit_price)s,
                    %(pivot_price)s, %(support_price)s, %(invalidation_price)s, %(measurements)s::jsonb,
                    %(supporting_evidence)s::jsonb, %(context)s::jsonb, %(exit_reason)s,
                    %(completeness)s::jsonb, %(ambiguity)s::jsonb, %(lineage)s::jsonb,
                    %(selection_policy_version)s, %(selection_reason)s, %(sector_code)s,
                    %(setup_score)s, %(market_regime)s, %(sector_context)s)
                ON CONFLICT (case_study_run_id, replay_fingerprint, selection_reason) DO NOTHING
                RETURNING id""", {
                    **{name: values.get(name) for name in (
                        "case_study_run_id", "source_backtest_run_id", "source_backtest_entry_id",
                        "replay_fingerprint", "isin", "historical_symbol", "historical_company_name",
                        "pattern_class", "pattern_type", "variant", "pattern_group", "direction", "timeframe",
                        "lifecycle_state", "pattern_start_date", "detection_date", "trigger_date",
                        "confirmation_date", "entry_date", "exit_date", "entry_price", "stop_price",
                        "target_price", "exit_price", "pivot_price", "support_price", "invalidation_price",
                        "exit_reason", "selection_policy_version", "selection_reason", "sector_code",
                        "setup_score", "market_regime", "sector_context")},
                    "id": case_id,
                    "measurements": json_value(values.get("measurements", {})),
                    "supporting_evidence": json_value(values.get("supporting_evidence", {})),
                    "context": json_value(values.get("context", {})),
                    "completeness": json_value(values.get("completeness", {})),
                    "ambiguity": json_value(values.get("ambiguity", {})),
                    "lineage": json_value(values.get("lineage", {})),
                })
                inserted = cursor.fetchone()
                if inserted is None:
                    cursor.execute("SELECT id FROM case_studies WHERE case_study_run_id = %s AND replay_fingerprint = %s AND selection_reason = %s", (values["case_study_run_id"], values["replay_fingerprint"], values["selection_reason"]))
                    existing = cursor.fetchone()
                    connection.commit()
                    return str(existing[0]) if existing else None
                cursor.execute("""INSERT INTO case_study_trade_results (
                    case_study_id, quantity, deployed_capital, initial_risk, gross_pnl, costs,
                    net_pnl, gross_return_pct, net_return_pct, gross_r_multiple, net_r_multiple,
                    mfe_pct, mae_pct, fixed_horizon_outcomes, completeness, target_touch_date,
                    stop_touch_date, same_session_policy, duration_sessions, policy_inputs)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s::jsonb)""", (
                    case_id, trade.get("quantity"), trade.get("deployed_capital"), trade.get("initial_risk"),
                    trade.get("gross_pnl"), trade.get("costs"), trade.get("net_pnl"),
                    trade.get("gross_return_pct"), trade.get("net_return_pct"),
                    trade.get("gross_r_multiple"), trade.get("net_r_multiple"), trade.get("mfe_pct"),
                    trade.get("mae_pct"), json_value(values.get("fixed_horizon_outcomes", {})),
                    json_value(values.get("horizon_completeness", {})), trade.get("target_touch_date"),
                    trade.get("stop_touch_date"), trade["same_session_policy"],
                    trade.get("duration_sessions"), json_value(trade.get("policy_inputs", {})),
                ))
            connection.commit()
        return case_id
    def load_chart_bars(self, isin, start, end, adjustment_version):
        return self._fetch("""WITH selected_version AS (
                    SELECT adjustment_version FROM adjusted_daily_bars
                    WHERE isin = %s AND (adjustment_version = %s OR adjustment_version LIKE %s::text || ':%%')
                    GROUP BY adjustment_version
                    ORDER BY CASE WHEN adjustment_version = %s THEN 0 ELSE 1 END, MAX(generated_at) DESC LIMIT 1)
                SELECT trading_date, open_price, high_price, low_price, close_price, volume
                FROM adjusted_daily_bars WHERE isin = %s AND trading_date BETWEEN %s AND %s
                  AND adjustment_version = (SELECT adjustment_version FROM selected_version)
                ORDER BY trading_date""", (isin, adjustment_version, adjustment_version, adjustment_version, isin, start, end))


def _matches(row, filters):
    if row.get("review_status") not in (None, "REVIEWED"): return False
    pairs = {"isin": "isin", "sector": "sector_code", "patternClass": "pattern_class", "patternType": "pattern_type", "variant": "variant", "timeframe": "timeframe", "direction": "direction", "exitReason": "exit_reason", "marketRegime": "market_regime"}
    if not all(not filters.get(query) or str(row.get(field)) == str(filters[query]) for query, field in pairs.items()): return False
    query = str(filters.get("q") or "").casefold()
    if query and not any(query in str(row.get(field) or "").casefold() for field in ("historical_symbol", "historical_company_name", "isin")): return False
    if filters.get("fromDate") and row.get("detection_date") < filters["fromDate"]: return False
    if filters.get("toDate") and row.get("detection_date") > filters["toDate"]: return False
    if filters.get("minSetupScore") is not None and (row.get("setup_score") is None or float(row["setup_score"]) < float(filters["minSetupScore"])): return False
    outcome = filters.get("outcome")
    if outcome == "PROFITABLE" and not (row.get("net_pnl") is not None and row["net_pnl"] > 0): return False
    if outcome == "LOSING" and not (row.get("net_pnl") is not None and row["net_pnl"] < 0): return False
    if outcome in {"SKIPPED", "INCOMPLETE"} and (row.get("completeness") or {}).get("status") != outcome: return False
    if outcome == "AMBIGUOUS" and not (row.get("ambiguity") or {}).get("ambiguous"): return False
    return True
