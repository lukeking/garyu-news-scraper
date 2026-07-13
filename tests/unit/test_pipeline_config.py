"""
Unit tests for the category_digest config block — Foundational (010):
defaults padding, validation, and feature-off behaviour in pipeline_config.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.pipeline_config import load_pipeline_config, reset_caches


def _load(tmp_path, yaml_text):
    reset_caches()
    p = tmp_path / "pipeline_config.yml"
    p.write_text(yaml_text, encoding="utf-8")
    try:
        return load_pipeline_config(str(p))
    finally:
        reset_caches()


def test_missing_key_defaults_to_empty_off(tmp_path):
    config = _load(tmp_path, "topic_scoring:\n  min_threshold: 1.5\n")
    assert config["category_digest"] == {}


def test_partial_keys_padded_with_defaults(tmp_path):
    config = _load(tmp_path, (
        "category_digest:\n"
        "  道安政策:\n"
        "    trigger_count: 8\n"
    ))
    cfg = config["category_digest"]["道安政策"]
    assert cfg["trigger_count"] == 8
    assert cfg["quality_floor"] == 0.18
    assert cfg["max_articles"] == 15


def test_null_category_body_padded_with_all_defaults(tmp_path):
    config = _load(tmp_path, "category_digest:\n  道安政策:\n")
    cfg = config["category_digest"]["道安政策"]
    assert cfg == {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}


@pytest.mark.parametrize("bad_yaml", [
    "category_digest:\n  道安政策:\n    trigger_count: 0\n",
    "category_digest:\n  道安政策:\n    trigger_count: -3\n",
    "category_digest:\n  道安政策:\n    trigger_count: abc\n",
    "category_digest:\n  道安政策:\n    max_articles: 0\n",
    "category_digest:\n  道安政策:\n    quality_floor: 1.5\n",
    "category_digest:\n  道安政策:\n    quality_floor: -0.1\n",
])
def test_invalid_values_raise(tmp_path, bad_yaml):
    with pytest.raises(RuntimeError):
        _load(tmp_path, bad_yaml)
