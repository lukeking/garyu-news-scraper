"""
Unit tests for policy-source filter gates:
relevance_exempt bypass, lookback-aware stale gate, per-source stamping,
and the traffic buffer fingerprint/upsert fixes.
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import _is_stale_article, filter_and_deduplicate


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _policy_article(**overrides) -> dict:
    """道安會報-style article: no motorcycle keyword anywhere."""
    article = {
        "title": "臺東縣6月道安會報 王副縣長指示做好熱氣球活動交通規劃",
        "summary": "縣府召開道路交通安全聯席會報",
        "source": "Google News 道安會報",
        "published": _iso_days_ago(2),
        "content_type": "traffic",
        "link": "https://news.google.com/rss/articles/abc123",
    }
    article.update(overrides)
    return article


# ── relevance_exempt bypasses MUST_INCLUDE ────────────────────────────────────

def test_exempt_article_survives_without_motorcycle_keyword():
    kept = filter_and_deduplicate([_policy_article(relevance_exempt=True)], throttle=False)
    assert len(kept) == 1


def test_non_exempt_article_still_requires_motorcycle_keyword():
    kept = filter_and_deduplicate([_policy_article()], throttle=False)
    assert kept == []


# ── stale gate honours per-source lookback_days ───────────────────────────────

def test_lookback_article_older_than_14_days_not_stale():
    """15–30 天文章：收集端已按 lookback 視窗把關，14 天啟發式不得再丟。"""
    assert _is_stale_article(_policy_article(published=_iso_days_ago(20), lookback_days=30)) is False


def test_default_article_older_than_14_days_is_stale():
    assert _is_stale_article(_policy_article(published=_iso_days_ago(20))) is True


def test_old_year_signal_still_applies_with_lookback():
    """信號 1（標題出現過舊年份）不受 lookback 豁免影響。"""
    old_year = datetime.now().year - 2
    article = _policy_article(
        title=f"道安會報回顧 {old_year}", published=_iso_days_ago(2), lookback_days=30
    )
    assert _is_stale_article(article) is True


# ── collect_sources stamps per-source config onto articles ────────────────────

def test_collect_sources_stamps_exempt_and_lookback():
    from src import collector

    fake_articles = [{"title": "a"}, {"title": "b"}]
    with patch.dict(collector.FETCHERS, {"rss": lambda source: [dict(a) for a in fake_articles]}), \
         patch.object(collector.time, "sleep"):
        stamped = collector.collect_sources(
            [{"name": "s1", "type": "rss", "relevance_exempt": True, "lookback_days": 30}]
        )
        plain = collector.collect_sources([{"name": "s2", "type": "rss"}])

    assert all(a["relevance_exempt"] is True and a["lookback_days"] == 30 for a in stamped)
    assert all("relevance_exempt" not in a and "lookback_days" not in a for a in plain)


# ── traffic buffer: title-only fingerprint + non-destructive upsert ───────────

def _capture_upsert(articles):
    from src import storage

    client = MagicMock()
    upsert_mock = client.table.return_value.upsert
    upsert_mock.return_value.execute.return_value.data = []
    with patch.object(storage, "_get_client", return_value=client):
        storage.upsert_traffic_buffer(articles, week_id="2026-W28")
    return upsert_mock.call_args


def test_buffer_fingerprint_matches_freshness_filter_read_path():
    from src.filter import title_fingerprint

    article = _policy_article()
    call = _capture_upsert([article])
    rows = call.args[0]
    assert rows[0]["content_fingerprint"] == title_fingerprint(article)


def test_buffer_upsert_never_overwrites_existing_links():
    call = _capture_upsert([_policy_article()])
    assert call.kwargs["on_conflict"] == "link"
    assert call.kwargs["ignore_duplicates"] is True
