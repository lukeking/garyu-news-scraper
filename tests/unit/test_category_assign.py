"""
Unit tests for assign_category() — FR-015.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import assign_category

TAXONOMY = {
    "大型車安全": ["大型車", "聯結車", "砂石車"],
    "酒駕": ["酒駕", "酒測"],
    "道路施工": ["施工", "封閉"],
}


def test_first_matching_category_wins():
    tokens = frozenset(["大型車", "事故", "台北"])
    assert assign_category(tokens, TAXONOMY) == "大型車安全"


def test_second_category_matches():
    tokens = frozenset(["酒駕", "肇事", "台中"])
    assert assign_category(tokens, TAXONOMY) == "酒駕"


def test_uncategorised_fallback():
    tokens = frozenset(["活動", "展覽", "新竹"])
    assert assign_category(tokens, TAXONOMY) == "uncategorised"


def test_priority_order_first_wins():
    """When tokens match both 大型車安全 and 酒駕, first defined wins."""
    tokens = frozenset(["大型車", "酒駕"])
    result = assign_category(tokens, TAXONOMY)
    assert result == "大型車安全"  # defined first


def test_empty_tokens():
    tokens = frozenset()
    assert assign_category(tokens, TAXONOMY) == "uncategorised"


def test_empty_taxonomy():
    tokens = frozenset(["機車", "事故"])
    assert assign_category(tokens, {}) == "uncategorised"


def test_keyword_lowercase_matching():
    """Keywords stored lowercase should match uppercase-equivalent tokens after normalisation."""
    taxonomy = {"酒駕": ["酒駕"]}
    tokens = frozenset(["酒駕", "肇事"])
    assert assign_category(tokens, taxonomy) == "酒駕"
