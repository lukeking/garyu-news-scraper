"""
Unit tests for compute_jaccard() — FR-005.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import compute_jaccard


def test_identical_sets():
    a = frozenset(["機車", "事故", "台北"])
    assert compute_jaccard(a, a) == pytest.approx(1.0)


def test_disjoint_sets():
    a = frozenset(["機車", "事故"])
    b = frozenset(["酒駕", "肇事"])
    assert compute_jaccard(a, b) == pytest.approx(0.0)


def test_partial_overlap():
    a = frozenset(["機車", "事故", "台北"])
    b = frozenset(["機車", "事故", "高雄"])
    # intersection=2, union=4 → 0.5
    assert compute_jaccard(a, b) == pytest.approx(0.5)


def test_empty_set_a():
    b = frozenset(["機車", "事故"])
    assert compute_jaccard(frozenset(), b) == pytest.approx(0.0)


def test_empty_set_b():
    a = frozenset(["機車", "事故"])
    assert compute_jaccard(a, frozenset()) == pytest.approx(0.0)


def test_both_empty():
    assert compute_jaccard(frozenset(), frozenset()) == pytest.approx(0.0)


def test_boundary_cluster_lower():
    """Score in the cluster range 0.20–0.45 should be detectable."""
    # |{A,B,C,D} ∩ {A,B,E,F}| = 2, |union| = 6 → Jaccard = 1/3 ≈ 0.333
    a = frozenset(["A", "B", "C", "D"])
    b = frozenset(["A", "B", "E", "F"])
    score = compute_jaccard(a, b)
    assert 0.20 <= score <= 0.45


def test_above_merge_threshold():
    """Score > 0.45 should trigger dedup."""
    a = frozenset(["機車", "事故", "台北", "路口"])
    b = frozenset(["機車", "事故", "台北", "路口", "死亡"])
    score = compute_jaccard(a, b)
    assert score > 0.45


def test_game_threshold_boundary():
    """Two near-identical game titles should score > 0.50."""
    a = frozenset(["FFXIV", "7.2", "更新", "職業", "調整"])
    b = frozenset(["FFXIV", "7.2", "更新", "職業", "平衡"])
    score = compute_jaccard(a, b)
    assert score > 0.50
