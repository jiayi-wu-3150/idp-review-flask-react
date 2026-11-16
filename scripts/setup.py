#!/usr/bin/env python3
"""Create the two output objects for whatever INPUT_TABLE points at.

Runs as *you*, not as the app's service principal, so the app never needs CREATE
on your schema: it only ever reads the input and appends to the log.

    INPUT_TABLE=catalog.schema.table python scripts/setup.py
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

from databricks import sql as dbsql
from databricks.sdk.core import Config

QUALIFIED = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")
SQL_FILE = pathlib.Path(__file__).resolve().parent.parent / "sql" / "setup.sql"


def statements(table: str) -> list[str]:
    body = SQL_FILE.read_text().replace("<INPUT_TABLE>", table).replace(
        "<INPUT_LEAF>", table.split(".")[-1]
    )
    # Split on a semicolon that ends a line, so a semicolon inside a COMMENT
    # string cannot split a statement in half.
    parts = re.split(r";\s*\n(?=(?:--|CREATE))", body)
    out = []
    for part in parts:
        cleaned = "\n".join(l for l in part.splitlines() if not l.strip().startswith("--")).strip()
        if cleaned:
            out.append(cleaned.rstrip(";"))
    return out


def main() -> int:
    table = os.getenv("INPUT_TABLE", "")
    warehouse = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
    if not QUALIFIED.match(table):
        print("INPUT_TABLE must be set to a catalog.schema.table name", file=sys.stderr)
        return 1
    if not warehouse:
        print("DATABRICKS_WAREHOUSE_ID must be set", file=sys.stderr)
        return 1

    cfg = Config()
    with dbsql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{warehouse}",
        credentials_provider=lambda: cfg.authenticate,
    ) as conn:
        for statement in statements(table):
            with conn.cursor() as cur:
                cur.execute(statement)
            kind = "view " if "CREATE OR REPLACE VIEW" in statement else "table"
            print(f"OK  {kind}  {table}_approved{'_log' if kind == 'table' else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
