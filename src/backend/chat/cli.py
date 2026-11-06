"""Local ontology setup and read-only verification (never prints credentials)."""
import argparse
import json
import os
from pathlib import Path
import secrets


def configure():
    from server import build_repository
    from psycopg import connect, sql
    from psycopg.conninfo import conninfo_to_dict

    build_repository()  # Preserve the established append-only migration runner.
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise ValueError("DATABASE_URL is required")
    root = Path(__file__).resolve().parents[3]
    config = root / "infra/ontology/.env"
    existing = {}
    if config.exists():
        existing = dict(line.split("=", 1) for line in config.read_text().splitlines() if "=" in line)
    password = existing.get("ONTOP_DB_PASSWORD") or secrets.token_urlsafe(32)
    role = "tradelens_ontology_reader"
    values = conninfo_to_dict(dsn)
    host = values.get("host", "127.0.0.1")
    if host in {"127.0.0.1", "localhost", "::1"}:
        host = "host.docker.internal"
    with connect(dsn) as connection:
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
        connection.execute(sql.SQL("ALTER ROLE {} WITH PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT").format(sql.Identifier(role), sql.Literal(password)))
        connection.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '8s'").format(sql.Identifier(role)))
        connection.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
        connection.execute(sql.SQL("GRANT SELECT ON chat_security_context, chat_current_setups, chat_setup_scores TO {}").format(sql.Identifier(role)))
    url = f"jdbc:postgresql://{host}:{values.get('port', '5432')}/{values.get('dbname', 'tradelens')}"
    config.write_text(f"ONTOP_DB_URL={url}\nONTOP_DB_USER={role}\nONTOP_DB_PASSWORD={password}\n", encoding="utf-8")
    print("Applied migrations and configured the read-only ontology role. Local Docker settings saved to infra/ontology/.env (git-ignored).")


def verify(symbol):
    from server import load_local_environment
    from repositories.knowledge_graph import OntopKnowledgeGraphRepository
    load_local_environment()
    rows = OntopKnowledgeGraphRepository(os.getenv("ONTOP_URL", "http://127.0.0.1:8088/sparql")).current_setups(symbol)
    # Public verification output avoids security IRIs containing internal ISINs.
    fields = ("symbol", "name", "dataAsOf", "featureDate", "patternDate", "patternId", "patternType", "state", "setup")
    print(json.dumps([{key: row.get(key) for key in fields} for row in rows], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure")
    check = commands.add_parser("verify")
    check.add_argument("--symbol", default="RELIANCE")
    args = parser.parse_args()
    try:
        if args.command == "configure":
            configure()
        else:
            verify(args.symbol)
    except Exception:
        # Driver/provider exceptions can contain connection details.
        parser.exit(1, "Ontology operation failed. Check database/service availability and local configuration.\n")


if __name__ == "__main__":
    main()
