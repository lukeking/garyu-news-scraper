"""不發布時不留下讀起來像「寫完了」「什麼都沒有」的既有訊息；漏斗欄位名照位置對（spec 020 FR-007、FR-008）。
來自 59442c7 那一輪 review 的兩條非阻擋 finding。邊界只換 Supabase 的設定判斷、寫入函式與類別清單。
"""
import json
import logging
import os
import sys
from unittest.mock import patch

import dotenv
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import publisher, storage  # noqa: E402
from src.pipeline.traffic import TrafficCategory, funnel_line  # noqa: E402

with patch.object(dotenv, "load_dotenv", return_value=False), patch.object(logging, "basicConfig"):
    from src import main as main_mod  # noqa: E402

_ARTICLE = {"title": "甲", "link": "https://x/1", "source": "s"}
_EVERY_CATEGORY_EMPTY = "所有 category 均無文章，結束執行"


def _messages(caplog):
    return [r.getMessage() for r in caplog.records]


def _traffic(monkeypatch):
    cat = TrafficCategory()
    monkeypatch.setattr(cat, "_buffer_max_age_weeks", lambda: 8)
    return cat


def test_collected_json_names_each_funnel_stage_by_position(monkeypatch, tmp_path):
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-input")
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(tmp_path))
    cat = _traffic(monkeypatch)
    counts = (8, 7, 6, 5, 4, 3, 2, 1)
    cat.last_funnel = {"來源甲": counts}
    cat._dump_collected([])
    data = json.loads((tmp_path / "collected.json").read_text(encoding="utf-8"))
    assert data["sources"] == [{
        "source": "來源甲", "collected": 8, "after_freshness": 7, "after_keyword_filter": 6,
        "after_source_block": 5, "after_batch_dedup": 4, "after_vector_dedup": 3,
        "kept": 2, "kept_in_confluence": 1,
    }]
    line = funnel_line("來源甲", counts)
    assert "收集 8" in line and "匯流四類 1" in line


@pytest.mark.parametrize("mode", ["dry-input", "dry-full"])
def test_traffic_publish_does_not_say_written_in_a_dry_mode(mode, monkeypatch, tmp_path, caplog):
    monkeypatch.setenv("GARYU_RUN_MODE", mode)
    monkeypatch.setenv("TRAFFIC_POOL_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "is_configured", lambda: True)
    cat = _traffic(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        cat.publish([_ARTICLE])
    msgs = _messages(caplog)
    assert "[不發布] 略過 upsert_traffic_buffer：1 筆" in msgs
    assert not [m for m in msgs if "寫入完成" in m]


def test_traffic_publish_still_says_written_in_formal_mode(monkeypatch, caplog):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upsert_traffic_buffer", lambda articles, week_id, max_age_weeks=8: 3)
    cat = _traffic(monkeypatch)
    with caplog.at_level(logging.DEBUG):
        cat.publish([_ARTICLE])
    assert [m for m in _messages(caplog) if "buffer 寫入完成：3 筆" in m]


def test_publisher_does_not_say_written_in_a_dry_mode(monkeypatch, caplog):
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-full")
    monkeypatch.setattr(storage, "is_configured", lambda: True)
    with caplog.at_level(logging.DEBUG):
        publisher._save_to_supabase([_ARTICLE], "2026-W46")
    msgs = _messages(caplog)
    assert "[不發布] 略過 upsert_articles：1 筆" in msgs
    assert not [m for m in msgs if "寫入完成" in m]


def test_publisher_still_says_written_in_formal_mode(monkeypatch, caplog):
    monkeypatch.delenv("GARYU_RUN_MODE", raising=False)
    monkeypatch.setattr(storage, "is_configured", lambda: True)
    monkeypatch.setattr(storage, "upsert_articles", lambda articles, week_id: 2)
    with caplog.at_level(logging.DEBUG):
        publisher._save_to_supabase([_ARTICLE], "2026-W46")
    assert [m for m in _messages(caplog) if "Supabase 寫入完成：2 筆" in m]


class _Category:
    def __init__(self, name, llm_stage, filtered):
        self.name, self.llm_stage, self._filtered = name, llm_stage, filtered

    def collect(self):
        return ["raw"]

    def filter(self, raw):
        return self._filtered

    def analyze(self, articles):
        return articles

    def publish(self, articles):
        return ""


def _run_main(monkeypatch, caplog, ffxiv_filtered):
    monkeypatch.setenv("GARYU_RUN_MODE", "dry-input")
    monkeypatch.setattr(main_mod, "CATEGORIES", [
        _Category("traffic", None, []), _Category("ffxiv", "FFXIV 分析", ffxiv_filtered),
    ])
    with caplog.at_level(logging.DEBUG), pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == 0
    return _messages(caplog)


def test_level_one_exit_after_a_stop_does_not_claim_every_category_was_empty(monkeypatch, caplog):
    msgs = _run_main(monkeypatch, caplog, [{"title": "乙"}])
    assert "[不發布] 第一級在 FFXIV 分析 之前停下" in msgs
    assert _EVERY_CATEGORY_EMPTY not in msgs
    assert "第一級已在分析之前停下，其餘 category 沒有文章，結束執行" in msgs


def test_level_one_exit_with_nothing_anywhere_keeps_the_existing_warning(monkeypatch, caplog):
    msgs = _run_main(monkeypatch, caplog, [])
    assert _EVERY_CATEGORY_EMPTY in msgs
    assert not [m for m in msgs if "之前停下" in m]
