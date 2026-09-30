"""GNS-015：來源失敗要出聲——每次印彙總行，失敗比例超過一半讓 daily job 失敗。"""
import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src import collector  # noqa: E402

_EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>t</title></channel></rss>'


def _rss_bytes(url):
    if url == "https://bad":
        raise RuntimeError("503 Server Error: Service Unavailable")
    return _EMPTY_RSS


def _collect(sources, caplog):
    with patch.object(collector, "_fetch_rss_bytes", side_effect=_rss_bytes), \
         patch("requests.Session.get", side_effect=RuntimeError("403 Client Error: Forbidden")), \
         patch.object(collector, "_build_youtube_client", return_value=None), \
         patch.object(collector.time, "sleep"), \
         caplog.at_level(logging.INFO, logger="src.collector"):
        return collector.collect_sources(sources)


def test_real_fetcher_failures_are_counted_and_summarised(caplog):
    sources = [
        {"name": "GN-ok", "type": "rss", "url": "https://ok"},
        {"name": "GN-bad", "type": "rss", "url": "https://bad"},
        {"name": "PTT/biker", "type": "ptt", "board": "biker"},
        {"name": "YT", "type": "youtube", "channel_id": "UCx"},
    ]
    _collect(sources, caplog)
    assert collector.last_collect_failures() == (["GN-bad", "PTT/biker", "YT"], 4)
    assert "來源失敗：3/4（GN-bad、PTT/biker、YT）" in caplog.text
    # 原本的逐筆格式不變：週驗收 routine 的 FOCUS (3) 會 grep `失敗: 503`
    assert "GN-bad 失敗: 503 Server Error" in caplog.text


def test_summary_is_printed_even_with_zero_failures(caplog):
    _collect([{"name": "GN-ok", "type": "rss", "url": "https://ok"}], caplog)
    assert collector.last_collect_failures() == ([], 1)
    assert "來源失敗：0/1" in caplog.text


def test_failures_do_not_carry_over_between_calls(caplog):
    _collect([{"name": "GN-bad", "type": "rss", "url": "https://bad"}], caplog)
    _collect([{"name": "GN-ok", "type": "rss", "url": "https://ok"}], caplog)
    assert collector.last_collect_failures() == ([], 1)


@pytest.mark.parametrize("failed, attempted, expected", [
    (1, 2, False),     # 剛好一半不算
    (16, 33, False),   # 48.5%
    (17, 33, True),    # 51.5%
    (25, 33, True),    # 09-13 事故
    (2, 33, False),    # 09-17 起每天的 PTT 403
    (0, 0, False),     # 沒有來源
])
def test_threshold_is_more_than_half(failed, attempted, expected):
    assert collector.too_many_source_failures(failed, attempted) is expected


# ── scripts/traffic_buffer.py：超過一半就 exit 1，但已收到的照樣寫入 buffer ──

_RUNNER_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "traffic_buffer.py")


def _run_runner(failures, cat):
    spec = importlib.util.spec_from_file_location("traffic_buffer_ratio_test", _RUNNER_PATH)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    with patch("src.pipeline.traffic.TrafficCategory", return_value=cat), \
         patch("src.pipeline_config.load_pipeline_config", return_value={"buffer": {}}), \
         patch.object(collector, "last_collect_failures", return_value=failures):
        runner.main()


def _fake_cat():
    cat = MagicMock()
    cat.collect.return_value = []
    cat.filter.return_value = []
    return cat


def test_runner_exits_nonzero_but_buffers_first_when_most_sources_fail():
    cat = _fake_cat()
    with pytest.raises(SystemExit) as exc:
        _run_runner((["s"] * 25, 33), cat)
    assert exc.value.code == 1
    cat.publish.assert_called_once()


def test_runner_does_not_fail_on_everyday_failures():
    cat = _fake_cat()
    _run_runner((["PTT/biker", "PTT/SuperBike"], 33), cat)
    cat.publish.assert_called_once()
