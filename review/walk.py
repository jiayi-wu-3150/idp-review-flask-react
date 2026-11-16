"""Turn any AI-function output into a flat list of reviewable values.

Nothing here knows a field name. Three shapes are recognised, in order:

- ``{"response": {...}}``          ai_extract, or a scalar function wrapped into a
                                  struct (ai_classify). Leaves are usually
                                  ``{value, confidence_score, citation_ids}``.
- ``{"document": {"elements": []}}``  ai_parse_document. Each element is a leaf whose
                                  value is ``content``, with its own ``confidence``
                                  and an inline ``bbox``.
- anything else                   walked as-is; bare scalars are their own values.

Confidence and evidence are optional everywhere: a function that provides neither
still produces an editable, approvable form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NUMERIC = re.compile(r"^-?\d+(\.\d+)?$")
_INDEX = re.compile(r"\[\d+\]")


@dataclass
class Leaf:
    """One reviewable value."""

    path: str
    """Full path from the document root: ``response.line_items[0].amount``."""
    type_key: str
    """Path with array indices removed, so leaves of one array share a label."""
    group_name: str | None
    item_index: int | None
    value: str | None
    confidence: float | None
    citation_ids: list[int] = field(default_factory=list)
    coord: list[int] | None = None
    """Evidence carried on the leaf itself (ai_parse_document)."""
    page_id: int | None = None
    kind: str = "text"
    """``number`` | ``text`` | ``json``"""


@dataclass
class Walked:
    leaves: list[Leaf]
    citations: dict[int, dict[str, Any]]
    """citation id -> {"coord", "page_id"}, from metadata.citations (ai_extract)."""
    page_images: dict[int, str]
    """page id -> image file name, from metadata.pages or document.pages."""


def _strip_indices(path: str) -> str:
    return _INDEX.sub("", path)


def _kind_of(v: Any) -> str:
    if isinstance(v, bool):
        return "text"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str) and NUMERIC.match(v.strip()):
        return "number"
    return "text"


def _as_text(v: Any) -> str | None:
    import json

    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list)):
        return json.dumps(v, indent=1)
    return str(v)


def _is_wrapped(v: Any) -> bool:
    """A leaf as ai_extract writes it."""
    return isinstance(v, dict) and "value" in v


def _is_element(v: Any) -> bool:
    """A leaf as ai_parse_document writes it."""
    return isinstance(v, dict) and "content" in v and "bbox" in v


def _bbox_of(node: dict[str, Any]) -> dict[str, Any]:
    bbox = node.get("bbox")
    if isinstance(bbox, list) and bbox and isinstance(bbox[0], dict):
        first = bbox[0]
        coord = first.get("coord")
        coord = [int(c) for c in coord] if isinstance(coord, list) and len(coord) == 4 else None
        page_id = first.get("page_id") if isinstance(first.get("page_id"), int) else None
        return {"coord": coord, "page_id": page_id}
    return {"coord": None, "page_id": None}


def _emit(node: Any, path: str, group: str | None, index: int | None) -> list[Leaf]:
    # Wrapped leaf: value plus whatever metadata the function provided.
    if _is_wrapped(node):
        raw = node.get("value")
        conf = node.get("confidence_score")
        ids = node.get("citation_ids")
        return [
            Leaf(
                path=path,
                type_key=_strip_indices(path),
                group_name=group,
                item_index=index,
                value=_as_text(raw),
                confidence=float(conf) if isinstance(conf, (int, float)) else None,
                citation_ids=[int(i) for i in ids] if isinstance(ids, list) else [],
                kind="number" if raw is None else _kind_of(raw),
                **_bbox_of(node),
            )
        ]

    # ai_parse_document element: the content is the value, evidence is inline.
    if _is_element(node):
        conf = node.get("confidence")
        element_type = node.get("type") if isinstance(node.get("type"), str) else "element"
        return [
            Leaf(
                path=f"{path}.content",
                type_key=f"{_strip_indices(path)}.{element_type}",
                group_name=group,
                item_index=index,
                value=_as_text(node.get("content")),
                confidence=float(conf) if isinstance(conf, (int, float)) else None,
                kind="text",
                **_bbox_of(node),
            )
        ]

    if isinstance(node, list):
        out: list[Leaf] = []
        for i, item in enumerate(node):
            out.extend(_emit(item, f"{path}[{i}]", _strip_indices(path), i))
        return out

    if isinstance(node, dict):
        keys = list(node)
        children: list[Leaf] = []
        for k in keys:
            children.extend(_emit(node[k], f"{path}.{k}" if path else k, group, index))
        if children:
            return children
        # Nothing reviewable inside. Two different cases, and conflating them turns
        # a document with an empty array into one unreadable JSON blob:
        #   - keys that yielded no leaves (empty arrays): nothing to review here;
        #   - no keys at all: opaque, worth showing read-only.
        if keys:
            return []
        return [
            Leaf(
                path=path,
                type_key=_strip_indices(path),
                group_name=group,
                item_index=index,
                value=_as_text(node),
                confidence=None,
                kind="json",
            )
        ]

    # Bare scalar: it is its own value.
    return [
        Leaf(
            path=path,
            type_key=_strip_indices(path),
            group_name=group,
            item_index=index,
            value=_as_text(node),
            confidence=None,
            kind=_kind_of(node),
        )
    ]


def _basename(uri: Any) -> str | None:
    return uri.split("/")[-1] if isinstance(uri, str) and uri else None


def walk(doc: Any) -> Walked:
    citations: dict[int, dict[str, Any]] = {}
    page_images: dict[int, str] = {}

    if not isinstance(doc, dict):
        return Walked([], citations, page_images)

    metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    document = doc.get("document") if isinstance(doc.get("document"), dict) else {}

    for c in metadata.get("citations") or []:
        if isinstance(c, dict) and isinstance(c.get("id"), int):
            citations[c["id"]] = _bbox_of(c)
    for source in (metadata.get("pages"), document.get("pages")):
        for p in source or []:
            if isinstance(p, dict) and isinstance(p.get("id"), int):
                name = _basename(p.get("image_uri"))
                if name:
                    page_images[p["id"]] = name

    # Field root, in precedence order.
    if isinstance(doc.get("response"), dict):
        leaves = _emit(doc["response"], "response", None, None)
    elif isinstance(document.get("elements"), list):
        leaves = _emit(document["elements"], "document.elements", "elements", None)
    else:
        leaves = _emit(doc, "", None, None)

    return Walked(leaves, citations, page_images)


def values_by_path(doc: Any) -> dict[str, str | None]:
    """Flat path -> value map, used to compare an approved document with the model's."""
    return {leaf.path: leaf.value for leaf in walk(doc).leaves}


def set_at_path(root: Any, path: str, value: str) -> None:
    """Set a value inside a copy of the model's response, at a path ``walk`` produced.

    The surrounding structure, including confidence scores and citations, is left
    exactly as the model wrote it, which is what keeps the approved copy in the
    same schema as the input.
    """
    steps = [s for s in re.sub(r"\[(\d+)\]", r".\1", path).split(".") if s]
    node: Any = root
    for step in steps[:-1]:
        nxt = node[int(step)] if isinstance(node, list) else node.get(step)
        if not isinstance(nxt, (dict, list)):
            return
        node = nxt
    last = steps[-1]
    target = node[int(last)] if isinstance(node, list) else node.get(last)

    if isinstance(target, dict) and "value" in target:
        target["value"] = value          # a wrapped leaf keeps its wrapper
    elif isinstance(target, dict) and "content" in target:
        target["content"] = value
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
