"""015 US4／FR-007：HTML 爬蟲與 PTT 回 200 但 selector 對到 0 個節點＝來源失敗；篩選後才變 0、RSS 0 篇都不算。"""
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import collector  # noqa: E402

_EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'

PATCH = {"name": "FFXIV Lodestone JP 更新資訊", "type": "html_patch",
         "url": "https://lodestone.test/news", "selector": "li.news__list", "title_selector": "a"}
FORUM = {"name": "FFXIV JP Forum - PLL", "type": "html_forum", "url": "https://forum.test/553"}
PTT = {"name": "PTT/biker", "type": "ptt", "board": "biker"}
PTT_URL = "https://www.ptt.cc/bbs/biker/index.html"
RSS = {"name": "FFXIV RSS", "type": "rss", "url": "https://rss.test", "content_type": "ffxiv"}

# 改版後 class 換了：selector 一個都對不到
PATCH_ZERO = '<ul><li class="news__list--topics"><a href="/n/1">アップデート情報</a></li></ul>'
PATCH_FILTERED = '<ul><li class="news__list"><a href="/n/1">ab</a></li></ul>'  # 對到 1 個，標題太短被篩掉
PATCH_OK = '<ul><li class="news__list"><a href="/n/1">パッチ7.4 アップデート</a></li></ul>'
# 頁面有連結，但沒有一個是 threads/<數字>
FORUM_ZERO = '<a href="forums/553-PLL">プロデューサーレターLIVE</a><a href="member.php/1-x">someone</a>'
FORUM_FILTERED = '<a href="threads/123-x">ab</a>'  # 對到 1 個，標題太短被篩掉
PTT_ZERO = '<div class="r-list-container bbs-screen"></div>'
PTT_BELOW = ('<div class="r-ent"><div class="nrec"><span>2</span></div>'
             '<div class="title"><a href="/bbs/biker/M.1.A.html">[問題] 測試</a></div></div>')


def _zero_line(name):
    return f"{name}: 回 200 但解析出 0 項（selector 可能失效）"


def _resp(html, error=None):
    resp = MagicMock()
    resp.text = html
    if error:
        resp.raise_for_status.side_effect = requests.HTTPError(error)
    return resp


def _collect(sources, pages, caplog):
    def get(url, **_):
        return pages[url]
    with patch("requests.get", side_effect=get), \
         patch("requests.Session.get", side_effect=get), \
         patch.object(collector, "_fetch_rss_bytes", return_value=_EMPTY_RSS), \
         patch.object(collector.time, "sleep"), \
         caplog.at_level(logging.INFO, logger="src.collector"):
        articles = collector.collect_sources(sources)
    return articles, collector.last_collect_failures()


@pytest.mark.parametrize("source, url, html", [
    (PATCH, PATCH["url"], PATCH_ZERO),
    (FORUM, FORUM["url"], FORUM_ZERO),
    (PTT, PTT_URL, PTT_ZERO),
], ids=["html_patch", "html_forum", "ptt"])
def test_zero_parsed_nodes_is_a_source_failure(source, url, html, caplog):
    articles, failures = _collect([source], {url: _resp(html)}, caplog)
    assert articles == []
    assert failures == ([source["name"]], 1)
    assert _zero_line(source["name"]) in caplog.text
    assert f"來源失敗：1/1（{source['name']}）" in caplog.text


@pytest.mark.parametrize("source, url, html", [
    (PATCH, PATCH["url"], PATCH_FILTERED),
    (FORUM, FORUM["url"], FORUM_FILTERED),
    (PTT, PTT_URL, PTT_BELOW),
], ids=["html_patch", "html_forum", "ptt-below-min-pushes"])
def test_zero_after_filtering_is_not_a_failure(source, url, html, caplog):
    articles, failures = _collect([source], {url: _resp(html)}, caplog)
    assert articles == []
    assert failures == ([], 1)
    assert _zero_line(source["name"]) not in caplog.text


def test_parsed_items_are_not_a_failure(caplog):
    articles, failures = _collect([PATCH], {PATCH["url"]: _resp(PATCH_OK)}, caplog)
    assert [a["title"] for a in articles] == ["パッチ7.4 アップデート"]
    assert failures == ([], 1)
    assert _zero_line(PATCH["name"]) not in caplog.text


def test_empty_rss_is_not_a_failure(caplog):
    articles, failures = _collect([RSS], {}, caplog)
    assert articles == []
    assert failures == ([], 1)
    assert _zero_line(RSS["name"]) not in caplog.text


@pytest.mark.parametrize("source, url", [
    (PATCH, PATCH["url"]),
    (FORUM, FORUM["url"]),
    (PTT, PTT_URL),
], ids=["html_patch", "html_forum", "ptt"])
def test_http_error_is_counted_once_and_not_as_parsed_zero(source, url, caplog):
    _, failures = _collect([source], {url: _resp("", error="403 Client Error: Forbidden")}, caplog)
    assert failures == ([source["name"]], 1)
    assert f"{source['name']} 失敗: 403 Client Error" in caplog.text
    assert _zero_line(source["name"]) not in caplog.text


def test_summary_line_counts_parsed_zero_alongside_other_sources(caplog):
    patch_ok = {**PATCH, "name": "Lodestone OK", "url": "https://lodestone.test/ok"}
    ptt_quiet = {"name": "PTT/SuperBike", "type": "ptt", "board": "SuperBike"}
    sources = [PATCH, FORUM, PTT, ptt_quiet, RSS, patch_ok]
    pages = {
        PATCH["url"]: _resp(PATCH_ZERO),
        FORUM["url"]: _resp(FORUM_ZERO),
        PTT_URL: _resp(PTT_ZERO),
        "https://www.ptt.cc/bbs/SuperBike/index.html": _resp(PTT_BELOW),
        patch_ok["url"]: _resp(PATCH_OK),
    }
    _, failures = _collect(sources, pages, caplog)
    assert failures == ([PATCH["name"], FORUM["name"], PTT["name"]], 6)
    assert f"來源失敗：3/6（{PATCH['name']}、{FORUM['name']}、{PTT['name']}）" in caplog.text
