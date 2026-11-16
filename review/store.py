"""Every SQL statement the app runs, plus the two identities it runs them as.

Reads and writes both run as the **signed-in user**: Databricks Apps forwards the
user's token in ``X-Forwarded-Access-Token``, so Unity Catalog applies the
reviewer's own grants and the approval is attributed to them. Locally there is no
proxy, so the CLI profile is used instead.

One env var names the input; the two outputs follow by convention:

    INPUT_TABLE                   your AI function output: id STRING, response VARIANT
    INPUT_TABLE_approved_log      append-only, the app's only write target
    INPUT_TABLE_approved          the view everything downstream reads
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from databricks import sql as dbsql
from databricks.sdk.core import Config

# Table names are identifiers, so they cannot be bound as parameters.
QUALIFIED_NAME = re.compile(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+\.[A-Za-z0-9_]+$")


class SetupRequired(Exception):
    """Raised with a message a user can act on, not a raw SQL error."""


@dataclass(frozen=True)
class Tables:
    input: str
    log: str
    approved: str


def tables() -> Tables:
    name = os.getenv("INPUT_TABLE", "")
    if not QUALIFIED_NAME.match(name):
        raise SetupRequired(
            "INPUT_TABLE must be set to a catalog.schema.table name. "
            "Point it at a table with an id column and a VARIANT response column."
        )
    return Tables(name, f"{name}_approved_log", f"{name}_approved")


def explain(err: Exception, t: Tables) -> str:
    """Turn the two first-run failures into something a user can act on."""
    message = str(err)
    if re.search(r"TABLE_OR_VIEW_NOT_FOUND|cannot be found|does not exist", message, re.I):
        if f"{t.input}_approved" in message:
            return (
                f"{t.approved} does not exist. Run `python scripts/setup.py` to create "
                f"the approval log and view for {t.input}."
            )
        return (
            f"{t.input} does not exist. Point INPUT_TABLE at a table with an id column "
            "and a VARIANT response column."
        )
    if re.search(r"PERMISSION_DENIED|does not have permission|INSUFFICIENT", message, re.I):
        return (
            f"You do not have access to {t.input}. Queries run as the signed-in user, so "
            "Unity Catalog grants apply to you, not to the app."
        )
    return message


def _connection(user_token: str | None):
    """A warehouse connection for this request.

    Deployed: the forwarded user token, so the query runs as the reviewer.
    Local: the CLI profile, because there is no proxy to forward a token.
    """
    cfg = Config()
    warehouse = os.getenv("DATABRICKS_WAREHOUSE_ID")
    if not warehouse:
        raise SetupRequired("DATABRICKS_WAREHOUSE_ID must be set (bind a sql-warehouse resource).")
    http_path = f"/sql/1.0/warehouses/{warehouse}"
    if user_token:
        return dbsql.connect(server_hostname=cfg.host, http_path=http_path, access_token=user_token)
    return dbsql.connect(
        server_hostname=cfg.host, http_path=http_path, credentials_provider=lambda: cfg.authenticate
    )


def _query(user_token: str | None, statement: str, params: dict[str, Any] | None = None):
    with _connection(user_token) as conn, conn.cursor() as cur:
        cur.execute(statement, params or {})
        columns = [c[0] for c in cur.description or []]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def list_documents(user_token: str | None) -> list[dict[str, Any]]:
    """Review queue, pending first. The view already has one row per document."""
    t = tables()
    rows = _query(
        user_token,
        f"""
        SELECT id,
               approval_count > 0 AS approved,
               CAST(latest_approved_at AS STRING) AS approved_at,
               approval_count
        FROM {t.approved}
        ORDER BY approved ASC, id ASC
        """,
    )
    return [
        {
            "id": r["id"],
            "approved": bool(r["approved"]),
            "approved_at": r["approved_at"],
            "approval_count": int(r["approval_count"]),
        }
        for r in rows
    ]


def get_document(user_token: str | None, document_id: str) -> dict[str, Any] | None:
    """One document as raw JSON. The client walks the shape, which is why this
    works for any AI function output without the server knowing the schema."""
    t = tables()
    rows = _query(
        user_token,
        f"""
        SELECT to_json(response)                 AS response,
               to_json(latest_approved_response) AS approved_response,
               CAST(latest_approved_at AS STRING) AS approved_at,
               latest_approver                   AS approver,
               approval_count
        FROM {t.approved}
        WHERE id = :id
        """,
        {"id": document_id},
    )
    if not rows:
        return None
    row = rows[0]
    return {
        "response": row["response"],
        "approved_response": row["approved_response"],
        "approved_at": row["approved_at"],
        "approver": row["approver"],
        "approval_count": int(row["approval_count"]),
    }


def approve(user_token: str | None, approver: str, document_id: str, edits: dict[str, str]) -> int:
    """Overlay the approver's edits onto the model's response and append the whole
    thing to the log. The client sends only what it changed, so it can neither
    invent metadata nor name the approver."""
    from review.walk import set_at_path

    t = tables()
    # Start from the latest approved copy if there is one, so a second approval
    # builds on the first rather than reverting it.
    rows = _query(
        user_token,
        f"""
        SELECT coalesce(to_json(latest_approved_response), to_json(response)) AS base
        FROM {t.approved}
        WHERE id = :id
        """,
        {"id": document_id},
    )
    if not rows or not rows[0]["base"]:
        raise SetupRequired("Document not found.")

    approved = json.loads(rows[0]["base"])
    for path, value in edits.items():
        set_at_path(approved, path, value)

    _query(
        user_token,
        f"""
        INSERT INTO {t.log} (id, approver, approved_at, approved_response)
        SELECT :id, :approver, current_timestamp(), parse_json(:approved_response)
        """,
        {"id": document_id, "approver": approver, "approved_response": json.dumps(approved)},
    )
    return len(edits)
