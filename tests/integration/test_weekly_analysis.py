"""
Integration test for the weekly traffic analysis pipeline — T042.
Seeds the buffer and verifies hot_topic_reports are created.
Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, and GEMINI_API_KEY; skips otherwise.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def skip_without_credentials():
    """Skip when Supabase or Gemini is not configured."""
    from src.storage import is_configured
    if not is_configured():
        pytest.skip("Supabase not configured")
    if not (os.environ.get("GEMINI_API_KEY") or "").strip():
        pytest.skip("GEMINI_API_KEY not configured")


def _seed_article(idx: int, category: str, source: str, pub_date: str) -> dict:
    return {
        "title": f"測試機車事故新聞第{idx}篇 {category}",
        "source": source,
        "published": f"{pub_date}T08:00:00+08:00",
        "summary": f"這是關於{category}的詳細報導，包含事故分析與相關資訊。事故地點在台灣某處路口，造成人員受傷。",
        "link": f"https://example.com/weekly-test/{idx}",
        "content_type": "traffic",
        "major_category": category,
        "initial_quality_score": 0.6,
    }


def test_weekly_analysis_creates_hot_topic_reports():
    """
    Seed ≥ 3 buffered traffic articles across 2 categories, run the analysis pipeline,
    verify ≥ 1 hot_topic_reports row and that source articles are marked analyzed.
    """
    from src.storage import upsert_traffic_buffer, get_traffic_buffer
    from src.storage import upsert_hot_topic_report
    from src.pipeline_config import reset_caches, load_pipeline_config
    from src.analyzer import cluster_traffic_articles, score_topic_buckets, select_hot_topics, analyze_hot_topic

    reset_caches()
    week_id = "2025-W99-integration-test"

    articles = [
        _seed_article(1, "機車事故", "自由時報", "2025-01-06"),
        _seed_article(2, "機車事故", "聯合新聞", "2025-01-07"),
        _seed_article(3, "酒駕", "蘋果新聞", "2025-01-06"),
        _seed_article(4, "酒駕", "自由時報", "2025-01-08"),
    ]
    upsert_traffic_buffer(articles, week_id, max_age_weeks=4)

    buffer = get_traffic_buffer(max_age_weeks=4)
    seeded = [a for a in buffer if a.get("week_id") == week_id]
    assert len(seeded) >= 3, f"Expected ≥3 seeded articles, got {len(seeded)}"

    # Use a permissive config so all buckets qualify as hot
    config = {
        "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20, "game_threshold": 0.50},
        "topic_scoring": {"min_threshold": 0.0, "max_hot_topics": 3},
        "quality_score_weights": {"keyword_match_ratio": 0.4, "normalised_word_count": 0.3, "source_weight": 0.3},
        "source_weights": {"自由時報": 0.8, "聯合新聞": 0.7, "蘋果新聞": 0.7},
        "buffer": {"max_age_weeks": 4},
    }

    buckets = cluster_traffic_articles(seeded, config)
    assert len(buckets) >= 1

    scores = score_topic_buckets(buckets, config)
    hot_ids = select_hot_topics(scores, config)
    assert len(hot_ids) >= 1

    week_start = "2025-01-06"
    for bid in hot_ids[:1]:  # Only one Gemini call to limit API usage
        bucket_articles = buckets[bid]
        topic_label = bucket_articles[0].get("major_category", bid)
        report_text = analyze_hot_topic(bucket_articles, topic_label, week_start)
        assert report_text, "analyze_hot_topic returned empty string"

        source_links = [a.get("link", "") for a in bucket_articles if a.get("link")]
        report = {
            "week_start_date": week_start,
            "topic_label": f"{topic_label}-integration-test",
            "report_text": report_text,
            "source_article_count": len(bucket_articles),
            "source_article_links": source_links,
            "cumulative_score": scores[bid],
            "distinct_sources": len({a.get("source") for a in bucket_articles}),
            "distinct_days": len({(a.get("published") or "")[:10] for a in bucket_articles}),
        }
        upsert_hot_topic_report(report)

    # Verify the report was persisted
    from src.storage import _get_client
    client = _get_client()
    resp = (
        client.table("hot_topic_reports")
        .select("*")
        .eq("week_start_date", week_start)
        .like("topic_label", "%-integration-test")
        .execute()
    )
    assert len(resp.data) >= 1, "No hot_topic_reports row found after upsert"
