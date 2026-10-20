"""spec 015 T015（FR-005）：PLL 與更新的 Reddit 並存時 PLL 入選。權重寫字面值，不讀設定檔。"""
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.pipeline.ffxiv import FFXIVCategory  # noqa: E402

CONFIG = {"jaccard": {"game_threshold": 0.50}}

PLL = "FFXIV JP Forum - プロデューサーレターLIVE"
BOARD = "FFXIV JP Forum - TANK"
REDDIT = "Reddit r/ffxiv"
LISTING = "FFXIV JP Forum"


def _art(title, source, weight, published):
    return {
        "title": title, "link": f"https://example/{title}", "summary": "",
        "source": source, "published": published, "content_type": "ffxiv", "source_weight": weight,
    }


def test_pll_enters_alongside_newer_reddit():
    now = datetime.now(timezone.utc)
    reddit_times = [now - timedelta(minutes=38 * i) for i in range(25)]   # 最近 16 小時內
    pll_time = max(reddit_times) - timedelta(days=6)

    raw = (
        [_art(f"listing{i:02d}", LISTING, 10, "") for i in range(15)]
        + [_art(f"reddit{i:02d}", REDDIT, 20, t.isoformat()) for i, t in enumerate(reddit_times)]
        + [_art(f"board{i}", BOARD, 80, (now - timedelta(days=2, hours=i)).isoformat()) for i in range(3)]
        + [_art("pll90", PLL, 100, pll_time.isoformat())]
    )
    with patch("src.storage.is_configured", return_value=False), \
         patch("src.pipeline_config.load_pipeline_config", return_value=CONFIG):
        selected = FFXIVCategory().filter(raw)

    assert len(selected) == 20
    assert Counter(a["source"] for a in selected) == {PLL: 1, BOARD: 3, REDDIT: 16}
