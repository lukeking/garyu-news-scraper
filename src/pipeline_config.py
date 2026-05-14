"""
pipeline_config.py
Shared loader for pipeline_config.yml and categories_traffic.yml.
Used by src/filter.py (category assignment, quality scoring, Jaccard thresholds)
and src/analyzer.py (topic scoring, hot-topic selection).
"""

import logging
import math
import os

import yaml

logger = logging.getLogger(__name__)

_pipeline_config_cache: dict | None = None
_category_taxonomy_cache: dict | None = None

_DEFAULTS = {
    "jaccard": {
        "merge_threshold": 0.45,
        "cluster_lower": 0.20,
        "game_threshold": 0.50,
    },
    "topic_scoring": {
        "min_threshold": 1.5,
        "max_hot_topics": 3,
    },
    "buffer": {
        "max_age_weeks": 8,
    },
    "quality_score_weights": {
        "keyword_match_ratio": 0.4,
        "normalised_word_count": 0.3,
        "source_weight": 0.3,
    },
    "source_weights": {},
    "blocked_sources": [],
    "blocked_content_keywords": [],
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_pipeline_config(path: str | None = None) -> dict:
    global _pipeline_config_cache
    if _pipeline_config_cache is not None:
        return _pipeline_config_cache

    if path is None:
        path = os.environ.get("PIPELINE_CONFIG_YML_PATH", "config/pipeline_config.yml")

    config = _DEFAULTS.copy()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        config = _deep_merge(_DEFAULTS, loaded)
        _validate_pipeline_config(config, path)
        logger.info("[pipeline_config] 載入：%s", path)
    else:
        logger.warning("[pipeline_config] 設定檔不存在，使用預設值：%s", path)

    _pipeline_config_cache = config
    return config


def _validate_pipeline_config(config: dict, path: str) -> None:
    weights = config.get("quality_score_weights", {})
    total = sum(weights.get(k, 0) for k in ("keyword_match_ratio", "normalised_word_count", "source_weight"))
    if not math.isclose(total, 1.0, abs_tol=0.001):
        raise RuntimeError(
            f"[pipeline_config] quality_score_weights 加總必須為 1.0，"
            f"目前為 {total:.4f}（路徑：{path}）"
        )
    for key in ("merge_threshold", "cluster_lower", "game_threshold"):
        val = config.get("jaccard", {}).get(key, 0)
        if not (0.0 <= val <= 1.0):
            raise RuntimeError(
                f"[pipeline_config] jaccard.{key} 必須在 [0, 1]，目前為 {val}（路徑：{path}）"
            )


def load_category_taxonomy(path: str | None = None) -> dict:
    """
    Returns {category_label: [keyword, ...]} in definition order.
    Articles matching no category receive 'uncategorised'.
    Raises RuntimeError if the file is missing or unparseable.
    """
    global _category_taxonomy_cache
    if _category_taxonomy_cache is not None:
        return _category_taxonomy_cache

    if path is None:
        path = os.environ.get("CATEGORIES_TRAFFIC_YML_PATH", "config/categories_traffic.yml")

    if not os.path.exists(path):
        raise RuntimeError(
            f"[pipeline_config] 類別分類檔不存在：{path}。"
            "請將 config/categories_traffic.example.yml 複製為 config/categories_traffic.yml"
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    categories_raw = raw.get("categories", {})
    if not categories_raw:
        raise RuntimeError(f"[pipeline_config] categories_traffic.yml 中沒有有效的類別定義：{path}")

    taxonomy = {
        label: [str(kw).lower() for kw in entry.get("keywords", [])]
        for label, entry in categories_raw.items()
    }
    logger.info("[pipeline_config] 類別分類載入：%d 個類別", len(taxonomy))
    _category_taxonomy_cache = taxonomy
    return taxonomy


def reset_caches() -> None:
    """Reset module-level caches. Used in tests to reload config between test cases."""
    global _pipeline_config_cache, _category_taxonomy_cache
    _pipeline_config_cache = None
    _category_taxonomy_cache = None
