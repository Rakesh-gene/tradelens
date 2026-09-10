from __future__ import annotations

from pathlib import Path

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
