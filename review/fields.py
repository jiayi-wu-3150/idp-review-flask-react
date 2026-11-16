"""Shape the walker's leaves into exactly what the UI renders.

This is the one real difference from the AppKit version of this app: there, shape
discovery happens in TypeScript because a query file cannot walk a VARIANT. Here
it happens in Python, server-side, so the browser receives a flat list of values
and never needs to understand an AI function's output shape.
"""

from __future__ import annotations

import json
from typing import Any

from review.walk import Walked, values_by_path, walk


def _as_json(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


def fields_for(response_json: Any, approved_json: Any) -> dict[str, Any]:
    """One entry per reviewable value, with evidence resolved and approvals applied."""
    model = _as_json(response_json)
    approved_doc = _as_json(approved_json)
    walked: Walked = walk(model)
    approved_values = values_by_path(approved_doc) if approved_doc is not None else {}

    # Any page will do as a fallback, so a document with no citations still shows
    # its page: the reviewer has to read it to judge a value.
    first_page = next(iter(sorted(walked.page_images)), None)

    fields: list[dict[str, Any]] = []
    for leaf in walked.leaves:
        approved_value = approved_values.get(leaf.path)
        citation = walked.citations.get(leaf.citation_ids[0]) if leaf.citation_ids else None
        coord = leaf.coord or (citation or {}).get("coord")
        page_id = leaf.page_id if leaf.page_id is not None else (citation or {}).get("page_id")
        image_page = page_id if page_id is not None else first_page
        fields.append(
            {
                "path": leaf.path,
                "type_key": leaf.type_key,
                "group_name": leaf.group_name,
                "item_index": leaf.item_index,
                # The agreed value: the approved one if it exists, else the model's.
                "value": approved_value if approved_value is not None else leaf.value,
                "model_value": leaf.value,
                "confidence": leaf.confidence,
                "human_changed": approved_value is not None and approved_value != leaf.value,
                "coord": coord,
                "page_id": page_id,
                "image_file": walked.page_images.get(image_page) if image_page is not None else None,
                "kind": leaf.kind,
            }
        )
    return {
        "fields": fields,
        # True when no field anywhere carries a score: the UI then hides the
        # confidence badges instead of marking every value as needing review.
        "has_confidence": any(f["confidence"] is not None for f in fields),
        "has_citations": any(f["coord"] for f in fields),
    }
