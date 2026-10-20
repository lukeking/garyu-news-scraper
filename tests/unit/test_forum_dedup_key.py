"""spec 015 T010：帶 dedup_key 的論壇項目略過跨週標題指紋（以回覆去重），年齡檢查照做。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import freshness_filter, title_fingerprint  # noqa: E402

SKIP_LINE = "跨週去重略過標題指紋（以回覆去重）"


def _article(title, days_ago=1, dedup_key=None):
    published = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    a = {"title": title, "link": f"https://x/{title}", "published": published, "content_type": "ffxiv"}
    if dedup_key:
        a["dedup_key"] = dedup_key
    return a


def _run(articles, fingerprints, caplog):
    with caplog.at_level(logging.INFO, logger="src.filter"):
        return freshness_filter(articles, fingerprints)


def test_forum_item_is_kept_even_when_its_title_fingerprint_is_known(caplog):
    forum = _article("獣使いスレ", dedup_key="forum:498925:6851335")
    kept = _run([forum], {title_fingerprint(forum)}, caplog)
    assert kept == [forum]
    assert f"{SKIP_LINE}：獣使いスレ" in caplog.text
    assert "跨週去重跳過" not in caplog.text


def test_forum_item_still_goes_through_the_age_check(caplog):
    old = _article("古い串", days_ago=40, dedup_key="forum:1:2")
    assert _run([old], set(), caplog) == []
    assert "過時文章跳過：古い串" in caplog.text


def test_skip_line_cuts_the_title_to_fifty_chars(caplog):
    title = "長" * 50 + "尾"
    _run([_article(title, dedup_key="forum:1:3")], set(), caplog)
    assert f"{SKIP_LINE}：{'長' * 50}" in caplog.text
    assert "尾" not in caplog.text


def test_articles_without_dedup_key_behave_as_before(caplog):
    seen = _article("先週の記事")
    fresh = _article("新しい記事")
    kept = _run([seen, fresh], {title_fingerprint(seen)}, caplog)
    assert kept == [fresh]
    assert "跨週去重跳過：先週の記事" in caplog.text
    assert SKIP_LINE not in caplog.text
