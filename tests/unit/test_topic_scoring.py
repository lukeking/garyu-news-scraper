"""
Unit tests for cluster_traffic_articles(), score_topic_buckets(), select_hot_topics() — US3.
"""
import math
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import cluster_traffic_articles, score_topic_buckets, select_hot_topics

_BASE_CONFIG = {
    "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3},
}


def _article(title: str, category: str = "酒駕", quality: float = 0.5,
             source: str = "自由時報", pub: str = "2025-01-01") -> dict:
    return {
        "title": title,
        "major_category": category,
        "initial_quality_score": quality,
        "source": source,
        "published": f"{pub}T00:00:00",
        "summary": "測試摘要",
    }


# ── cluster_traffic_articles ──────────────────────────────────────────────────

def test_cluster_jaccard_range_same_bucket():
    """Two articles with Jaccard 0.333 (in [0.20, 0.45]) should land in same bucket."""
    a1 = _article("標題甲")
    a2 = _article("標題乙")
    # Intersection=2, union=6 → Jaccard=0.333
    ts_map = {
        "標題甲": frozenset(["酒駕", "肇事", "機車", "台北"]),
        "標題乙": frozenset(["酒駕", "肇事", "事故", "台中"]),
    }
    with patch("src.filter.normalise_title", side_effect=lambda t: ts_map.get(t, frozenset())):
        buckets = cluster_traffic_articles([a1, a2], _BASE_CONFIG)
    assert len(buckets) == 1
    assert sum(len(v) for v in buckets.values()) == 2


def test_cluster_dedup_lower_word_count_discarded():
    """Two articles with Jaccard 0.667 (> 0.45) → near-duplicate; lower word-count is discarded."""
    short_article = _article("標題短", source="聯合")
    short_article["summary"] = "短"
    long_article = _article("標題長", source="蘋果")
    long_article["summary"] = "這是一篇非常詳細的長文章，包含大量交通事故分析資訊" * 5

    # Intersection=4, union=6 → Jaccard=0.667
    ts_map = {
        "標題短": frozenset(["酒駕", "肇事", "機車", "台北", "事故"]),
        "標題長": frozenset(["酒駕", "肇事", "機車", "台北", "嚴重"]),
    }
    with patch("src.filter.normalise_title", side_effect=lambda t: ts_map.get(t, frozenset())):
        buckets = cluster_traffic_articles([short_article, long_article], _BASE_CONFIG)

    all_articles = [a for bucket in buckets.values() for a in bucket]
    assert len(all_articles) == 1
    assert all_articles[0]["title"] == "標題長"


def test_cluster_different_categories_separate_buckets():
    """Articles in different major_categories never share a bucket."""
    a1 = _article("酒駕事故標題", category="酒駕")
    a2 = _article("道路施工標題", category="道路施工")
    ts_map = {
        "酒駕事故標題": frozenset(["酒駕", "事故", "機車"]),
        "道路施工標題": frozenset(["酒駕", "事故", "機車"]),  # same tokens, but different category
    }
    with patch("src.filter.normalise_title", side_effect=lambda t: ts_map.get(t, frozenset())):
        buckets = cluster_traffic_articles([a1, a2], _BASE_CONFIG)
    assert len(buckets) == 2


def test_cluster_low_jaccard_separate_buckets():
    """Two articles with Jaccard < 0.20 (below cluster_lower) go into separate buckets."""
    a1 = _article("標題甲")
    a2 = _article("標題乙")
    ts_map = {
        "標題甲": frozenset(["A", "B", "C", "D", "E", "F", "G", "H"]),
        "標題乙": frozenset(["A", "I", "J", "K", "L", "M", "N", "O"]),
        # Intersection=1, union=15 → Jaccard=1/15≈0.067 < 0.20
    }
    with patch("src.filter.normalise_title", side_effect=lambda t: ts_map.get(t, frozenset())):
        buckets = cluster_traffic_articles([a1, a2], _BASE_CONFIG)
    assert len(buckets) == 2


# ── score_topic_buckets ───────────────────────────────────────────────────────

def test_score_source_diversity_factor():
    """Bucket with 5 articles from 3 sources/3 days should score higher than
    10 articles from 1 source/1 day (validates log diversity factor)."""
    single_source_bucket = {
        "bucket_a": [
            _article(f"同源新聞{i}", source="自由時報", quality=0.5, pub="2025-01-01")
            for i in range(10)
        ]
    }
    diverse_bucket = {
        "bucket_b": [
            _article(f"多源新聞{i}",
                     source=["自由時報", "聯合新聞", "蘋果新聞"][i % 3],
                     quality=0.5,
                     pub=f"2025-01-0{(i % 3) + 1}")
            for i in range(5)
        ]
    }

    score_a = score_topic_buckets(single_source_bucket, _BASE_CONFIG)["bucket_a"]
    score_b = score_topic_buckets(diverse_bucket, _BASE_CONFIG)["bucket_b"]
    assert score_b > score_a, (
        f"Diverse bucket (score={score_b:.3f}) should beat single-source (score={score_a:.3f})"
    )


def test_score_formula_correctness():
    """Verify the formula: sum(q) × log(sources+1) × log(days+1)."""
    articles = [
        _article("A", quality=0.5, source="自由時報", pub="2025-01-01"),
        _article("B", quality=0.5, source="聯合新聞", pub="2025-01-02"),
    ]
    buckets = {"bucket_x": articles}
    scores = score_topic_buckets(buckets, _BASE_CONFIG)
    expected = 1.0 * math.log(3) * math.log(3)
    assert abs(scores["bucket_x"] - expected) < 1e-9


def test_score_empty_bucket():
    """Empty bucket should score 0.0."""
    scores = score_topic_buckets({"b0": []}, _BASE_CONFIG)
    assert scores["b0"] == 0.0


# ── select_hot_topics ─────────────────────────────────────────────────────────

def test_select_below_threshold_excluded():
    """Buckets below min_threshold are excluded from hot topics."""
    bucket_scores = {"b_low": 0.5, "b_high": 3.0, "b_mid": 1.5}
    result = select_hot_topics(bucket_scores, _BASE_CONFIG)
    assert "b_low" not in result
    assert "b_high" in result
    assert "b_mid" in result  # exactly at threshold → included


def test_select_sorted_by_score_descending():
    """Hot topics are returned in descending score order."""
    bucket_scores = {"b1": 2.0, "b2": 5.0, "b3": 3.5}
    result = select_hot_topics(bucket_scores, _BASE_CONFIG)
    assert result[0] == "b2"
    assert result[1] == "b3"
    assert result[2] == "b1"


def test_select_max_hot_topics_cap():
    """Result is capped at max_hot_topics (default 3)."""
    bucket_scores = {f"b{i}": float(i + 2) for i in range(10)}
    result = select_hot_topics(bucket_scores, _BASE_CONFIG)
    assert len(result) == 3


def test_select_none_qualify():
    """When no bucket meets the threshold, empty list is returned."""
    bucket_scores = {"b1": 0.1, "b2": 0.5}
    result = select_hot_topics(bucket_scores, _BASE_CONFIG)
    assert result == []
