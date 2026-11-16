"""The walker is the only part of this app that has to understand a shape, so
these fixtures are the real output shapes of three AI functions, trimmed.
If a future AI function arrives with a fourth shape, add it here first.
"""

import copy

from review.walk import set_at_path, values_by_path, walk

AI_EXTRACT = {
    "response": {
        "merchant_name": {"value": "Walgreens", "confidence_score": 1.0, "citation_ids": [3]},
        "tax_amount": {"value": None, "confidence_score": None, "citation_ids": []},
        "line_items": [
            {"amount": {"value": "4.99", "confidence_score": 1.0, "citation_ids": [7]}},
            {"amount": {"value": "3.79", "confidence_score": 0.6, "citation_ids": [7]}},
        ],
    },
    "metadata": {
        "citations": [
            {"id": 3, "bbox": [{"coord": [51, 660, 1457, 1481], "page_id": 0}]},
            {"id": 7, "bbox": [{"coord": [10, 20, 30, 40], "page_id": 1}]},
        ],
        "pages": [
            {"id": 0, "image_uri": "/Volumes/c/s/v/page0.jpg"},
            {"id": 1, "image_uri": "/Volumes/c/s/v/page1.jpg"},
        ],
    },
}

AI_PARSE_DOCUMENT = {
    "document": {
        "elements": [
            {"id": 0, "type": "text", "content": "OLD NAVY - 03788", "confidence": 0.9,
             "bbox": [{"coord": [48, 109, 583, 402], "page_id": 0}]},
            {"id": 1, "type": "table", "content": "DATE | CHARGES", "confidence": 0.81,
             "bbox": [{"coord": [1, 2, 3, 4], "page_id": 0}]},
        ],
        "pages": [{"id": 0, "image_uri": "/Volumes/c/s/v/parse0.jpg"}],
    },
    "metadata": {"version": "2.0"},
}

AI_CLASSIFY = {
    "response": {
        "expense_category": {"value": "lodging"},
        "reimbursable": {"value": "reimbursable"},
    },
    "metadata": {"citations": [], "pages": [{"id": 0, "image_uri": "/Volumes/c/s/v/classify0.jpg"}]},
}


class TestAiExtract:
    def test_discovers_every_scalar_and_array_leaf(self):
        assert [l.path for l in walk(AI_EXTRACT).leaves] == [
            "response.merchant_name",
            "response.tax_amount",
            "response.line_items[0].amount",
            "response.line_items[1].amount",
        ]

    def test_array_leaves_carry_group_and_index(self):
        leaves = walk(AI_EXTRACT).leaves
        assert [(l.group_name, l.item_index) for l in leaves if l.group_name] == [
            ("response.line_items", 0),
            ("response.line_items", 1),
        ]
        assert leaves[0].group_name is None

    def test_array_leaves_share_an_index_free_type_key(self):
        leaves = walk(AI_EXTRACT).leaves
        assert leaves[2].type_key == "response.line_items.amount"
        assert leaves[3].type_key == leaves[2].type_key

    def test_unwraps_value_confidence_and_citations(self):
        leaf = walk(AI_EXTRACT).leaves[0]
        assert (leaf.value, leaf.confidence, leaf.citation_ids) == ("Walgreens", 1.0, [3])

    def test_a_value_the_model_never_found_is_none(self):
        leaf = walk(AI_EXTRACT).leaves[1]
        assert leaf.value is None and leaf.confidence is None

    def test_indexes_citations_and_page_images(self):
        w = walk(AI_EXTRACT)
        assert w.citations[3] == {"coord": [51, 660, 1457, 1481], "page_id": 0}
        assert w.page_images[1] == "page1.jpg"

    def test_numeric_looking_strings_get_the_number_widget(self):
        leaves = walk(AI_EXTRACT).leaves
        assert leaves[2].kind == "number"
        assert leaves[0].kind == "text"


class TestAiParseDocument:
    def test_each_element_is_one_leaf(self):
        assert [l.path for l in walk(AI_PARSE_DOCUMENT).leaves] == [
            "document.elements[0].content",
            "document.elements[1].content",
        ]

    def test_element_type_lands_in_the_type_key(self):
        assert [l.type_key for l in walk(AI_PARSE_DOCUMENT).leaves] == [
            "document.elements.text",
            "document.elements.table",
        ]

    def test_evidence_is_read_from_the_leaf_itself(self):
        leaf = walk(AI_PARSE_DOCUMENT).leaves[0]
        assert leaf.coord == [48, 109, 583, 402] and leaf.page_id == 0 and leaf.citation_ids == []

    def test_confidence_comes_from_the_element_field(self):
        assert [l.confidence for l in walk(AI_PARSE_DOCUMENT).leaves] == [0.9, 0.81]

    def test_pages_are_found_under_document(self):
        assert walk(AI_PARSE_DOCUMENT).page_images[0] == "parse0.jpg"


class TestAiClassify:
    def test_wrapped_scalars_with_no_confidence_or_citation(self):
        leaves = walk(AI_CLASSIFY).leaves
        assert [(l.path, l.value, l.confidence, l.citation_ids) for l in leaves] == [
            ("response.expense_category", "lodging", None, []),
            ("response.reimbursable", "reimbursable", None, []),
        ]

    def test_page_without_citations_is_still_available(self):
        w = walk(AI_CLASSIFY)
        assert w.citations == {}
        assert w.page_images[0] == "classify0.jpg"


class TestUnrecognisedEnvelopes:
    def test_bare_scalars_are_their_own_values(self):
        leaves = walk({"category": "apparel", "score": 0.5}).leaves
        assert [(l.path, l.value, l.kind) for l in leaves] == [
            ("category", "apparel", "text"),
            ("score", "0.5", "number"),
        ]

    def test_opaque_empty_object_is_one_read_only_leaf(self):
        leaves = walk({"response": {"odd": {}}}).leaves
        assert len(leaves) == 1
        assert leaves[0].path == "response.odd" and leaves[0].kind == "json"

    def test_empty_array_contributes_no_leaves(self):
        assert walk({"response": {"line_items": []}}).leaves == []

    def test_non_objects_do_not_raise(self):
        assert walk(None).leaves == []
        assert walk("a string").leaves == []


class TestOverlay:
    def test_values_by_path_keys_match_the_walker(self):
        approved = copy.deepcopy(AI_EXTRACT)
        approved["response"]["merchant_name"]["value"] = "Walgreens #1234"
        values = values_by_path(approved)
        assert values["response.merchant_name"] == "Walgreens #1234"
        assert values["response.line_items[1].amount"] == "3.79"

    def test_set_at_path_keeps_the_wrapper_and_its_metadata(self):
        doc = copy.deepcopy(AI_EXTRACT)
        set_at_path(doc, "response.line_items[0].amount", "5.49")
        leaf = doc["response"]["line_items"][0]["amount"]
        assert leaf["value"] == "5.49"
        assert leaf["confidence_score"] == 1.0 and leaf["citation_ids"] == [7]

    def test_set_at_path_writes_content_for_parse_elements(self):
        doc = copy.deepcopy(AI_PARSE_DOCUMENT)
        set_at_path(doc, "document.elements[0].content", "OLD NAVY - 03788 (corrected)")
        assert doc["document"]["elements"][0]["content"].endswith("(corrected)")
        assert doc["document"]["elements"][0]["confidence"] == 0.9
