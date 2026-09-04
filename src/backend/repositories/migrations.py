from __future__ import annotations

from pathlib import Path


class MigrationRunner:
    def __init__(self, connection_factory, migrations_path: Path) -> None:
        self._connection_factory = connection_factory
        self._migrations_path = migrations_path

    def apply(self) -> None:
        migration_files = sorted(self._migrations_path.glob("*.sql"))
        if not migration_files:
            return

        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cursor.execute("SELECT version FROM schema_migrations")
                applied = {row[0] for row in cursor.fetchall()}

                for migration_file in migration_files:
                    version = migration_file.stem
                    if version in applied:
                        continue
                    cursor.execute(migration_file.read_text(encoding="utf-8"))
                    cursor.execute(
                        "INSERT INTO schema_migrations (version) VALUES (%s)",
                        (version,),
                    )
            connection.commit()
