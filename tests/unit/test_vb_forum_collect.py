"""spec 015 T009：vb_forum 收集——選串、翻頁、窗口內回覆、上限、退回、截斷警告、每串一行。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock, call, patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import collector  # noqa: E402

UTC = timezone.utc
NAME = "FFXIV JP Forum - DPS"
SOURCE = {"name": NAME, "type": "vb_forum", "url": "https://rss", "content_type": "ffxiv"}
BASE = "https://forum.square-enix.com/ffxiv/threads"
# 週一 01:00Z → 窗口［10-12 00:00Z, 10-19 00:00Z）＝日本時間［10-12 09:00, 10-19 09:00）
NOW = datetime(2026, 10, 19, 1, 0, tzinfo=UTC)
AFTER = "10-19-2026 10:00 AM"    # 10-19 01:00Z，窗口終點之後
BEFORE = "10-11-2026 08:00 PM"   # 10-11 11:00Z，窗口起點之前


def _utc(*args):
    return datetime(*args, tzinfo=UTC)


def _item(tid, title, pub, body="RSS 最後一則的內文"):
    return (
        f"<item><title>{title}</title><link>{BASE}/{tid}-x?goto=newpost</link>"
        f"<pubDate>{format_datetime(pub, usegmt=True)}</pubDate>"
        f"<content:encoded><![CDATA[<div>{body}</div>]]></content:encoded>"
        f"<guid isPermaLink=\"true\">{BASE}/{tid}-x</guid></item>"
    )


def _rss(*items):
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        "<channel><title>t</title>" + "".join(items) + "</channel></rss>"
    ).encode("utf-8")


def _page(posts, page=None, of=None):
    nav = f"<a class='popupctrl'>Page {page} of {of}</a>" if page else ""
    lis = "".join(
        f"<li id='post_{pid}'><span class='date'>{when}</span><div id='post_message_{pid}'>{text}</div></li>"
        for pid, when, text in posts
    )
    return f"<html><body>{nav}<ol id='posts'>{lis}</ol></body></html>"


def _resp(text):
    r = MagicMock()
    r.text = text
    return r


def _run(rss, pages, caplog, now=NOW, **cfg):
    def get(url, **kw):
        page = pages(url) if callable(pages) else pages[url]
        if isinstance(page, Exception):
            raise page
        return _resp(page)

    getter = MagicMock(side_effect=get)
    with patch.object(collector, "_fetch_rss_bytes", return_value=rss), \
         patch.object(collector.requests, "get", getter), \
         patch.object(collector.time, "sleep") as sleep, \
         caplog.at_level(logging.INFO, logger="src.collector"):
        articles = collector._fetch_vb_forum({**SOURCE, **cfg}, now=now)
    return articles, [c.args[0] for c in getter.call_args_list], sleep


def _goto(tid):
    return f"{BASE}/{tid}-x?goto=newpost"


def _thread_line(title, n, m, p):
    return f"{NAME}: {title[:30]} 窗口內 {n} 則、收 {m} 則、翻 {p} 頁"


# ── (a) 選串 ──────────────────────────────────────────────────

def test_only_threads_whose_last_reply_is_after_window_start_are_processed(caplog):
    rss = _rss(_item(101, "選中的串", _utc(2026, 10, 18, 12)), _item(102, "太舊的串", _utc(2026, 10, 11, 23)))
    pages = {_goto(101): _page([(1001, "10-18-2026 09:00 PM", "回覆一")])}
    articles, requested, _ = _run(rss, pages, caplog)
    assert requested == [_goto(101)]
    assert [a["title"] for a in articles] == ["選中的串"]


# ── (b)(d)(g) 翻頁、窗口內回覆、link／dedup_key、翻頁上限 ────────

_FOUR_PAGES = {
    _goto(201): _page([(2005, "10-18-2026 09:00 PM", "四"), (2006, AFTER, "窗口後")], 4, 4),
    f"{BASE}/201-x/page3": _page([(2003, "10-15-2026 09:00 PM", "二"), (2004, "10-16-2026 09:00 PM", "三")], 3, 4),
    f"{BASE}/201-x/page2": _page([(2001, BEFORE, "窗口前"), (2002, "10-12-2026 10:00 AM", "一")], 2, 4),
}
_WALK_RSS = _rss(_item(201, "長期串", _utc(2026, 10, 19, 1)))


def test_walks_back_until_a_page_starts_before_the_window(caplog):
    articles, requested, sleep = _run(_WALK_RSS, _FOUR_PAGES, caplog, max_pages=3)
    assert requested == [_goto(201), f"{BASE}/201-x/page3", f"{BASE}/201-x/page2"]
    assert len(articles) == 1
    assert articles[0]["summary"] == "[10/12 10:00] 一\n[10/15 21:00] 二\n[10/16 21:00] 三\n[10/18 21:00] 四"
    assert _thread_line("長期串", 4, 4, 3) in caplog.text
    assert "翻到上限" not in caplog.text
    assert sleep.call_args_list == [call(1)] * 3


def test_article_fields_point_at_the_newest_reply_inside_the_window(caplog):
    articles, _, _ = _run(_WALK_RSS, _FOUR_PAGES, caplog)
    a = articles[0]
    assert a["title"] == "長期串"
    assert a["link"] == f"{BASE}/201-x?p=2005"
    assert a["dedup_key"] == "forum:201:2005"
    assert a["published"] == "2026-10-18T12:00:00+00:00"
    assert a["source"] == NAME
    assert a["content_type"] == "ffxiv"


def test_window_includes_its_start_and_excludes_its_end(caplog):
    # 終點那一則（10-19 00:00Z）屬於下一週；算進來就會被兩週各分析一次（FR-003）
    rss = _rss(_item(301, "邊界串", _utc(2026, 10, 19, 0)))
    posts = [
        (3001, "10-12-2026 08:59 AM", "起點前一分鐘"),
        (3002, "10-12-2026 09:00 AM", "剛好起點"),
        (3003, "10-19-2026 08:59 AM", "終點前一分鐘"),
        (3004, "10-19-2026 09:00 AM", "剛好終點"),
    ]
    articles, _, _ = _run(rss, {_goto(301): _page(posts)}, caplog)
    assert articles[0]["summary"] == "[10/12 09:00] 剛好起點\n[10/19 08:59] 終點前一分鐘"
    assert articles[0]["link"] == f"{BASE}/301-x?p=3003"
    assert _thread_line("邊界串", 2, 2, 1) in caplog.text


def test_page_cap_stops_the_walk_and_says_so(caplog):
    articles, requested, _ = _run(_WALK_RSS, _FOUR_PAGES, caplog, max_pages=2)
    assert requested == [_goto(201), f"{BASE}/201-x/page3"]
    assert articles[0]["summary"] == "[10/15 21:00] 二\n[10/16 21:00] 三\n[10/18 21:00] 四"
    assert f"{NAME}: 長期串 翻到上限 2 頁仍未到窗口起點，可能還有更早的回覆沒收" in caplog.text
    assert _thread_line("長期串", 3, 3, 2) in caplog.text


def test_default_page_cap_is_three(caplog):
    pages = {_goto(301): _page([(3005, "10-18-2026 09:00 PM", "e")], 5, 5)}
    for n in range(1, 5):
        pages[f"{BASE}/301-x/page{n}"] = _page([(3000 + n, f"10-1{n + 3}-2026 09:00 PM", "x")], n, 5)
    _, requested, _ = _run(_rss(_item(301, "五頁的串", _utc(2026, 10, 18, 12))), pages, caplog)
    assert requested == [_goto(301), f"{BASE}/301-x/page4", f"{BASE}/301-x/page3"]
    assert f"{NAME}: 五頁的串 翻到上限 3 頁仍未到窗口起點" in caplog.text


def test_reaching_the_reply_cap_stops_the_walk_without_page_cap_warning(caplog):
    posts = [(3101, "10-16-2026 09:00 PM", "甲"), (3102, "10-17-2026 09:00 PM", "乙"), (3103, "10-18-2026 09:00 PM", "丙")]
    pages = {_goto(310): _page(posts, 2, 2)}
    articles, requested, _ = _run(_rss(_item(310, "夠多的串", _utc(2026, 10, 18, 12))), pages, caplog, max_replies=2)
    assert requested == [_goto(310)]
    assert articles[0]["summary"] == "[10/17 21:00] 乙\n[10/18 21:00] 丙"
    assert _thread_line("夠多的串", 3, 2, 1) in caplog.text
    assert "翻到上限" not in caplog.text


# ── (c) 上限：max_replies 丟最舊、max_chars 新的優先 ─────────────

def _one_page_thread(tid, texts):
    posts = [(tid * 10 + i, f"10-1{i + 3}-2026 09:00 PM", t) for i, t in enumerate(texts)]
    return _rss(_item(tid, f"串{tid}", _utc(2026, 10, 18, 12))), {_goto(tid): _page(posts)}


def test_reply_cap_drops_the_oldest_and_keeps_time_order(caplog):
    rss, pages = _one_page_thread(41, ["一", "二", "三", "四", "五"])
    articles, _, _ = _run(rss, pages, caplog, max_replies=3)
    assert articles[0]["summary"] == "[10/15 21:00] 三\n[10/16 21:00] 四\n[10/17 21:00] 五"
    assert _thread_line("串41", 5, 3, 1) in caplog.text


def test_char_cap_drops_whole_oldest_replies_first(caplog):
    rss, pages = _one_page_thread(42, ["あ" * 10, "い" * 10, "う" * 10])
    articles, _, _ = _run(rss, pages, caplog, max_chars=50)
    # 每則 "[MM/DD HH:MM] " 14 字＋10 字；兩則加換行 49 字，三則 74 字
    assert articles[0]["summary"] == "[10/14 21:00] " + "い" * 10 + "\n[10/15 21:00] " + "う" * 10
    assert _thread_line("串42", 3, 2, 1) in caplog.text


def test_newest_reply_alone_over_the_char_cap_is_cut(caplog):
    rss, pages = _one_page_thread(43, ["あ" * 10, "い" * 10])
    articles, _, _ = _run(rss, pages, caplog, max_chars=20)
    assert articles[0]["summary"] == ("[10/14 21:00] " + "い" * 10)[:20]
    assert _thread_line("串43", 2, 1, 1) in caplog.text


def test_default_reply_cap_is_twenty(caplog):
    posts = [(4400 + i, f"10-15-2026 01:{i:02d} PM", "短") for i in range(25)]
    pages = {_goto(44): _page(posts)}
    _run(_rss(_item(44, "回覆很多的串", _utc(2026, 10, 18, 12))), pages, caplog)
    assert _thread_line("回覆很多的串", 25, 20, 1) in caplog.text


def test_default_char_cap_is_six_thousand(caplog):
    posts = [(4500 + i, f"10-15-2026 01:{i:02d} PM", "長" * 400) for i in range(20)]
    pages = {_goto(45): _page(posts)}
    articles, _, _ = _run(_rss(_item(45, "長回覆的串", _utc(2026, 10, 18, 12))), pages, caplog)
    # 每則 414 字：14 則加 13 個換行 5,809 字，15 則 6,224 字
    assert len(articles[0]["summary"]) == 14 * 414 + 13
    assert _thread_line("長回覆的串", 20, 14, 1) in caplog.text


# ── (e) 窗口內 0 則 ────────────────────────────────────────────

def test_thread_with_no_reply_inside_the_window_produces_nothing(caplog):
    pages = {_goto(501): _page([(5001, BEFORE, "前"), (5002, AFTER, "後")])}
    articles, _, _ = _run(_rss(_item(501, "只有窗口後回覆的串", _utc(2026, 10, 19, 1))), pages, caplog)
    assert articles == []
    assert _thread_line("只有窗口後回覆的串", 0, 0, 1) in caplog.text


# ── (f) 三種退回 ──────────────────────────────────────────────

_FALLBACK_PUB = _utc(2026, 10, 18, 12)
_EPOCH = int(_FALLBACK_PUB.timestamp())


def test_three_fallbacks_each_say_their_own_reason_and_use_the_rss_last_reply(caplog):
    rss = _rss(
        _item(601, "請求失敗的串", _FALLBACK_PUB),
        _item(602, "解析不到回覆的串", _FALLBACK_PUB),
        _item(603, "時間解析不出的串", _FALLBACK_PUB),
    )
    pages = {
        _goto(601): requests.exceptions.ConnectionError("boom"),
        _goto(602): "<html><body><p>維護中</p></body></html>",
        _goto(603): _page([(6031, "Last Week 01:00 PM", "x")]),
    }
    articles, _, _ = _run(rss, pages, caplog)
    lines = [
        f"{NAME}: 請求失敗的串 討論串頁面請求失敗（boom），退回 RSS 最後一則",
        f"{NAME}: 解析不到回覆的串 頁面解析不到回覆，退回 RSS 最後一則",
        f"{NAME}: 時間解析不出的串 回覆時間解析不出來（Last Week 01:00 PM），退回 RSS 最後一則",
    ]
    for line in lines:
        assert line in caplog.text
    assert caplog.text.count("退回 RSS 最後一則") == 3
    assert [a["title"] for a in articles] == ["請求失敗的串", "解析不到回覆的串", "時間解析不出的串"]
    for tid, a in zip((601, 602, 603), articles):
        assert a["summary"] == "[10/18 21:00] RSS 最後一則的內文"
        assert a["link"] == f"{BASE}/{tid}-x?lastpost={_EPOCH}"
        assert a["dedup_key"] == f"forum:{tid}:t{_EPOCH}"
        assert a["published"] == "2026-10-18T12:00:00+00:00"
    assert _thread_line("請求失敗的串", 1, 1, 0) in caplog.text


def test_fallback_outside_the_window_produces_nothing_and_says_so(caplog):
    rss = _rss(_item(604, "最後一則在窗口後的串", _utc(2026, 10, 19, 1)))
    pages = {_goto(604): requests.exceptions.ConnectionError("boom")}
    articles, _, _ = _run(rss, pages, caplog)
    assert articles == []
    assert (f"{NAME}: 最後一則在窗口後的串 討論串頁面請求失敗（boom），退回 RSS 最後一則，"
            "但它不在窗口內，這串略過") in caplog.text


# ── (h) 截斷警告 ──────────────────────────────────────────────

def _any_page(url):
    return _page([(9, "10-15-2026 09:00 PM", "x")])


def _feed(n, oldest):
    items = [_item(700 + i, f"串{i}", _utc(2026, 10, 18, 12) - timedelta(hours=i)) for i in range(n - 1)]
    return _rss(*items, _item(799, "最舊的串", oldest))


def test_full_feed_with_oldest_inside_the_window_warns(caplog):
    _run(_feed(15, _utc(2026, 10, 12, 5)), _any_page, caplog)
    assert f"{NAME}: 回滿 15 串且最舊一串仍在窗口內，可能有串被截掉（最舊 2026-10-12T05:00:00+00:00）" in caplog.text


def test_fourteen_threads_do_not_warn(caplog):
    _run(_feed(14, _utc(2026, 10, 12, 5)), _any_page, caplog)
    assert "回滿 15 串" not in caplog.text


def test_full_feed_with_oldest_outside_the_window_does_not_warn(caplog):
    _, requested, _ = _run(_feed(15, _utc(2026, 10, 11, 23)), _any_page, caplog)
    assert "回滿 15 串" not in caplog.text
    assert _goto(799) not in requested


# ── (i) 每串一行 ──────────────────────────────────────────────

def test_one_line_per_thread_with_title_cut_to_thirty_chars(caplog):
    title = "あ" * 25 + "いいいいいうううう"
    pages = {_goto(801): _page([(8001, "10-18-2026 09:00 PM", "x")]), _goto(802): _page([(8002, BEFORE, "y")])}
    _run(_rss(_item(801, title, _utc(2026, 10, 18, 12)), _item(802, "第二串", _utc(2026, 10, 18, 12))), pages, caplog)
    assert _thread_line(title, 1, 1, 1) in caplog.text
    assert title[:31] not in caplog.text
    assert _thread_line("第二串", 0, 0, 1) in caplog.text
    assert caplog.text.count("窗口內 ") == 2


# ── (j) RSS 0 筆不算失敗；RSS 抓不到才算（經 collect_sources，順便證明 FETCHERS 有註冊） ──

def _collect(rss_side_effect, caplog):
    with patch.object(collector, "_fetch_rss_bytes", side_effect=rss_side_effect), \
         patch.object(collector.time, "sleep"), \
         caplog.at_level(logging.INFO, logger="src.collector"):
        return collector.collect_sources([SOURCE])


def test_empty_feed_is_not_a_failure(caplog):
    assert _collect(lambda url: _rss(), caplog) == []
    assert collector.last_collect_failures() == ([], 1)
    assert f"{NAME}: 0 筆" in caplog.text


def test_feed_fetch_failure_is_a_source_failure(caplog):
    assert _collect(RuntimeError("503 Server Error"), caplog) == []
    assert collector.last_collect_failures() == ([NAME], 1)
    assert f"{NAME} 失敗: 503 Server Error" in caplog.text


# ── 真實頁面（fixtures）走一遍 ────────────────────────────────

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ffxiv")
THREAD = "https://forum.square-enix.com/ffxiv/threads/498925-%E7%8D%A3%E4%BD%BF%E3%81%84%E3%82%B9%E3%83%AC"


def _fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def test_real_thread_pages_from_the_capture_day(caplog):
    item = (
        f"<item><title>獣使いスレ</title><link>{THREAD}?goto=newpost</link>"
        "<pubDate>Tue, 20 Oct 2026 11:32:28 GMT</pubDate>"
        "<content:encoded><![CDATA[<div>x</div>]]></content:encoded>"
        f"<guid isPermaLink=\"true\">{THREAD}</guid></item>"
    )
    pages = {
        f"{THREAD}?goto=newpost": _fixture("thread_last_page.html"),
        f"{THREAD}/page64": _fixture("thread_prev_page.html"),
    }
    articles, requested, _ = _run(_rss(item), pages, caplog, now=_utc(2026, 10, 20, 12, 26), max_pages=2)
    assert requested == [f"{THREAD}?goto=newpost", f"{THREAD}/page64"]
    a = articles[0]
    assert a["link"] == f"{THREAD}?p=6851335"
    assert a["dedup_key"] == "forum:498925:6851335"
    assert a["published"] == "2026-10-18T15:02:00+00:00"
    assert [s[:13] for s in a["summary"].split("\n")] == [
        "[10/15 13:16]", "[10/16 07:22]", "[10/17 00:14]", "[10/19 00:02]",
    ]
    assert a["summary"].endswith("等の変更が必要かなと思いました。")
    assert _thread_line("獣使いスレ", 4, 4, 2) in caplog.text
    assert f"{NAME}: 獣使いスレ 翻到上限 2 頁仍未到窗口起點" in caplog.text


# ── 邊界：窗口起點／終點、上限剛好等於（每一個比較運算子都有一條測試會在它被改時轉紅） ──

def test_thread_whose_last_reply_is_exactly_at_window_start_is_processed(caplog):
    rss = _rss(_item(901, "起點那一刻的串", _utc(2026, 10, 12, 0)), _item(902, "早一秒的串", _utc(2026, 10, 11, 23, 59, 59)))
    pages = {_goto(901): _page([(9011, "10-12-2026 09:00 AM", "剛好起點")])}
    articles, requested, _ = _run(rss, pages, caplog)
    assert requested == [_goto(901)]
    assert [a["title"] for a in articles] == ["起點那一刻的串"]


def test_full_feed_with_oldest_exactly_at_window_start_warns(caplog):
    _run(_feed(15, _utc(2026, 10, 12, 0)), _any_page, caplog)
    assert f"{NAME}: 回滿 15 串且最舊一串仍在窗口內，可能有串被截掉（最舊 2026-10-12T00:00:00+00:00）" in caplog.text


def test_fallback_whose_rss_reply_is_exactly_at_window_end_is_outside(caplog):
    rss = _rss(_item(903, "終點那一刻的串", _utc(2026, 10, 19, 0)))
    articles, _, _ = _run(rss, {_goto(903): requests.exceptions.ConnectionError("boom")}, caplog)
    assert articles == []
    assert "終點那一刻的串 討論串頁面請求失敗（boom），退回 RSS 最後一則，但它不在窗口內，這串略過" in caplog.text


def test_page_starting_exactly_at_window_start_still_walks_back(caplog):
    pages = {
        _goto(904): _page([(9042, "10-12-2026 09:00 AM", "後頁起點"), (9043, "10-15-2026 09:00 PM", "後頁")], 2, 2),
        f"{BASE}/904-x/page1": _page([(9041, "10-12-2026 09:00 AM", "前頁同一分鐘")], 1, 2),
    }
    articles, requested, _ = _run(_rss(_item(904, "起點跨頁的串", _utc(2026, 10, 18, 12))), pages, caplog)
    assert requested == [_goto(904), f"{BASE}/904-x/page1"]
    assert articles[0]["summary"] == "[10/12 09:00] 前頁同一分鐘\n[10/12 09:00] 後頁起點\n[10/15 21:00] 後頁"


def test_walk_stops_as_soon_as_the_reply_cap_is_exactly_reached(caplog):
    pages = {
        _goto(905): _page([(9052, "10-16-2026 09:00 PM", "乙"), (9053, "10-17-2026 09:00 PM", "丙")], 2, 2),
        f"{BASE}/905-x/page1": _page([(9051, "10-15-2026 09:00 PM", "甲")], 1, 2),
    }
    articles, requested, _ = _run(_rss(_item(905, "剛好收滿的串", _utc(2026, 10, 18, 12))), pages, caplog, max_replies=2)
    assert requested == [_goto(905)]
    assert articles[0]["summary"] == "[10/16 21:00] 乙\n[10/17 21:00] 丙"


def test_merged_text_exactly_at_the_char_cap_is_kept_whole(caplog):
    rss, pages = _one_page_thread(46, ["あ" * 10, "い" * 10])
    articles, _, _ = _run(rss, pages, caplog, max_chars=49)
    # 兩則各 24 字加一個換行＝49 字，剛好等於上限
    assert articles[0]["summary"] == "[10/13 21:00] " + "あ" * 10 + "\n[10/14 21:00] " + "い" * 10
