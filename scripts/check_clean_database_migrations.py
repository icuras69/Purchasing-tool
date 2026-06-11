from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).resolve().parents[1]
CORE_TABLES = {"products", "suppliers", "product_suppliers", "alembic_version"}


def _guard_database_url(database_url: str, *, allow_non_empty: bool) -> None:
    url = make_url(database_url)
    database_name = url.database or ""
    if url.drivername.startswith("postgresql") and database_name == "purchasing_ai" and not allow_non_empty:
        raise RuntimeError(
            "Refusing to run clean migration check against the normal local development database. "
            "Use a disposable database or pass --allow-non-empty after careful review."
        )


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return set(inspect(connection).get_table_names())
    finally:
        engine.dispose()


def _current_revision(database_url: str) -> str | None:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            if "alembic_version" not in inspect(connection).get_table_names():
                return None
            return connection.execute(text("select version_num from alembic_version")).scalar()
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Alembic can upgrade a clean disposable database to head.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--allow-non-empty", action="store_true")
    args = parser.parse_args()

    if not args.database_url:
        print("DATABASE_URL is required.", file=sys.stderr)
        return 2

    _guard_database_url(args.database_url, allow_non_empty=args.allow_non_empty)
    existing_tables = _table_names(args.database_url)
    if existing_tables and not args.allow_non_empty:
        print(
            "Target database is not empty. Refusing to run clean migration check without --allow-non-empty. "
            f"Existing tables: {sorted(existing_tables)}",
            file=sys.stderr,
        )
        return 2

    os.environ["DATABASE_URL"] = args.database_url
    config = Config(str(ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    head = script.get_current_head()
    command.upgrade(config, "head")

    tables = _table_names(args.database_url)
    missing = sorted(CORE_TABLES - tables)
    if missing:
        print(f"Migration completed, but required tables are missing: {missing}", file=sys.stderr)
        return 1

    current = _current_revision(args.database_url)
    print(f"Alembic head: {head}")
    print(f"Database current revision: {current}")
    print(f"Verified core tables: {sorted(CORE_TABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
