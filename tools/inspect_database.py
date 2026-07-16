#!/usr/bin/env python3
"""Display how WE_OWE stores Sprint 1 data in SQLite.

Run from the project folder:
    python tools/inspect_database.py

Optional: inspect only one table:
    python tools/inspect_database.py users
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, select

# Allow this file to be run directly as: python tools/inspect_database.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app, db


SENSITIVE_COLUMNS = {"password_hash"}


def format_value(column: str, value: object) -> str:
    if column in SENSITIVE_COLUMNS and value:
        return "<secure password hash hidden>"
    if value is None:
        return "NULL"
    return str(value)


def print_schema(inspector, table_name: str) -> None:
    print(f"\nTABLE: {table_name}")
    print("-" * (7 + len(table_name)))
    for column in inspector.get_columns(table_name):
        flags = []
        if column.get("primary_key"):
            flags.append("PRIMARY KEY")
        if not column.get("nullable", True):
            flags.append("NOT NULL")
        details = f" ({', '.join(flags)})" if flags else ""
        print(f"  {column['name']}: {column['type']}{details}")

    for foreign_key in inspector.get_foreign_keys(table_name):
        local = ", ".join(foreign_key["constrained_columns"])
        remote = ", ".join(foreign_key["referred_columns"])
        print(f"  RELATIONSHIP: {local} -> {foreign_key['referred_table']}.{remote}")


def print_rows(table_name: str) -> None:
    table = db.metadata.tables[table_name]
    rows = db.session.execute(select(table)).mappings().all()
    print(f"  STORED ROWS: {len(rows)}")
    for number, row in enumerate(rows, start=1):
        values = ", ".join(
            f"{column}={format_value(column, value)}" for column, value in row.items()
        )
        print(f"    {number}. {values}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("table", nargs="?", help="Optional table name")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        database_path = Path(app.instance_path) / "we_owe.db"
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()

        if args.table:
            if args.table not in tables:
                parser.error(f"Unknown table '{args.table}'. Choose from: {', '.join(tables)}")
            tables = [args.table]

        print(f"WE_OWE DATABASE: {database_path}")
        for table_name in tables:
            print_schema(inspector, table_name)
            print_rows(table_name)


if __name__ == "__main__":
    main()
