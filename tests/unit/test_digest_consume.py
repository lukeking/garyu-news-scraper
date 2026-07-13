"""
Unit tests for mark_articles_analyzed — US2 (010):
count return, empty-input short-circuit, fail-soft ERROR semantics.
(Runner-level consumption ordering is covered in tests/integration/test_digest_weekly.py.)
"""
import logging
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.storage import mark_articles_analyzed


def test_mark_returns_count_and_updates_by_link():
    client = MagicMock()
    with patch("src.storage._get_client", return_value=client):
        assert mark_articles_analyzed(["l1", "l2", "l3"]) == 3
    client.table.assert_called_once_with("articles")
    client.table.return_value.update.assert_called_once_with({"hot_topic_analyzed": True})
    client.table.return_value.update.return_value.in_.assert_called_once_with(
        "link", ["l1", "l2", "l3"]
    )


def test_mark_empty_links_returns_zero_without_touching_client():
    with patch("src.storage._get_client") as get_client:
        assert mark_articles_analyzed([]) == 0
    get_client.assert_not_called()


def test_mark_failure_logs_error_and_returns_zero(caplog):
    client = MagicMock()
    client.table.return_value.update.return_value.in_.return_value.execute.side_effect = \
        RuntimeError("boom")
    with patch("src.storage._get_client", return_value=client), \
         caplog.at_level(logging.ERROR):
        assert mark_articles_analyzed(["l1"]) == 0
    assert "mark_articles_analyzed 失敗" in caplog.text
