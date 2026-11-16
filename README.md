# Intelligent Document Review

Human review of AI document-processing output, in Python. A reviewer sees each value
the model produced, the page region it came from, and a confidence badge, then
corrects what is wrong and approves the document.

The form is generated from the data **at runtime**: no field name appears in the
application code, so pointing `INPUT_TABLE` at a different table reshapes the UI with
no code change. (Field names appear only in the test fixtures, which exist to prove
exactly that.)

**Flask** API + **React** client. Python does the shape discovery and all SQL; Node is
a build-time dependency only.

## What it can review

Any table with `id STRING` and a `response VARIANT` holding AI function output.
Confidence and evidence are optional, so a function that provides neither still gives
an editable, approvable form.

| Input | Values discovered | Confidence | Evidence on the page |
|---|---|---|---|
| `ai_extract` | one per field, arrays flattened to `line_items[0].amount` | yes | citation bbox per value |
| `ai_parse_document` | one per element (`content`) | yes | bbox per element |
| `ai_classify` (wrapped into a struct) | one per label | no - badges hidden | page shown, no boxes |

## Lineage

```
Volume (PDFs) --ai_parse_document--> parse table --ai_extract--> INPUT_TABLE (id, response)
                      |                                              |
                 imageOutputPath                            read as the user
                      v                                              v
            Volume (page images) ---- Files API ---->        Flask + React app
                                                                      |
                                                       append as the user
                                                                      v
                                              INPUT_TABLE_approved_log  (append-only)
                                              INPUT_TABLE_approved      (view: one row per document)
```

| Object | Contains |
|---|---|
| `INPUT_TABLE` | your AI function output. **Never written to.** |
| `INPUT_TABLE_approved_log` | append-only: `id`, `approver`, `approved_at`, `approved_response`. One row per approval, so the full history is kept. |
| `INPUT_TABLE_approved` | view, one row per input document: `id`, `response`, `latest_approved_response`, `latest_approved_at`, `latest_approver`, `approval_count` (0 until approved). What downstream reads. |

`approved_response` is the **same schema as `response`** with corrected values
replaced; confidence scores and citations ride along untouched. So `response` vs
`latest_approved_response` is a ready-made model-vs-human evaluation pair.

## Identity: user vs service principal

| Hop | Runs as | How |
|---|---|---|
| Queue + document reads | **signed-in user** | `X-Forwarded-Access-Token` → `databricks.sql.connect(access_token=…)` |
| Approve (`INSERT`) | **signed-in user** | same connection |
| `approver` column | `X-Forwarded-Email`, server-side | never accepted from the client, so the audit trail cannot be forged |
| Page images | **signed-in user** | Files API with the forwarded token |
| Warehouse + volume bindings | app **service principal** | `valueFrom` grants the app; they do not grant the reviewer |

Locally there is no proxy to forward a token, so reads use your CLI profile and the
approver is recorded as `local-dev@localhost` rather than an empty string.

## Prerequisites

**Data.** Run the AI functions first - this app only reviews their output:

```sql
-- 1. parse, writing page images the app can show
CREATE OR REPLACE TABLE my.schema.parsed AS
SELECT path AS id,
       ai_parse_document(content, map('imageOutputPath', '/Volumes/my/schema/page_images')) AS response
FROM READ_FILES('/Volumes/my/schema/pdfs', format => 'binaryFile');

-- 2. extract the fields you care about (or ai_classify, wrapped into a struct)
CREATE OR REPLACE TABLE my.schema.extracted AS
SELECT id, ai_extract(...) AS response FROM my.schema.parsed;
```

**Grants.** Two different roles:

| Role | Needs |
|---|---|
| whoever runs setup, once | `CREATE TABLE` on the schema (this covers views - there is no `CREATE VIEW` privilege), plus `USE CATALOG` and `USE SCHEMA` |
| every reviewer | `SELECT` on `INPUT_TABLE` and `INPUT_TABLE_approved`; `MODIFY` **and** `SELECT` on `INPUT_TABLE_approved_log`; `READ VOLUME` on the page-image volume |

**App.** Python 3.11+, Node 22+ (build only), Databricks CLI, and the app created with
user authorization scopes `sql` and `files.files` - **scopes are fixed at creation and
cannot be added later**.

## Setup

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # profile, warehouse, volume, INPUT_TABLE

# create INPUT_TABLE_approved_log and INPUT_TABLE_approved
INPUT_TABLE=catalog.schema.extracted DATABRICKS_WAREHOUSE_ID=… .venv/bin/python scripts/setup.py

npm --prefix frontend install && npm --prefix frontend run build
.venv/bin/python app.py          # http://localhost:9000
```

The two DDL statements are in [`sql/setup.sql`](sql/setup.sql) if you would rather run
them yourself.

### Deploy

`scripts/deploy.sh` creates the app with the right scopes on first run, builds the
client, stages a runtime bundle and deploys it:

```bash
APP_NAME=my-review-app \
WAREHOUSE_ID=… VOLUME=catalog.schema.page_images \
INPUT_TABLE=catalog.schema.extracted \
PROFILE=my-cli-profile ./scripts/deploy.sh
```

`scripts/smoke_test.py` checks a running instance: `BASE_URL=http://localhost:9000
.venv/bin/python scripts/smoke_test.py`.

## Tests

```bash
.venv/bin/python -m pytest tests -q      # 21 tests, no workspace needed
```

They pin the three output shapes and the overlay that keeps `approved_response` in the
input's schema. The fixtures are real (trimmed) AI function output; if a fourth shape
appears, add it there first.

## Implementation notes

Things that are deliberate, and cost time to find:

- **A forwarded user token needs its own `Config`.** A deployed app already has OAuth
  credentials in its environment, so `WorkspaceClient(host=…, token=…)` fails with
  *"more than one authorization method configured: oauth and pat"*. Use
  `Config(host=…, token=…, auth_type="pat")`.
- **`databricks sync` honours `.gitignore`**, which excludes `frontend/dist` - syncing
  the source tree deploys an app with no client. `deploy.sh` stages a runtime bundle
  instead, which also leaves the TypeScript sources behind.
- **Shape discovery runs server-side** (`review/walk.py`), so the browser receives a
  flat list of values and never needs to understand an AI function's output.
- **Numbers use `type="text"`**: a native number input coerces DECIMAL to float,
  turning `109303.32` into `109303.3203125`.
- **Bbox colours are fixed hex, not theme colours** - they sit on an always-white page
  image.
- **Constraint names are schema-scoped in UC**, so the log's primary key name includes
  the table name; a fixed name collides the second time you run setup in one schema.
- **No dropdown widget**: `ai_extract` stores `enum` as `STRING`, so a closed enum
  cannot be told from a low-cardinality string, and constraining a reviewer to seen
  values would block the correction they came to make.

## Known gaps

- No claim or lock on a document: two reviewers can approve the same one, and the view
  resolves by recency (`approval_count` shows how many).
- Cross-page citation resolution is implemented but untested - no field in the sample
  corpora cites page 2.
- Streamlit was considered and dropped: the Apps router does not honour its session
  affinity cookie, so anything with in-memory session state breaks above one instance.
