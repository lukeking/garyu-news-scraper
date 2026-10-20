"""spec 015 T016：html_patch 的 date_pattern／exclude_title_prefixes／detail_selector／max_chars 與「解析 N 則」那行。"""
import logging
import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import collector  # noqa: E402

UTC = timezone.utc
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ffxiv")
NAME = "FFXIV Lodestone JP 更新資訊"
LIST_URL = "https://jp.finalfantasyxiv.com/lodestone/news/category/3"
DETAIL = "https://jp.finalfantasyxiv.com/lodestone/news/detail/"
D1020 = DETAIL + "148f852faaa79f79a8542a9450e9361b17940884"
D1013 = DETAIL + "2d2d1673a944a8c0af10be5521aa4d1536a1ff77"
D0919 = DETAIL + "1b6ac6d76ea75f66cfb39e565fcb96e8bf40506d"
LODESTONE_1013 = DETAIL + "f9c53c825f34aa2685737ce7baafcd5e90bc2250"
COMPANION_1013 = DETAIL + "f04be0d48c4a0aaf9ff9b92c2f457861679c6cd9"
# 契約裡的真實設定（contracts/sources-ffxiv-config.md）
SOURCE = {
    "name": NAME, "type": "html_patch", "url": LIST_URL, "enabled": True, "content_type": "ffxiv",
    "weight": 60, "selector": "li.news__list", "title_selector": "p.news__list--title", "max_items": 10,
    "date_pattern": r"ldst_strftime\((\d{10})", "exclude_title_prefixes": ["Lodestone", "コンパニオンアプリ"],
    "detail_selector": "div.news__detail__wrapper", "max_chars": 2000,
}
OPTIONS = ("date_pattern", "exclude_title_prefixes", "detail_selector", "max_chars")
# 剛好等於 10/13 遊戲更新的 ldst_strftime(1791875580)：等於 CUTOFF 算窗口內
CUTOFF_AT_1013 = datetime(2026, 10, 13, 7, 13, tzinfo=UTC)
DETAIL_HEAD = "下記日時におきまして、ファイナルファンタジーXIVのバージョンアップを実施いたしました。 ※下記日時以降に"
DETAIL_TAIL = "今後のパッチでの修正を予定しております。"


def _read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def _resp(html, error=None):
    resp = MagicMock()
    resp.text = html
    if error:
        resp.raise_for_status.side_effect = requests.HTTPError(error)
    return resp


def _pages(**overrides):
    pages = {LIST_URL: _resp(_read("lodestone_category3.html")), D1020: _resp(_read("lodestone_detail.html")),
             D1013: _resp(_read("lodestone_detail.html"))}
    return {**pages, **overrides}


def _collect(source, pages, caplog, cutoff=CUTOFF_AT_1013, events=None):
    events = [] if events is None else events

    def get(url, **_):
        events.append(("get", url))
        page = pages[url]
        if isinstance(page, Exception):
            raise page
        return page

    with patch("requests.get", side_effect=get), \
         patch.object(collector.time, "sleep", side_effect=lambda s: events.append(("sleep", s))), \
         patch.object(collector, "CUTOFF", cutoff), \
         caplog.at_level(logging.INFO, logger="src.collector"):
        articles = collector.collect_sources([source])
    return articles, collector.last_collect_failures()


def _line(n, m, a, b):
    return f"{NAME}: 解析 {n} 則、收進 {m} 則（窗口外 {a}、排除 {b}）"


def _fallback(title, reason):
    return f"{NAME}: {title} 詳細頁抓不到（{reason}），只用標題"


def test_lodestone_config_keeps_in_window_game_updates_with_detail_text(caplog):
    articles, failures = _collect(SOURCE, _pages(), caplog)
    assert [(a["title"], a["link"], a["published"]) for a in articles] == [
        ("更新のお知らせ(10/20)", D1020, "2026-10-20T06:50:00+00:00"),
        ("更新のお知らせ(10/13)", D1013, "2026-10-13T07:13:00+00:00"),
    ]
    for a in articles:
        assert a["summary"].startswith(DETAIL_HEAD) and a["summary"].endswith(DETAIL_TAIL)
        assert len(a["summary"]) == 414
        assert "\n" not in a["summary"] and "  " not in a["summary"]
        assert "更新のお知らせ" not in a["summary"] and "ldst_strftime" not in a["summary"]
        assert (a["source"], a["content_type"], a["source_weight"]) == (NAME, "ffxiv", 60)
    assert failures == ([], 1)
    assert _line(5, 2, 1, 2) in caplog.text
    assert f"{NAME}: 2 筆" in caplog.text


def test_item_exactly_at_cutoff_is_inside_and_one_second_later_is_not(caplog):
    at, _ = _collect(SOURCE, _pages(), caplog, cutoff=datetime(2026, 10, 13, 7, 13, tzinfo=UTC))
    later, _ = _collect(SOURCE, _pages(), caplog, cutoff=datetime(2026, 10, 13, 7, 13, 1, tzinfo=UTC))
    assert [a["title"] for a in at] == ["更新のお知らせ(10/20)", "更新のお知らせ(10/13)"]
    assert [a["title"] for a in later] == ["更新のお知らせ(10/20)"]
    assert _line(5, 1, 2, 2) in caplog.text


def test_exclusion_is_counted_before_the_window(caplog):
    """コンパニオンアプリ（10-13 07:27）在窗口外也被排除：算進排除，不算窗口外。"""
    articles, _ = _collect(SOURCE, _pages(), caplog, cutoff=datetime(2026, 10, 13, 8, 0, tzinfo=UTC))
    assert [a["title"] for a in articles] == ["更新のお知らせ(10/20)"]
    assert _line(5, 1, 2, 2) in caplog.text


def test_old_notices_do_not_flood_in_when_window_is_after_everything(caplog):
    articles, failures = _collect(SOURCE, _pages(), caplog, cutoff=datetime(2026, 10, 21, tzinfo=UTC))
    assert articles == []
    assert failures == ([], 1)
    assert _line(5, 0, 3, 2) in caplog.text


def test_item_without_a_date_match_is_out_of_window(caplog):
    html = ('<ul><li class="news__list"><a href="/lodestone/news/detail/a"><p class="news__list--title">'
            '更新のお知らせ(10/20)</p><script>ldst_strftime(1792479000, \'YMD\');</script></a></li>'
            '<li class="news__list"><a href="/lodestone/news/detail/b"><p class="news__list--title">'
            '更新のお知らせ(日付なし)</p></a></li></ul>')
    source = {k: v for k, v in SOURCE.items() if k not in ("detail_selector", "max_chars")}
    articles, _ = _collect(source, {LIST_URL: _resp(html)}, caplog)
    assert [a["title"] for a in articles] == ["更新のお知らせ(10/20)"]
    assert _line(2, 1, 1, 0) in caplog.text


def test_exclude_alone_drops_both_prefixes_without_a_window(caplog):
    source = {k: v for k, v in SOURCE.items() if k in ("name", "type", "url", "selector", "title_selector",
                                                        "exclude_title_prefixes")}
    articles, _ = _collect(source, _pages(), caplog, cutoff=datetime(2026, 12, 1, tzinfo=UTC))
    assert [(a["title"], a["published"], a["summary"]) for a in articles] == [
        ("更新のお知らせ(10/20)", "", ""), ("更新のお知らせ(10/13)", "", ""), ("更新のお知らせ(9/19)", "", ""),
    ]
    assert _line(5, 3, 0, 2) in caplog.text


def test_date_pattern_alone_prints_the_line_and_keeps_both_prefixes(caplog):
    source = {k: v for k, v in SOURCE.items() if k not in ("exclude_title_prefixes", "detail_selector", "max_chars")}
    articles, _ = _collect(source, _pages(), caplog)
    assert [a["link"] for a in articles] == [D1020, LODESTONE_1013, COMPANION_1013, D1013]
    assert _line(5, 4, 1, 0) in caplog.text


def test_detail_text_is_cut_to_max_chars(caplog):
    full, _ = _collect(SOURCE, _pages(), caplog)
    articles, _ = _collect({**SOURCE, "max_chars": 50}, _pages(), caplog)
    assert [len(a["summary"]) for a in articles] == [50, 50]
    assert articles[0]["summary"] == full[0]["summary"][:50]


def test_max_chars_defaults_to_2000_when_detail_selector_is_set(caplog):
    long = '<div class="news__detail__wrapper">' + "あ" * 2500 + "</div>"
    source = {k: v for k, v in SOURCE.items() if k != "max_chars"}
    articles, _ = _collect(source, _pages(**{D1020: _resp(long)}), caplog)
    assert articles[0]["summary"] == "あ" * 2000
    assert len(articles[1]["summary"]) == 414


def test_detail_request_failure_keeps_title_only_and_says_why(caplog):
    pages = _pages(**{D1013: requests.ConnectionError("Connection reset by peer")})
    articles, failures = _collect(SOURCE, pages, caplog)
    assert [(a["title"], a["summary"][:10]) for a in articles] == [
        ("更新のお知らせ(10/20)", DETAIL_HEAD[:10]), ("更新のお知らせ(10/13)", ""),
    ]
    assert failures == ([], 1)
    assert _fallback("更新のお知らせ(10/13)", "Connection reset by peer") in caplog.text
    assert _fallback("更新のお知らせ(10/20)", "Connection reset by peer") not in caplog.text


def test_detail_http_error_keeps_title_only(caplog):
    articles, failures = _collect(SOURCE, _pages(**{D1020: _resp("", error="404 Client Error: Not Found")}), caplog)
    assert articles[0]["summary"] == ""
    assert failures == ([], 1)
    assert _fallback("更新のお知らせ(10/20)", "404 Client Error: Not Found") in caplog.text


def test_detail_selector_missing_on_page_is_a_distinct_reason(caplog):
    page = _resp('<article class="news__detail"><div class="news__body">改版後</div></article>')
    articles, failures = _collect(SOURCE, _pages(**{D1013: page}), caplog)
    assert articles[1]["summary"] == ""
    assert failures == ([], 1)
    assert _fallback("更新のお知らせ(10/13)", "找不到 div.news__detail__wrapper") in caplog.text


def test_detail_pages_only_for_collected_items_with_a_pause_before_each(caplog):
    events = []
    _collect(SOURCE, _pages(), caplog, events=events)
    assert events == [("get", LIST_URL), ("sleep", 1), ("get", D1020), ("sleep", 1), ("get", D1013), ("sleep", 1)]


def test_max_items_caps_what_is_collected_and_fetched(caplog):
    events = []
    articles, _ = _collect({**SOURCE, "max_items": 1}, _pages(), caplog, events=events)
    assert [a["link"] for a in articles] == [D1020]
    assert [e for e in events if e[0] == "get"] == [("get", LIST_URL), ("get", D1020)]
    assert _line(5, 1, 0, 0) in caplog.text


def test_without_the_options_behaviour_is_unchanged(caplog):
    """TW 修正說明現在就這樣用：不抽時間、不排除、不抓詳細頁、不印新那行；窗口設在全部之後也照收。"""
    events = []
    source = {k: v for k, v in SOURCE.items() if k not in OPTIONS}
    articles, failures = _collect(source, _pages(), caplog, cutoff=datetime(2026, 12, 1, tzinfo=UTC), events=events)
    titles = ["更新のお知らせ(10/20)", "Lodestone 更新のお知らせ(10/13)", "コンパニオンアプリ 更新のお知らせ(10/13)",
              "更新のお知らせ(10/13)", "更新のお知らせ(9/19)"]
    links = [D1020, LODESTONE_1013, COMPANION_1013, D1013, D0919]
    assert articles == [
        {"title": t, "link": u, "summary": "", "source": NAME, "published": "", "content_type": "ffxiv",
         "source_weight": 60}
        for t, u in zip(titles, links)
    ]
    assert failures == ([], 1)
    assert [e for e in events if e[0] == "get"] == [("get", LIST_URL)]
    assert "解析" not in caplog.text and "詳細頁" not in caplog.text
    assert f"{NAME}: 5 筆" in caplog.text
