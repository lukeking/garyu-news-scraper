"""spec 015 T003：FFXIVCategory.filter() 在兩個去重步驟之前依排序鍵排序；沒設 weight 的來源各印一次警告。"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.pipeline.ffxiv import FFXIVCategory  # noqa: E402

CONFIG = {"jaccard": {"game_threshold": 0.50}}


def _recent(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def _filter(raw):
    with patch("src.storage.is_configured", return_value=False), \
         patch("src.pipeline_config.load_pipeline_config", return_value=CONFIG):
        return FFXIVCategory().filter(raw)


@pytest.mark.parametrize("listing_title, board_title", [
    ("knight adjustment thread", "knight adjustment thread"),          # 同標題：filter_and_deduplicate 擋
    ("knight adjustment", "knight adjustment thread part2"),           # 包含關係：game_deduplicate 擋
])
def test_higher_weight_duplicate_survives_dedupe(listing_title, board_title):
    listing = {
        "title": listing_title, "link": "https://forum/listing/1", "summary": "",
        "source": "FFXIV JP Forum", "published": "", "content_type": "ffxiv", "source_weight": 10,
    }
    board = {
        "title": board_title, "link": "https://forum/thread/1?p=9", "summary": "回覆全文",
        "source": "FFXIV JP Forum - TANK", "published": _recent(days=1),
        "content_type": "ffxiv", "source_weight": 80,
    }
    result = _filter([listing, board])
    assert [a["source"] for a in result] == ["FFXIV JP Forum - TANK"]
    assert result[0]["summary"] == "回覆全文"


def test_missing_weight_warned_once_per_source(caplog):
    raw = (
        [{"title": f"srca{i}", "source": "Src A", "published": _recent(hours=i), "content_type": "ffxiv"}
         for i in range(3)]
        + [{"title": f"srcb{i}", "source": "Src B", "published": "", "content_type": "ffxiv"} for i in range(2)]
        + [{"title": "srcc0", "source": "Src C", "published": "", "content_type": "ffxiv", "source_weight": 50}]
        + [{"title": "srcd0", "source": "Src D", "published": "", "content_type": "ffxiv", "source_weight": 0}]
    )
    with caplog.at_level(logging.INFO, logger="src.pipeline.ffxiv"):
        _filter(raw)

    msgs = [r.getMessage() for r in caplog.records if r.name == "src.pipeline.ffxiv"]
    assert msgs.count("Src A: 未設 weight，排在最後") == 1
    assert msgs.count("Src B: 未設 weight，排在最後") == 1
    assert not any(m.startswith(("Src C", "Src D")) for m in msgs)
