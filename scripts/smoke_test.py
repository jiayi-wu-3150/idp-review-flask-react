#!/usr/bin/env python3
"""Smoke-test a running instance: the three endpoints and the first-run errors.

    BASE_URL=http://localhost:9000 python scripts/smoke_test.py

Against a deployed app, pass a URL it can reach; a deployed app also requires a
browser session, so this is aimed at local runs and CI.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("BASE_URL", "http://localhost:9000").rstrip("/")


def get(path: str):
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=60) as r:  # noqa: S310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def main() -> int:
    failures: list[str] = []

    status, body = get("/health")
    if status != 200 or body.get("status") != "ok":
        failures.append(f"/health returned {status} {body}")

    status, docs = get("/api/documents")
    if status != 200 or not isinstance(docs, list) or not docs:
        failures.append(f"/api/documents returned {status} {docs}")
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"OK  /api/documents        {len(docs)} documents, "
          f"{sum(1 for d in docs if d['approved'])} approved")

    first = docs[0]["id"]
    status, detail = get(f"/api/document?id={urllib.request.quote(first)}")
    if status != 200 or "fields" not in detail:
        failures.append(f"/api/document returned {status} {detail}")
    else:
        print(f"OK  /api/document         {len(detail['fields'])} fields, "
              f"confidence={detail['has_confidence']}, citations={detail['has_citations']}")
        image = next((f["image_file"] for f in detail["fields"] if f["image_file"]), None)
        if image:
            try:
                with urllib.request.urlopen(  # noqa: S310
                    f"{BASE}/api/files/raw?path={urllib.request.quote(image)}", timeout=60
                ) as r:
                    size = len(r.read())
                print(f"OK  /api/files/raw        {size:,} bytes")
            except urllib.error.HTTPError as e:
                failures.append(f"/api/files/raw returned {e.code}")

    status, body = get("/api/document?id=")
    if status != 400:
        failures.append(f"missing id should be 400, got {status}")
    else:
        print("OK  missing id            400")

    if failures:
        print("\nFAILED:\n" + "\n".join(f"  {f}" for f in failures), file=sys.stderr)
        return 1
    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
