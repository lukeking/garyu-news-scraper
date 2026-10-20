"""spec 015 T002：來源權重蓋到文章上、FFXIV 排序鍵、game_deduplicate 依鍵取前 20、候選池／入選兩行。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import collector  # noqa: E402
from src.filter import ffxiv_rank_key, game_deduplicate  # noqa: E402

CONFIG = {"jaccard": {"game_threshold": 0.50}}
BASE = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)

_RSS = (
    b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>'
    b"<item><title>alpha</title><link>https://x/1</link></item>"
    b"<item><title>beta</title><link>https://x/2</link></item>"
    b"</channel></rss>"
)


def _a(title, source="S", weight=None, pub=""):
    a = {"title": title, "source": source, "published": pub, "content_type": "ffxiv"}
    if weight is not None:
        a["source_weight"] = weight
    return a


def _ago(**kw):
    return (BASE - timedelta(**kw)).isoformat()


# ── (a) collect_sources 蓋 source_weight ──────────────────────

def test_collect_sources_stamps_weight_only_on_sources_that_have_it():
    sources = [
        {"name": "Weighted", "type": "rss", "url": "https://w", "content_type": "ffxiv", "weight": 80},
        {"name": "Zero", "type": "rss", "url": "https://z", "content_type": "ffxiv", "weight": 0},
        {"name": "Unweighted", "type": "rss", "url": "https://u", "content_type": "ffxiv"},
    ]
    with patch.object(collector, "_fetch_rss_bytes", return_value=_RSS), \
         patch.object(collector.time, "sleep"):
        articles = collector.collect_sources(sources)

    by_source = {}
    for a in articles:
        by_source.setdefault(a["source"], []).append(a)
    assert {k: len(v) for k, v in by_source.items()} == {"Weighted": 2, "Zero": 2, "Unweighted": 2}
    assert [a["source_weight"] for a in by_source["Weighted"]] == [80, 80]
    assert [a["source_weight"] for a in by_source["Zero"]] == [0, 0]
    assert all("source_weight" not in a for a in by_source["Unweighted"])


# ── (b) 排序鍵 ────────────────────────────────────────────────

def test_rank_key_weight_desc_then_newest_then_missing_published_last():
    articles = [
        _a("lo_none", weight=20),
        _a("unweighted_newest", pub=_ago(hours=-1)),
        _a("lo_old", weight=20, pub=_ago(days=1)),
        _a("hi_none", weight=80),
        _a("hi_old", weight=80, pub=_ago(days=5)),
        _a("lo_new", weight=20, pub=_ago(hours=0)),
        _a("hi_new", weight=80, pub=_ago(days=1)),
    ]
    ranked = sorted(articles, key=ffxiv_rank_key)
    assert [a["title"] for a in ranked] == [
        "hi_new", "hi_old", "hi_none", "lo_new", "lo_old", "lo_none", "unweighted_newest",
    ]


def test_rank_key_missing_weight_counts_as_zero():
    missing_new = _a("missing_new", pub=_ago(days=1))
    zero_mid = _a("zero_mid", weight=0, pub=_ago(days=2))
    missing_old = _a("missing_old", pub=_ago(days=3))
    low = _a("low", weight=1, pub=_ago(days=9))
    ranked = sorted([missing_old, zero_mid, missing_new, low], key=ffxiv_rank_key)
    assert [a["title"] for a in ranked] == ["low", "missing_new", "zero_mid", "missing_old"]


def test_rank_key_reads_rfc2822_naive_iso_and_unparseable_published():
    # 時間格式沿用 _parse_published（ISO 或 RFC 2822）；不帶時區的 ISO 當 UTC；解析不出來的與沒有時間的同列最後。
    rfc_newest = _a("rfc_newest", weight=20, pub="Mon, 19 Oct 2026 11:00:00 +0000")
    naive_mid = _a("naive_mid", weight=20, pub="2026-10-19T10:00:00")
    aware_old = _a("aware_old", weight=20, pub="2026-10-19T09:00:00+00:00")
    garbage = _a("garbage", weight=20, pub="not a date")
    missing = _a("missing", weight=20)
    ranked = sorted([garbage, aware_old, missing, naive_mid, rfc_newest], key=ffxiv_rank_key)
    assert [a["title"] for a in ranked] == ["rfc_newest", "naive_mid", "aware_old", "garbage", "missing"]


# ── (c) game_deduplicate 依排序鍵取前 20 ──────────────────────

def test_game_deduplicate_takes_top_20_by_rank_key():
    low_new = [_a(f"low{i:02d}", "Low", 20, _ago(hours=i)) for i in range(25)]
    high_old = [_a(f"high{i:02d}", "High", 80, _ago(days=6, hours=i)) for i in range(3)]
    result = game_deduplicate(low_new + high_old, CONFIG)
    assert [a["title"] for a in result] == (
        [f"high{i:02d}" for i in range(3)] + [f"low{i:02d}" for i in range(17)]
    )


def test_game_deduplicate_without_weights_keeps_time_order():
    timed = [_a(f"item{i:02d}", pub=_ago(hours=i)) for i in range(19)]
    untimed = [_a("untimed_first"), _a("untimed_second")]
    shuffled = timed[1::2] + [untimed[0]] + timed[0::2] + [untimed[1]]
    result = game_deduplicate(shuffled, CONFIG)
    assert [a["title"] for a in result] == [f"item{i:02d}" for i in range(19)] + ["untimed_first"]


# ── (d) 候選池／入選兩行（contracts/log-lines.md）─────────────

def _messages(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "src.filter"]


def test_pool_and_selected_lines_match_contract(caplog):
    articles = (
        [_a(f"tw{i}", "FFXIV TW 修正說明", 50) for i in range(2)]
        + [_a(f"other{i}", "FFXIV JP Forum - その他バトルシステム", 80, _ago(days=2, hours=i)) for i in range(2)]
        + [_a(f"dps{i}", "FFXIV JP Forum - DPS", 80, _ago(days=3, hours=i)) for i in range(2)]
        + [_a(f"reddit{i:02d}", "Reddit r/ffxiv", 20, _ago(hours=i)) for i in range(25)]
    )
    with caplog.at_level(logging.INFO, logger="src.filter"):
        result = game_deduplicate(articles, CONFIG)

    assert len(result) == 20
    msgs = _messages(caplog)
    assert (
        "FFXIV 候選池 31 篇：Reddit r/ffxiv 25、FFXIV JP Forum - DPS 2、"
        "FFXIV JP Forum - その他バトルシステム 2、FFXIV TW 修正說明 2"
    ) in msgs
    assert (
        "FFXIV 入選 20 篇：Reddit r/ffxiv 14、FFXIV JP Forum - DPS 2、"
        "FFXIV JP Forum - その他バトルシステム 2、FFXIV TW 修正說明 2"
    ) in msgs


def test_pool_is_counted_after_jaccard_dedupe(caplog):
    articles = [
        _a("knight adjustment", "FFXIV JP Forum - TANK", 80, _ago(days=1)),
        _a("knight adjustment", "Reddit r/ffxiv", 20, _ago(hours=1)),
        _a("gamma", "Reddit r/ffxiv", 20, _ago(hours=2)),
    ]
    with caplog.at_level(logging.INFO, logger="src.filter"):
        game_deduplicate(articles, CONFIG)

    msgs = _messages(caplog)
    assert "FFXIV 候選池 2 篇：FFXIV JP Forum - TANK 1、Reddit r/ffxiv 1" in msgs
    assert "FFXIV 入選 2 篇：FFXIV JP Forum - TANK 1、Reddit r/ffxiv 1" in msgs


def test_empty_pool_lines(caplog):
    with caplog.at_level(logging.INFO, logger="src.filter"):
        assert game_deduplicate([], CONFIG) == []

    msgs = _messages(caplog)
    assert "FFXIV 候選池 0 篇" in msgs
    assert "FFXIV 入選 0 篇" in msgs
