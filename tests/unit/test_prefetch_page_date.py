"""GNS-20261108-a7k：充實後用媒體頁日期再跑一次年齡門檻；舊文不進 buffer，逐篇與整批各印一行。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import src.gn_resolver as gn  # noqa: E402
from src.pipeline.traffic import TrafficCategory  # noqa: E402

OLD_GN, NEW_GN = "https://news.google.com/rss/articles/OLD", "https://news.google.com/rss/articles/NEW"
OLD_URL, NEW_URL = "https://news.pts.org.tw/article/1", "https://udn.com/news/story/2"
FRESH = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def _prefetch(monkeypatch, caplog, articles, dates):
    monkeypatch.setattr(gn, "resolve_gn_link", lambda s, link: {OLD_GN: OLD_URL, NEW_GN: NEW_URL}[link])
    monkeypatch.setattr(gn, "fetch_og_meta", lambda s, url: ("摘要" * 30, "", dates[url]))
    monkeypatch.setattr(gn.time, "sleep", lambda *_: None)
    with caplog.at_level(logging.INFO, logger="src.pipeline.traffic"):
        return TrafficCategory().prefetch(articles)


def _art(title, link):
    return {"title": title, "link": link, "summary": "", "image": "", "source": "Google News 交通安全教育",
            "published": "2026-09-14T07:00:00+00:00"}


def test_old_page_date_is_dropped_with_reason(monkeypatch, caplog):
    kept = _prefetch(monkeypatch, caplog, [_art("舊文", OLD_GN), _art("新文", NEW_GN)],
                     {OLD_URL: "2019-03-05T08:00:00+00:00", NEW_URL: FRESH})
    assert [a["title"] for a in kept] == ["新文"]
    assert "[充實後過時] 擋下：news.pts.org.tw 日期 2019-03-05「舊文」" in caplog.text
    assert "[充實後過時] 擋下 1/2 篇（充實後的日期早於 30 天前）" in caplog.text


def test_summary_line_is_printed_when_nothing_is_dropped(monkeypatch, caplog):
    kept = _prefetch(monkeypatch, caplog, [_art("新文", NEW_GN)], {NEW_URL: FRESH})
    assert [a["title"] for a in kept] == ["新文"]
    assert "[充實後過時] 擋下 0/1 篇（充實後的日期早於 30 天前）" in caplog.text
