"""Atomic PostgreSQL and in-memory persistence for pattern lifecycle state."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import json
from pathlib import Path
from uuid import uuid4

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover
    psycopg = None

from pattern_engine.models import serialize_value
from repositories.migrations import MigrationRunner


class PatternConcurrencyError(RuntimeError):
    pass


class PostgresPatternRepository:
    def __init__(self, dsn: str, *, apply_migrations: bool = True) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for PostgreSQL support")
        self._dsn = dsn
        if apply_migrations:
            MigrationRunner(
                self._connect, Path(__file__).resolve().parents[1] / "migrations"
            ).apply()

    def _connect(self):
        return psycopg.connect(self._dsn)

    def load_active_patterns(self, isin, pattern_type=None):
        statement = """
            SELECT * FROM pattern_instances
            WHERE isin = %s AND terminal_date IS NULL
              AND (%s::text IS NULL OR pattern_type = %s)
            ORDER BY last_updated_date DESC, id
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (isin, pattern_type, pattern_type))
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    def create_pattern(self, values, event):
        pattern_id, event_id = str(uuid4()), str(uuid4())
        columns = tuple(values.keys())
        statement = f"""
            INSERT INTO pattern_instances (id, {', '.join(columns)})
            VALUES (%(id)s, {', '.join(f'%({name})s' + ('::jsonb' if name in {'measurements', 'supporting_patterns'} else '') for name in columns)})
            RETURNING *
        """
        parameters = {"id": pattern_id, **_json_parameters(values)}
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                row = cursor.fetchone()
                columns_out = [column.name for column in cursor.description]
                self._insert_event(cursor, event_id, pattern_id, event)
            connection.commit()
        return dict(row) if isinstance(row, Mapping) else dict(zip(columns_out, row))

    def update_pattern(self, pattern_id, expected_state_version, values, event):
        assignments = [
            f"{name} = %({name})s" + ("::jsonb" if name in {"measurements", "supporting_patterns"} else "")
            for name in values if name not in {"id", "state_version", "created_at", "updated_at"}
        ]
        statement = f"""
            UPDATE pattern_instances
            SET {', '.join(assignments)}, state_version = %(new_state_version)s, updated_at = NOW()
            WHERE id = %(id)s AND state_version = %(expected_state_version)s
              AND terminal_date IS NULL
            RETURNING *
        """
        parameters = {
            "id": pattern_id, "expected_state_version": expected_state_version,
            "new_state_version": expected_state_version + (1 if event is not None else 0),
            **_json_parameters(values),
        }
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                row = cursor.fetchone()
                if row is None:
                    raise PatternConcurrencyError(f"Pattern {pattern_id} changed concurrently or is terminal")
                columns = [column.name for column in cursor.description]
                if event is not None:
                    self._insert_event(cursor, str(uuid4()), pattern_id, event)
            connection.commit()
        return dict(row) if isinstance(row, Mapping) else dict(zip(columns, row))

    def load_events(self, pattern_id):
        statement = """
            SELECT * FROM pattern_events WHERE pattern_instance_id = %s
            ORDER BY state_version, recorded_at, id
        """
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (pattern_id,))
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    @contextmanager
    def security_transaction(self, isin):
        """Yield a repository whose writes share one security-scoped transaction."""

        connection = self._connect()
        try:
            yield _PostgresPatternTransaction(connection, isin)
            connection.commit()
        except Exception:
            rollback = getattr(connection, "rollback", None)
            if rollback is not None:
                rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if close is not None:
                close()

    @staticmethod
    def _insert_event(cursor, event_id, pattern_id, event):
        cursor.execute(
            """
            INSERT INTO pattern_events (
                id, pattern_instance_id, event_type, state_version,
                previous_state, new_state, previous_values, new_values, effective_date
            ) VALUES (
                %(id)s, %(pattern_instance_id)s, %(event_type)s, %(state_version)s,
                %(previous_state)s, %(new_state)s, %(previous_values)s::jsonb,
                %(new_values)s::jsonb, %(effective_date)s
            )
            """,
            {
                "id": event_id, "pattern_instance_id": pattern_id, **event,
                "previous_values": json.dumps(serialize_value(event["previous_values"]), sort_keys=True),
                "new_values": json.dumps(serialize_value(event["new_values"]), sort_keys=True),
            },
        )


class InMemoryPatternRepository:
    def __init__(self) -> None:
        self.instances: dict[str, dict[str, object]] = {}
        self.events: list[dict[str, object]] = []

    def load_active_patterns(self, isin, pattern_type=None):
        return [
            dict(value) for value in self.instances.values()
            if value["isin"] == isin and value.get("terminal_date") is None
            and (pattern_type is None or value["pattern_type"] == pattern_type)
        ]

    def create_pattern(self, values, event):
        pattern_id = str(uuid4())
        instance = {"id": pattern_id, **dict(values)}
        self.instances[pattern_id] = instance
        self.events.append({"id": str(uuid4()), "pattern_instance_id": pattern_id, **dict(event)})
        return dict(instance)

    def update_pattern(self, pattern_id, expected_state_version, values, event):
        current = self.instances.get(pattern_id)
        if current is None or current["state_version"] != expected_state_version or current.get("terminal_date") is not None:
            raise PatternConcurrencyError(f"Pattern {pattern_id} changed concurrently or is terminal")
        updated = {
            **current, **dict(values),
            "state_version": expected_state_version + (1 if event is not None else 0),
        }
        self.instances[pattern_id] = updated
        if event is not None:
            self.events.append({"id": str(uuid4()), "pattern_instance_id": pattern_id, **dict(event)})
        return dict(updated)

    def load_events(self, pattern_id):
        return [
            dict(event) for event in self.events
            if event["pattern_instance_id"] == pattern_id
        ]

    @contextmanager
    def security_transaction(self, isin):
        instances = {key: dict(value) for key, value in self.instances.items()}
        events = [dict(value) for value in self.events]
        try:
            yield _InMemorySecurityTransaction(self, isin)
        except Exception:
            self.instances = instances
            self.events = events
            raise


class _InMemorySecurityTransaction:
    def __init__(self, repository, isin):
        self._repository = repository
        self._isin = isin

    def load_active_patterns(self, isin, pattern_type=None):
        self._require_isin(isin)
        return self._repository.load_active_patterns(isin, pattern_type)

    def create_pattern(self, values, event):
        self._require_isin(values.get("isin"))
        return self._repository.create_pattern(values, event)

    def update_pattern(self, pattern_id, expected_state_version, values, event):
        current = self._repository.instances.get(pattern_id)
        self._require_isin(current.get("isin") if current else None)
        return self._repository.update_pattern(pattern_id, expected_state_version, values, event)

    def load_events(self, pattern_id):
        return self._repository.load_events(pattern_id)

    def _require_isin(self, isin):
        if isin != self._isin:
            raise ValueError("Pattern transaction cannot cross security boundaries")


class _PostgresPatternTransaction:
    def __init__(self, connection, isin):
        self._connection = connection
        self._isin = isin

    def load_active_patterns(self, isin, pattern_type=None):
        self._require_isin(isin)
        statement = """
            SELECT * FROM pattern_instances
            WHERE isin = %s AND terminal_date IS NULL
              AND (%s::text IS NULL OR pattern_type = %s)
            ORDER BY last_updated_date DESC, id
        """
        with self._connection.cursor() as cursor:
            cursor.execute(statement, (isin, pattern_type, pattern_type))
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    def create_pattern(self, values, event):
        self._require_isin(values.get("isin"))
        pattern_id, event_id = str(uuid4()), str(uuid4())
        columns = tuple(values.keys())
        statement = f"""
            INSERT INTO pattern_instances (id, {', '.join(columns)})
            VALUES (%(id)s, {', '.join(f'%({name})s' + ('::jsonb' if name in {'measurements', 'supporting_patterns'} else '') for name in columns)})
            RETURNING *
        """
        with self._connection.cursor() as cursor:
            cursor.execute(statement, {"id": pattern_id, **_json_parameters(values)})
            row = cursor.fetchone()
            columns_out = [column.name for column in cursor.description]
            PostgresPatternRepository._insert_event(cursor, event_id, pattern_id, event)
        return dict(row) if isinstance(row, Mapping) else dict(zip(columns_out, row))

    def update_pattern(self, pattern_id, expected_state_version, values, event):
        assignments = [
            f"{name} = %({name})s" + ("::jsonb" if name in {"measurements", "supporting_patterns"} else "")
            for name in values if name not in {"id", "state_version", "created_at", "updated_at", "isin"}
        ]
        statement = f"""
            UPDATE pattern_instances
            SET {', '.join(assignments)}, state_version = %(new_state_version)s, updated_at = NOW()
            WHERE id = %(id)s AND isin = %(scope_isin)s
              AND state_version = %(expected_state_version)s AND terminal_date IS NULL
            RETURNING *
        """
        parameters = {
            "id": pattern_id, "scope_isin": self._isin,
            "expected_state_version": expected_state_version,
            "new_state_version": expected_state_version + (1 if event is not None else 0),
            **_json_parameters(values),
        }
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            row = cursor.fetchone()
            if row is None:
                raise PatternConcurrencyError(f"Pattern {pattern_id} changed concurrently or is terminal")
            columns = [column.name for column in cursor.description]
            if event is not None:
                PostgresPatternRepository._insert_event(cursor, str(uuid4()), pattern_id, event)
        return dict(row) if isinstance(row, Mapping) else dict(zip(columns, row))

    def load_events(self, pattern_id):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pattern_events WHERE pattern_instance_id = %s ORDER BY state_version, recorded_at, id",
                (pattern_id,),
            )
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
        return [dict(row) if isinstance(row, Mapping) else dict(zip(columns, row)) for row in rows]

    def _require_isin(self, isin):
        if isin != self._isin:
            raise ValueError("Pattern transaction cannot cross security boundaries")


def _json_parameters(values):
    result = dict(values)
    for name in ("measurements", "supporting_patterns"):
        if name in result:
            result[name] = json.dumps(serialize_value(result[name]), sort_keys=True)
    return result
