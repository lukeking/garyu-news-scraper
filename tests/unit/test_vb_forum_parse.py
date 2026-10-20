"""spec 015 T008：討論串頁面解析（回覆 id、時間、內文、前一頁網址）與日本時間的回覆時間。"""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.collector import _parse_vb_page, _parse_vb_time  # noqa: E402

UTC = timezone.utc
FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "ffxiv")
THREAD = "https://forum.square-enix.com/ffxiv/threads/498925-%E7%8D%A3%E4%BD%BF%E3%81%84%E3%82%B9%E3%83%AC"
# fixtures 的抓取時刻：日本時間 10-20 21:26（SOURCES.md）
CAPTURED = datetime(2026, 10, 20, 12, 26, tzinfo=UTC)
# 日本時間 10-20 00:30，UTC 仍是 10-19
JST_EARLY_MORNING = datetime(2026, 10, 19, 15, 30, tzinfo=UTC)


def _read(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def _iso(dt):
    return dt.isoformat() if dt else None


# ── 回覆時間 ──────────────────────────────────────────────────

@pytest.mark.parametrize("text, now, expected", [
    ("10-15-2026 01:16 PM", CAPTURED, "2026-10-15T04:16:00+00:00"),
    ("10-16-2026 07:22 AM", CAPTURED, "2026-10-15T22:22:00+00:00"),
    ("10-17-2026 12:14 AM", CAPTURED, "2026-10-16T15:14:00+00:00"),
    ("10-17-2026 12:05 PM", CAPTURED, "2026-10-17T03:05:00+00:00"),
    ("Today 08:32 PM", CAPTURED, "2026-10-20T11:32:00+00:00"),       # RSS pubDate 11:32:28 GMT 的那則
    ("Yesterday 04:53 PM", CAPTURED, "2026-10-19T07:53:00+00:00"),
    ("Today 12:22 AM", JST_EARLY_MORNING, "2026-10-19T15:22:00+00:00"),
    ("Yesterday 12:02 AM", JST_EARLY_MORNING, "2026-10-18T15:02:00+00:00"),
])
def test_reply_time_is_japan_time(text, now, expected):
    assert _iso(_parse_vb_time(text, now)) == expected


@pytest.mark.parametrize("text", [
    "",
    "Last Week 01:00 PM",
    "10-15-2026",
    "13-45-2026 01:00 PM",
    "10-15-2026 13:16 PM",
    "Today",
])
def test_unparsable_reply_time_is_reported_not_guessed(text):
    assert _parse_vb_time(text, CAPTURED) is None


# ── 頁面解析 ──────────────────────────────────────────────────

def test_last_page_posts_and_previous_page_url():
    posts, prev_url = _parse_vb_page(_read("thread_last_page.html"), THREAD, CAPTURED)
    assert [p["id"] for p in posts] == [6851510, 6851637, 6851739]
    assert [_iso(p["time"]) for p in posts] == [
        "2026-10-19T15:22:00+00:00",
        "2026-10-20T04:22:00+00:00",
        "2026-10-20T11:32:00+00:00",
    ]
    assert [p["raw_time"] for p in posts] == ["Today 12:22 AM", "Today 01:22 PM", "Today 08:32 PM"]
    assert posts[0]["text"].startswith("ついさっきようやく闘獣練を解放したので")
    assert posts[2]["text"].endswith("コンテンツも信頼も育てて良くしていって欲しいです。")
    assert all("\n" not in p["text"] and "  " not in p["text"] for p in posts)
    assert prev_url == THREAD + "/page64"


def test_previous_page_absolute_dates_and_yesterday():
    posts, prev_url = _parse_vb_page(_read("thread_prev_page.html"), THREAD, CAPTURED)
    assert [p["id"] for p in posts] == [6850652, 6850873, 6850994, 6851335, 6851440]
    assert [_iso(p["time"]) for p in posts] == [
        "2026-10-15T04:16:00+00:00",
        "2026-10-15T22:22:00+00:00",
        "2026-10-16T15:14:00+00:00",
        "2026-10-18T15:02:00+00:00",
        "2026-10-19T07:53:00+00:00",
    ]
    assert posts[3]["text"].startswith("ランク上げに関しては攻略段階においては")
    assert prev_url == THREAD + "/page63"


def _page(pagination, date_text="10-15-2026 01:16 PM"):
    return (
        f"<html><body>{pagination}<ol id='posts'>"
        f"<li id='post_11'><span class='date'>{date_text}</span>"
        f"<div id='post_message_11'>本文</div></li></ol></body></html>"
    )


def test_first_page_has_no_previous_page():
    posts, prev_url = _parse_vb_page(_page("<a class='popupctrl'>Page 1 of 3</a>"), THREAD, CAPTURED)
    assert [p["id"] for p in posts] == [11]
    assert prev_url is None


def test_single_page_thread_without_pagination_has_no_previous_page():
    posts, prev_url = _parse_vb_page(_page(""), THREAD, CAPTURED)
    assert [p["id"] for p in posts] == [11]
    assert prev_url is None


def test_unparsable_time_keeps_the_raw_text_and_no_time():
    posts, _ = _parse_vb_page(_page("", date_text="Last Week 01:00 PM"), THREAD, CAPTURED)
    assert posts[0]["time"] is None
    assert posts[0]["raw_time"] == "Last Week 01:00 PM"


def test_page_without_posts_parses_to_empty_list():
    posts, prev_url = _parse_vb_page("<html><body><p>Page 2 of 2</p></body></html>", THREAD, CAPTURED)
    assert posts == []
    assert prev_url == THREAD + "/page1"
