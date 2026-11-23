"""
Unit tests for game_deduplicate() — FR-008, FR-009, FR-010.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import game_deduplicate

CONFIG = {"jaccard": {"game_threshold": 0.50}}


def _article(title: str, pub: str = "2025-01-01T00:00:00") -> dict:
    return {"title": title, "published": pub}


def test_inclusion_check_shorter_discarded():
    """FR-008: A whose tokens ⊆ B's tokens is dropped."""
    long_title = "FFXIV 7.2 更新 職業 調整 詳細 說明"
    short_title = "FFXIV 更新"
    articles = [_article(long_title), _article(short_title)]
    result = game_deduplicate(articles, CONFIG)
    titles = [a["title"] for a in result]
    assert long_title in titles
    assert short_title not in titles


def test_jaccard_above_threshold_discarded():
    """FR-009: second article with Jaccard > 0.50 vs. retained article is dropped."""
    a1 = _article("FFXIV 7.2 更新 職業 調整 平衡 補丁")
    a2 = _article("FFXIV 7.2 更新 職業 調整 平衡 說明")
    result = game_deduplicate([a1, a2], CONFIG)
    assert len(result) == 1


def test_cap_at_twenty():
    """FR-010: output is capped at 20 articles even with 25 unique inputs."""
    articles = [_article(f"完全不同的遊戲新聞第{i}篇獨立標題內容") for i in range(25)]
    result = game_deduplicate(articles, CONFIG)
    assert len(result) <= 20


def test_all_unique_retained():
    """All unique articles (≤ 20) are retained without truncation."""
    articles = [
        _article("戰士職業平衡調整說明"),
        _article("白魔法師治療技能更新"),
        _article("忍者轉職任務攻略完整"),
        _article("占星術士位置技巧介紹"),
        _article("龍騎士連擊循環教學"),
        _article("賢者治療手法分析"),
        _article("舞者職業特色詳解"),
        _article("黑魔法師傷害輸出優化"),
        _article("武士刀技連段攻略"),
        _article("園藝師採集路線規劃"),
    ]
    result = game_deduplicate(articles, CONFIG)
    assert len(result) == 10


def test_disjoint_articles_all_retained():
    """Completely disjoint titles → all retained (up to cap)."""
    a1 = _article("坦克職業技能說明")
    a2 = _article("治療職業平衡調整")
    a3 = _article("遠端物理傷害輸出")
    result = game_deduplicate([a1, a2, a3], CONFIG)
    assert len(result) == 3


def test_empty_input_returns_empty():
    result = game_deduplicate([], CONFIG)
    assert result == []


def test_newest_first_ordering():
    """Retained articles are sorted newest-first."""
    old = _article("舊版本職業技能說明詳細", "2024-12-01T00:00:00")
    new = _article("新地圖區域探索指南完整", "2025-03-01T00:00:00")
    result = game_deduplicate([old, new], CONFIG)
    assert len(result) == 2
    assert result[0]["title"] == new["title"]


# ── spec 019 T005：上限 ffxiv.max_selected 與截掉論壇那一行（contracts/config-and-logs.md）──

BASE = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)
CAP_25 = {**CONFIG, "ffxiv": {"max_selected": 25}}


def _ranked(title, source="FFXIV Lodestone", weight=100, hours=0, dedup_key=None):
    a = {"title": title, "source": source, "source_weight": weight,
         "published": (BASE - timedelta(hours=hours)).isoformat()}
    if dedup_key is not None:
        a["dedup_key"] = dedup_key
    return a


def _forum(title, source, hours):
    return _ranked(title, source, 80, hours, dedup_key=f"forum:{title}:1")


def _lodestone(n):
    return [_ranked(f"lodestone{i:02d}", hours=i) for i in range(n)]


def _warnings(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "src.filter" and r.levelno == logging.WARNING]


@pytest.fixture
def quiet_dump(monkeypatch):
    monkeypatch.delenv("FFXIV_POOL_DUMP", raising=False)


@pytest.mark.parametrize("config", [
    CONFIG,
    {**CONFIG, "ffxiv": None},
    {**CONFIG, "ffxiv": {}},
    {**CONFIG, "ffxiv": {"other_key": 5}},
], ids=["no-block", "null-block", "empty-block", "block-without-key"])
def test_cap_defaults_to_20_when_key_missing(config):
    result = game_deduplicate(_lodestone(21), config)
    assert [a["title"] for a in result] == [f"lodestone{i:02d}" for i in range(20)]


def test_cap_25_takes_25_of_26():
    result = game_deduplicate(_lodestone(26), CAP_25)
    assert [a["title"] for a in result] == [f"lodestone{i:02d}" for i in range(25)]


def test_cap_25_with_exactly_25_keeps_all_and_stays_quiet(caplog, quiet_dump):
    articles = _lodestone(24) + [_forum("entank0", "FFXIV EN Forum - TANK", 1)]
    with caplog.at_level(logging.INFO, logger="src.filter"):
        result = game_deduplicate(articles, CAP_25)
    assert len(result) == 25
    assert result[-1]["title"] == "entank0"
    assert _warnings(caplog) == []


@pytest.mark.parametrize("value", [0, -1, 25.0, "25", True, False, None, [25]])
def test_cap_not_positive_int_raises(value):
    with pytest.raises(RuntimeError) as exc:
        game_deduplicate(_lodestone(3), {**CONFIG, "ffxiv": {"max_selected": value}})
    assert "ffxiv.max_selected" in str(exc.value)
    assert repr(value) in str(exc.value)


def test_bad_cap_raises_even_on_empty_input():
    with pytest.raises(RuntimeError, match=r"ffxiv\.max_selected"):
        game_deduplicate([], {**CONFIG, "ffxiv": {"max_selected": 0}})


@pytest.mark.parametrize("block", [25, "max_selected: 25", [], 0, False])
def test_ffxiv_block_not_a_map_raises(block):
    with pytest.raises(RuntimeError) as exc:
        game_deduplicate(_lodestone(3), {**CONFIG, "ffxiv": block})
    assert "ffxiv" in str(exc.value)
    assert repr(block) in str(exc.value)


def test_cut_forum_line_with_default_cap(caplog, quiet_dump):
    articles = _lodestone(20) + [
        _forum("entank0", "FFXIV EN Forum - TANK", 1),
        _forum("entank1", "FFXIV EN Forum - TANK", 2),
        _forum("jpdps0", "FFXIV JP Forum - DPS", 3),
        _ranked("reddit00", "Reddit r/ffxiv", 20, 0),
    ]
    with caplog.at_level(logging.INFO, logger="src.filter"):
        result = game_deduplicate(articles, CONFIG)
    assert len(result) == 20
    assert _warnings(caplog) == ["FFXIV 上限 20 截掉論壇 3 篇：FFXIV EN Forum - TANK 2、FFXIV JP Forum - DPS 1"]


def test_cut_forum_line_uses_configured_cap_and_orders_ties_by_name(caplog, quiet_dump):
    # 第 25 篇 jptank0 剛好入選；截掉的 jptank1 排在 entank0 前面，行內照名稱排
    articles = _lodestone(24) + [
        _forum("jptank0", "FFXIV JP Forum - TANK", 1),
        _forum("jptank1", "FFXIV JP Forum - TANK", 2),
        _forum("entank0", "FFXIV EN Forum - TANK", 3),
    ]
    with caplog.at_level(logging.INFO, logger="src.filter"):
        result = game_deduplicate(articles, CAP_25)
    assert len(result) == 25
    assert result[-1]["title"] == "jptank0"
    assert _warnings(caplog) == ["FFXIV 上限 25 截掉論壇 2 篇：FFXIV EN Forum - TANK 1、FFXIV JP Forum - TANK 1"]


def test_no_line_when_cap_cuts_only_non_forum_items(caplog, quiet_dump):
    # 截掉的有沒帶 dedup_key 的論壇列表頁與 Reddit，都不是 vb_forum 項目
    articles = (
        [_forum(f"jpdps{i}", "FFXIV JP Forum - DPS", i) for i in range(3)]
        + [_ranked(f"reddit{i:02d}", "Reddit r/ffxiv", 20, i) for i in range(18)]
        + [_ranked("listing00", "FFXIV JP Forum", 10, 0)]
    )
    with caplog.at_level(logging.INFO, logger="src.filter"):
        result = game_deduplicate(articles, CONFIG)
    assert len(result) == 20
    assert {a["title"] for a in result} >= {"jpdps0", "jpdps1", "jpdps2"}
    assert _warnings(caplog) == []


# ── GNS-20261123-033：論壇串的身分是 dedup_key，標題相近不算重複；被拿掉的篇每篇印一行 ──

CAP_30 = {**CONFIG, "ffxiv": {"max_selected": 30}}
EVOLVED_HEALERS = 'What Would You Have Wanted From "Evolved" Healers'
EVOLVED_DPS = 'What Would You Have Wanted From "Evolved" DPS?'

# 11-23 週報窗口內的 13 串（來源、串 id、標題），照當週的排序；補師版與 DPS 版那兩串標題只差最後一個字
THREADS_1123 = [
    ("FFXIV JP Forum - その他バトルシステム", 533188, "【要望】１ジョブにつき２種の武器を使えるようになりたい"),
    ("FFXIV EN Forum - Tank Roles", 529932, "Bastion- Discussions and thoughts"),
    ("FFXIV EN Forum - Other Battle Systems", 533177, "Request for Blue Mage change"),
    ("FFXIV JP Forum - DPS", 325458, "赤魔導士 スレッド"),
    ("FFXIV EN Forum - Healer Roles", 531628, EVOLVED_HEALERS),
    ("FFXIV JP Forum - DPS", 116277, "竜騎士改善の具体案"),
    ("FFXIV JP Forum - DPS", 188453, "黒魔導士"),
    ("FFXIV JP Forum - DPS", 498925, "獣使いスレ"),
    ("FFXIV JP Forum - その他バトルシステム", 452719, "種族ステータス補正を廃止してほしい"),
    ("FFXIV JP Forum - TANK", 527721, "新システムによるMT/ST分けへの不満"),
    ("FFXIV JP Forum - TANK", 517309, "先釣りについて"),
    ("FFXIV EN Forum - DPS Roles", 532142, EVOLVED_DPS),
    ("FFXIV JP Forum - HEALER", 432393, "賢者スレ"),
]


def _thread(source, tid, title, hours=0):
    return _ranked(title, source, 80, hours, dedup_key=f"forum:{tid}:1")


def _dedup_lines(caplog):
    msgs = [r.getMessage() for r in caplog.records if r.name == "src.filter"]
    return [m for m in msgs if m.startswith("FFXIV 去重拿掉")]


def _run(articles, caplog, config=CAP_30):
    with caplog.at_level(logging.INFO, logger="src.filter"):
        return game_deduplicate(articles, config)


def test_1123_window_threads_all_stay_in_pool(caplog, quiet_dump):
    articles = [_thread(s, tid, t, hours=i) for i, (s, tid, t) in enumerate(THREADS_1123)]
    result = _run(articles, caplog)
    assert [a["title"] for a in result] == [t for _, _, t in THREADS_1123]
    assert _dedup_lines(caplog) == []


def test_forum_threads_with_the_same_title_on_two_boards_both_stay(caplog, quiet_dump):
    tank = _thread("FFXIV EN Forum - Tank Roles", 101, "Job feedback megathread", 1)
    dps = _thread("FFXIV EN Forum - DPS Roles", 202, "Job feedback megathread", 2)
    assert _run([tank, dps], caplog) == [tank, dps]
    assert _dedup_lines(caplog) == []


def test_same_forum_thread_twice_is_dropped_with_a_line(caplog, quiet_dump):
    first = _thread("FFXIV EN Forum - Tank Roles", 301, "Tank feedback", 1)
    again = _thread("FFXIV EN Forum - Tank Roles", 301, "Tank feedback", 2)
    assert _run([first, again], caplog) == [first]
    assert _dedup_lines(caplog) == [
        "FFXIV 去重拿掉：FFXIV EN Forum - Tank Roles「Tank feedback」，"
        "與 FFXIV EN Forum - Tank Roles「Tank feedback」重複（同一串）"
    ]


def test_jaccard_duplicate_prints_one_line_with_the_score(caplog, quiet_dump):
    kept = _ranked(EVOLVED_HEALERS, "Reddit r/ffxiv", 20, 1)
    dropped = _ranked(EVOLVED_DPS, "FFXIV TW 修正說明", 20, 2)
    assert _run([kept, dropped], caplog) == [kept]
    assert _dedup_lines(caplog) == [
        f"FFXIV 去重拿掉：FFXIV TW 修正說明「{EVOLVED_DPS}」，"
        f"與 Reddit r/ffxiv「{EVOLVED_HEALERS}」重複（Jaccard 0.778 > 0.5）"
    ]


def test_title_inclusion_duplicate_prints_one_line(caplog, quiet_dump):
    kept = _ranked("FFXIV 7.2 更新 職業 調整 詳細 說明", hours=1)
    dropped = _ranked("FFXIV 更新", hours=2)
    assert _run([kept, dropped], caplog) == [kept]
    assert _dedup_lines(caplog) == [
        "FFXIV 去重拿掉：FFXIV Lodestone「FFXIV 更新」，"
        "與 FFXIV Lodestone「FFXIV 7.2 更新 職業 調整 詳細 說明」重複（標題包含）"
    ]


def test_forum_thread_against_other_source_still_compares_titles(caplog, quiet_dump):
    news = _ranked("Patch 7.4 Notes", "FFXIV Lodestone JP 更新資訊", 100, 1)
    thread = _thread("FFXIV EN Forum - Tank Roles", 401, "Patch 7.4 Notes", 2)
    assert _run([news, thread], caplog) == [news]
    assert _dedup_lines(caplog) == [
        "FFXIV 去重拿掉：FFXIV EN Forum - Tank Roles「Patch 7.4 Notes」，"
        "與 FFXIV Lodestone JP 更新資訊「Patch 7.4 Notes」重複（標題包含）"
    ]
