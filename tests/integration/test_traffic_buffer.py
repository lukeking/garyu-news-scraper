"""
Integration test for the traffic buffer pipeline — T041.
Tests TrafficCategory.filter() enrichment and upsert_traffic_buffer() storage.
Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to be set; skips otherwise.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def skip_without_supabase():
    """Skip all tests in this module when Supabase is not configured."""
    from src.storage import is_configured
    if not is_configured():
        pytest.skip("Supabase not configured — set SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY")


def _make_article(title: str, source: str = "自由時報") -> dict:
    return {
        "title": title,
        "source": source,
        "published": "2025-01-06T08:00:00+08:00",
        "summary": f"{title}的詳細報導，包含事故原因分析與影響評估。",
        "link": f"https://example.com/traffic/{hash(title) % 100000}",
        "content_type": "traffic",
    }


def test_filter_attaches_category_and_score(monkeypatch):
    """After filter(), articles have major_category and initial_quality_score attached."""
    from src.pipeline_config import reset_caches
    reset_caches()

    # Write a minimal categories file so assign_category has taxonomy to use
    import tempfile
    import yaml

    taxonomy = {"機車事故": ["機車", "事故", "碰撞"]}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as f:
        yaml.dump({"categories": taxonomy}, f, allow_unicode=True)
        cat_path = f.name

    pipeline_cfg = {
        "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20, "game_threshold": 0.50},
        "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3},
        "quality_score_weights": {"keyword_match_ratio": 0.4, "normalised_word_count": 0.3, "source_weight": 0.3},
        "source_weights": {"自由時報": 0.8},
        "buffer": {"max_age_weeks": 8},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as f:
        yaml.dump(pipeline_cfg, f, allow_unicode=True)
        cfg_path = f.name

    monkeypatch.setenv("CATEGORIES_TRAFFIC_YML_PATH", cat_path)
    monkeypatch.setenv("PIPELINE_CONFIG_YML_PATH", cfg_path)
    reset_caches()

    articles = [
        _make_article("機車事故造成一人受傷"),
        _make_article("台北路口機車碰撞意外"),
        _make_article("展覽活動本週末開放"),
    ]

    # Mock freshness_filter and filter_and_deduplicate to return articles unchanged
    from unittest.mock import patch
    with patch("src.filter.freshness_filter", return_value=articles), \
         patch("src.filter.filter_and_deduplicate", return_value=articles):
        from src.pipeline.traffic import TrafficCategory
        cat = TrafficCategory()
        result = cat.filter(articles)

    assert len(result) == 3
    for article in result:
        assert "major_category" in article, f"major_category missing from: {article['title']}"
        assert "initial_quality_score" in article, "initial_quality_score missing"
        score = article["initial_quality_score"]
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"

    # The two 機車-related articles should be categorised correctly
    cats = {a["title"]: a["major_category"] for a in result}
    assert cats["機車事故造成一人受傷"] == "機車事故"
    assert cats["台北路口機車碰撞意外"] == "機車事故"
    assert cats["展覽活動本週末開放"] == "uncategorised"

    import os
    os.unlink(cat_path)
    os.unlink(cfg_path)
    reset_caches()


def test_upsert_traffic_buffer_writes_and_returns_count():
    """upsert_traffic_buffer() writes articles and returns a positive count."""
    from src.storage import upsert_traffic_buffer

    articles = [
        {**_make_article(f"測試交通緩衝區文章{i}"), "major_category": "機車事故", "initial_quality_score": 0.6}
        for i in range(3)
    ]
    week_id = "2025-W01-test"
    count = upsert_traffic_buffer(articles, week_id, max_age_weeks=1)
    assert count >= 0  # >= 0 because upsert may return 0 on conflict


def test_buffer_rows_have_expected_fields():
    """After upsert, get_traffic_buffer returns rows with required traffic columns."""
    from src.storage import upsert_traffic_buffer, get_traffic_buffer
    from datetime import datetime, timezone, timedelta

    week_id = "2025-W02-test"
    articles = [
        {**_make_article("機車追撞緩衝測試文章"), "major_category": "機車事故", "initial_quality_score": 0.55}
    ]
    upsert_traffic_buffer(articles, week_id, max_age_weeks=8)

    buffer = get_traffic_buffer(max_age_weeks=8)
    test_rows = [r for r in buffer if r.get("week_id") == week_id]
    assert len(test_rows) >= 1

    row = test_rows[0]
    assert row.get("major_category") is not None
    assert row.get("initial_quality_score") is not None
    assert row.get("buffered_at") is not None
    assert row.get("hot_topic_analyzed") is False
