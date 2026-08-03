"""Unit test for the daily runner's og-enrichment wiring (scripts/traffic_buffer.py).

The daily buffer now runs the HTTP-only og prefetch (it used to run on Mondays only,
leaving most Google News rows unresolved — see specs/BACKLOG.md). It is gated by
buffer.daily_enrich, default on, with false as the kill-switch.
"""
import importlib.util
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_RUNNER_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "scripts", "traffic_buffer.py"
)


def _load_runner():
    spec = importlib.util.spec_from_file_location("traffic_buffer_under_test", _RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_cat():
    cat = MagicMock()
    cat.collect.return_value = ["raw"]
    cat.filter.return_value = [{"link": "https://news.google.com/rss/articles/X"}]
    cat.publish.return_value = "buffered 1"
    return cat


def _run_with(config):
    cat = _fake_cat()
    runner = _load_runner()
    with patch("src.pipeline.traffic.TrafficCategory", return_value=cat), \
         patch("src.pipeline_config.load_pipeline_config", return_value=config):
        runner.main()
    return cat


def test_daily_enrich_default_on_calls_prefetch():
    """Key absent → default on → prefetch runs (the feature turns on at merge)."""
    cat = _run_with({"buffer": {}})
    cat.prefetch.assert_called_once_with(cat.filter.return_value)
    cat.publish.assert_called_once_with(cat.filter.return_value)


def test_daily_enrich_false_skips_prefetch_but_still_buffers():
    """Kill-switch: daily_enrich=false stops enrichment, buffering still happens."""
    cat = _run_with({"buffer": {"daily_enrich": False}})
    cat.prefetch.assert_not_called()
    cat.publish.assert_called_once_with(cat.filter.return_value)
