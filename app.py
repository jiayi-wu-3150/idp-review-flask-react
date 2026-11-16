"""Intelligent Document Review - Flask + React.

Human review of AI document-processing output. The review form is generated from
the data at runtime, so no field name appears in this application code and
pointing INPUT_TABLE at a different table reshapes the UI with no code change.

Identity, end to end:

    reads + the approve write   the signed-in user (X-Forwarded-Access-Token)
    approver column             X-Forwarded-Email, server-side, never from the client
    page images                 the signed-in user, via the Files API
    warehouse + volume          named by env, bound as app resources

Locally there is no proxy to forward a token, so the CLI profile is used and the
approver falls back to a marked identity rather than an empty string.
"""

from __future__ import annotations

import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from flask import Flask, Response, jsonify, request, send_from_directory

from review.fields import fields_for
from review.store import SetupRequired, approve, explain, get_document, list_documents, tables

DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
INDEX = os.path.join(DIST, "index.html")

app = Flask(__name__, static_folder=DIST, static_url_path="")


def user_token() -> str | None:
    """The reviewer's forwarded token. Absent locally, where there is no proxy."""
    return request.headers.get("X-Forwarded-Access-Token")


def approver() -> str:
    """Attribution is never a knob: it comes from the request, not the client."""
    email = request.headers.get("X-Forwarded-Email") or request.headers.get(
        "X-Forwarded-Preferred-Username"
    )
    if email:
        return email
    if os.getenv("FLASK_DEBUG") or not os.getenv("DATABRICKS_APP_PORT"):
        return "local-dev@localhost"
    raise SetupRequired("No authenticated user on the request.")


def _fail(err: Exception):
    if isinstance(err, SetupRequired):
        return jsonify({"error": str(err)}), 500
    try:
        return jsonify({"error": explain(err, tables())}), 500
    except SetupRequired as setup_err:
        return jsonify({"error": str(setup_err)}), 500


@app.get("/api/documents")
def api_documents():
    try:
        return jsonify(list_documents(user_token()))
    except Exception as err:  # noqa: BLE001 - surfaced to the client as a message
        app.logger.exception("Failed to list documents")
        return _fail(err)


@app.get("/api/document")
def api_document():
    document_id = request.args.get("id", "")
    if not document_id:
        return jsonify({"error": "id is required"}), 400
    try:
        doc = get_document(user_token(), document_id)
        if doc is None:
            return jsonify({"error": "Document not found"}), 404
        # Shape discovery happens here, not in the browser.
        shaped = fields_for(doc.pop("response"), doc.get("approved_response"))
        doc.pop("approved_response", None)
        return jsonify({**doc, **shaped})
    except Exception as err:  # noqa: BLE001
        app.logger.exception("Failed to load document")
        return _fail(err)


@app.post("/api/approve")
def api_approve():
    body = request.get_json(silent=True) or {}
    document_id = body.get("id")
    edits = body.get("edits")
    if not isinstance(document_id, str) or not document_id or not isinstance(edits, dict):
        return jsonify({"error": "Invalid approval payload"}), 400
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in edits.items()):
        return jsonify({"error": "Invalid approval payload"}), 400
    try:
        who = approver()
        changed = approve(user_token(), who, document_id, edits)
        return jsonify({"id": document_id, "approver": who, "changed": changed})
    except Exception as err:  # noqa: BLE001
        app.logger.exception("Failed to approve")
        return _fail(err)


@app.get("/api/files/raw")
def api_file():
    """Serve a page image from the volume, as the signed-in user.

    Only a file name is accepted: the volume is fixed by DATABRICKS_VOLUME_FILES,
    so a caller cannot walk out of it.
    """
    name = os.path.basename(request.args.get("path", ""))
    volume = os.getenv("DATABRICKS_VOLUME_FILES")
    if not name or not volume:
        return jsonify({"error": "path is required and DATABRICKS_VOLUME_FILES must be set"}), 400
    try:
        token = user_token()
        if token:
            # A deployed app already has OAuth credentials in its environment, so
            # passing a user token alongside them makes the SDK refuse with
            # "more than one authorization method configured: oauth and pat".
            # Isolate the forwarded token in its own Config instead.
            host = os.getenv("DATABRICKS_HOST") or Config().host
            client = WorkspaceClient(config=Config(host=host, token=token, auth_type="pat"))
        else:
            client = WorkspaceClient()
        download = client.files.download(f"{volume.rstrip('/')}/{name}")
        return Response(download.contents.read(), mimetype="image/jpeg")
    except Exception as err:  # noqa: BLE001
        app.logger.exception("Failed to read %s", name)
        return jsonify({"error": str(err)}), 404


@app.get("/health")
def health():
    return {"status": "ok"}


def _client():
    """Serve the built client, or say plainly that it has not been built.

    Without this guard a missing build makes the 404 handler call itself and the
    browser sees an opaque 500.
    """
    if not os.path.exists(INDEX):
        return (
            jsonify(
                {
                    "error": "frontend/dist is missing. Build the client with "
                    "`npm --prefix frontend install && npm --prefix frontend run build`, "
                    "or deploy with scripts/deploy.sh, which builds and packages it."
                }
            ),
            500,
        )
    return send_from_directory(DIST, "index.html")


@app.get("/")
def index():
    return _client()


@app.errorhandler(404)
def spa_fallback(_err):
    """Single-page app: unknown non-API paths render the client."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return _client()


if __name__ == "__main__":
    # Databricks Apps injects the port; FLASK_RUN_HOST is set to 0.0.0.0 there.
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("DATABRICKS_APP_PORT") or os.getenv("FLASK_RUN_PORT") or 8000)
    app.run(host=host, port=port)
