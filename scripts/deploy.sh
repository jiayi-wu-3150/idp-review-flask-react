#!/usr/bin/env bash
# Deploy to Databricks Apps. Creates the app on first run with the user
# authorization scopes it needs -- scopes are FIXED at creation and cannot be
# added later, which is why this script creates rather than expecting you to.
#
#   APP_NAME=my-review-app \
#   WAREHOUSE_ID=... VOLUME=catalog.schema.page_images \
#   INPUT_TABLE=catalog.schema.extracted \
#   PROFILE=my-cli-profile ./scripts/deploy.sh
set -euo pipefail

: "${APP_NAME:?set APP_NAME}"
: "${WAREHOUSE_ID:?set WAREHOUSE_ID}"
: "${VOLUME:?set VOLUME (catalog.schema.volume)}"
: "${INPUT_TABLE:?set INPUT_TABLE (catalog.schema.table)}"
PROFILE="${PROFILE:-DEFAULT}"
WORKSPACE_PATH="${WORKSPACE_PATH:-/Workspace/Users/$(databricks current-user me -p "$PROFILE" -o json | python3 -c 'import json,sys;print(json.load(sys.stdin)["userName"])')/apps/$APP_NAME}"

echo "==> building the frontend (Flask serves frontend/dist)"
(cd frontend && npm install --silent && npm run build)

if ! databricks apps get "$APP_NAME" -p "$PROFILE" >/dev/null 2>&1; then
  echo "==> creating $APP_NAME with scopes sql + files.files"
  databricks apps create -p "$PROFILE" --json "$(python3 - "$APP_NAME" "$WAREHOUSE_ID" "$VOLUME" <<'PY'
import json, sys
name, warehouse, volume = sys.argv[1], sys.argv[2], sys.argv[3]
print(json.dumps({
    "name": name,
    "description": "Human review of AI document-processing output",
    "user_api_scopes": ["sql", "files.files"],
    "resources": [
        {"name": "sql-warehouse", "sql_warehouse": {"id": warehouse, "permission": "CAN_USE"}},
        {"name": "files", "uc_securable": {
            "securable_type": "VOLUME", "securable_full_name": volume, "permission": "READ_VOLUME"}},
    ],
}))
PY
)"
fi

# `databricks sync` honours .gitignore, which excludes frontend/dist -- so
# syncing the source tree would deploy an app with no client. Stage exactly what
# the app needs at runtime instead, which also leaves the TS sources behind.
echo "==> staging the runtime bundle in .deploy"
rm -rf .deploy && mkdir -p .deploy/frontend
cp app.py requirements.txt .deploy/
# INPUT_TABLE is written into the STAGED app.yaml only, so the repo keeps its
# placeholder and a deploy never leaves the working tree dirty.
python3 -c "
import pathlib, re, sys
src = pathlib.Path('app.yaml').read_text()
pathlib.Path('.deploy/app.yaml').write_text(
    re.sub(r\"(?m)^(    value: ').*(')$\", r\"\\g<1>\" + sys.argv[1] + r\"\\g<2>\", src))
" "$INPUT_TABLE"
cp -R review .deploy/review
cp -R frontend/dist .deploy/frontend/dist
find .deploy -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo "==> syncing $WORKSPACE_PATH"
databricks sync .deploy "$WORKSPACE_PATH" -p "$PROFILE" --full

echo "==> deploying"
databricks apps deploy "$APP_NAME" -p "$PROFILE" --source-code-path "$WORKSPACE_PATH"

databricks apps get "$APP_NAME" -p "$PROFILE" -o json | python3 -c 'import json,sys;a=json.load(sys.stdin);print("\n==> "+a["url"])'
