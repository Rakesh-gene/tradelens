from __future__ import annotations

from pathlib import Path
from datetime import date
from hashlib import sha1
import json

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - optional at test time
    psycopg = None

from repositories.migrations import MigrationRunner


class PostgresEquityRepository:
    """PostgreSQL persistence for the NSE equity master list."""

    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            self._apply_migrations()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def _apply_migrations(self) -> None:
        migrations_path = Path(__file__).resolve().parents[1] / "migrations"
        MigrationRunner(self._connect, migrations_path).apply()

    def upsert_equities(self, equities: list[dict[str, object]]) -> int:
        if not equities:
            return 0
        statement = """
            INSERT INTO nse_equities (
                symbol, company_name, series, listed_on, paid_up_value,
                market_lot, isin, face_value
            ) VALUES (
                %(symbol)s, %(company_name)s, %(series)s, %(listed_on)s,
                %(paid_up_value)s, %(market_lot)s, %(isin)s, %(face_value)s
            )
            ON CONFLICT (isin) DO UPDATE SET
                symbol = EXCLUDED.symbol,
                company_name = EXCLUDED.company_name,
                series = EXCLUDED.series,
                listed_on = EXCLUDED.listed_on,
                paid_up_value = EXCLUDED.paid_up_value,
                market_lot = EXCLUDED.market_lot,
                face_value = EXCLUDED.face_value,
                updated_at = NOW()
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(statement, equities)
            connection.commit()
        return len(equities)

    def list_classifications_due(self, limit: int | None, stale_days: int) -> list[dict[str, object]]:
        statement = """
            SELECT equity.isin, equity.symbol, equity.listed_on
            FROM nse_equities equity
            LEFT JOIN equity_classification_refresh_state state ON state.isin = equity.isin
            WHERE equity.series = 'EQ' AND (
                state.isin IS NULL OR state.status IN ('MISSING', 'FAILED', 'STALE')
                OR state.last_succeeded_at < NOW() - (%s * INTERVAL '1 day')
            )
            ORDER BY (state.isin IS NULL) DESC, equity.listed_on DESC, state.last_succeeded_at NULLS FIRST,
                     equity.symbol
        """
        parameters: list[object] = [stale_days]
        if limit is not None:
            statement += " LIMIT %s"
            parameters.append(limit)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in rows]

    def upsert_classification(self, classification: dict[str, object], effective_from: date) -> bool:
        macro_code = _taxonomy_code("MACRO", str(classification["macro_sector"]))
        sector_code = _taxonomy_code("SECTOR", str(classification["sector"]), macro_code)
        industry_code = _taxonomy_code("INDUSTRY", str(classification["industry"]), sector_code)
        basic_code = _taxonomy_code("BASIC", str(classification["basic_industry"]), industry_code)
        payload = json.dumps(classification.get("source_payload") or {}, default=str, sort_keys=True)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT source_checksum FROM security_industry_memberships WHERE isin = %s AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1", (classification["isin"],))
                current = cursor.fetchone()
                changed = current is None or current[0] != classification["source_checksum"]
                cursor.execute("INSERT INTO market_macro_sectors (code, name) VALUES (%s, %s) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, updated_at = NOW()", (macro_code, classification["macro_sector"]))
                cursor.execute("INSERT INTO market_sectors (code, name, taxonomy_source, macro_sector_code) VALUES (%s, %s, 'NSE', %s) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, taxonomy_source = EXCLUDED.taxonomy_source, macro_sector_code = EXCLUDED.macro_sector_code, updated_at = NOW()", (sector_code, classification["sector"], macro_code))
                cursor.execute("INSERT INTO market_industries (code, sector_code, name) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET sector_code = EXCLUDED.sector_code, name = EXCLUDED.name, updated_at = NOW()", (industry_code, sector_code, classification["industry"]))
                cursor.execute("INSERT INTO market_basic_industries (code, industry_code, name) VALUES (%s, %s, %s) ON CONFLICT (code) DO UPDATE SET industry_code = EXCLUDED.industry_code, name = EXCLUDED.name, updated_at = NOW()", (basic_code, industry_code, classification["basic_industry"]))
                if changed:
                    cursor.execute("UPDATE security_industry_memberships SET effective_to = %s - 1 WHERE isin = %s AND effective_to IS NULL AND effective_from < %s", (effective_from, classification["isin"], effective_from))
                    cursor.execute("UPDATE security_sector_memberships SET effective_to = %s - 1 WHERE isin = %s AND effective_to IS NULL AND effective_from < %s", (effective_from, classification["isin"], effective_from))
                    cursor.execute("DELETE FROM security_industry_memberships WHERE isin = %s AND effective_from = %s", (classification["isin"], effective_from))
                    cursor.execute("DELETE FROM security_sector_memberships WHERE isin = %s AND effective_from = %s", (classification["isin"], effective_from))
                    cursor.execute("INSERT INTO security_industry_memberships (isin, basic_industry_code, effective_from, source_checksum, source_payload) VALUES (%s, %s, %s, %s, %s::jsonb)", (classification["isin"], basic_code, effective_from, classification["source_checksum"], payload))
                    cursor.execute("INSERT INTO security_sector_memberships (isin, sector_code, effective_from, source_name, source_checksum) VALUES (%s, %s, %s, 'NSE', %s)", (classification["isin"], sector_code, effective_from, classification["source_checksum"]))
                cursor.execute("INSERT INTO equity_classification_refresh_state (isin, status, last_attempted_at, last_succeeded_at) VALUES (%s, 'CURRENT', NOW(), NOW()) ON CONFLICT (isin) DO UPDATE SET status = 'CURRENT', last_attempted_at = NOW(), last_succeeded_at = NOW(), retry_count = 0, last_error = NULL, updated_at = NOW()", (classification["isin"],))
            connection.commit()
        return changed

    def mark_classification_failed(self, isin: str, error: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO equity_classification_refresh_state (isin, status, last_attempted_at, retry_count, last_error) VALUES (%s, 'FAILED', NOW(), 1, %s) ON CONFLICT (isin) DO UPDATE SET status = 'FAILED', last_attempted_at = NOW(), retry_count = equity_classification_refresh_state.retry_count + 1, last_error = EXCLUDED.last_error, updated_at = NOW()", (isin, error))
            connection.commit()

    def mark_classification_missing(self, isin: str, reason: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO equity_classification_refresh_state (isin, status, last_attempted_at, retry_count, last_error) VALUES (%s, 'MISSING', NOW(), 0, %s) ON CONFLICT (isin) DO UPDATE SET status = 'MISSING', last_attempted_at = NOW(), retry_count = 0, last_error = EXCLUDED.last_error, updated_at = NOW()", (isin, reason))
            connection.commit()


def _taxonomy_code(level: str, name: str, parent: str = "") -> str:
    material = f"{parent}|{' '.join(name.upper().split())}"
    return f"NSE-{level}-{sha1(material.encode('utf-8')).hexdigest()[:12].upper()}"
