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
_source_defaults_cache: dict | None = None
_relevance_rules_cache: dict | None = None

_DEFAULTS = {
    "jaccard": {
        "merge_threshold": 0.45,
        "cluster_lower": 0.20,
        "game_threshold": 0.50,
    },
    "topic_scoring": {
        "min_threshold": 1.5,
        "max_hot_topics": 3,
        "novelty_growth_pct": 0.5,
        "category_min_threshold": {},
    },
    "topic_identity": {
        "similarity_threshold": 0.3,
    },
    "buffer": {
        "max_age_weeks": 8,
    },
    # 低頻類別聚合（feature 010）：{major_category: {trigger_count, quality_floor,
    # max_articles}}。空 = feature off。子鍵可省略，於驗證時補預設值。
    "category_digest": {},
    "embed_dedup": {
        "threshold": 0.88,
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
    npct = config.get("topic_scoring", {}).get("novelty_growth_pct", 0)
    if npct < 0:
        raise RuntimeError(
            f"[pipeline_config] topic_scoring.novelty_growth_pct 必須 ≥ 0，目前為 {npct}（路徑：{path}）"
        )
    for cat, val in (config.get("topic_scoring", {}).get("category_min_threshold") or {}).items():
        if not isinstance(val, (int, float)) or val < 0:
            raise RuntimeError(
                f"[pipeline_config] topic_scoring.category_min_threshold['{cat}'] 必須為 ≥ 0 的數值，"
                f"目前為 {val!r}（路徑：{path}）"
            )
    sim = config.get("topic_identity", {}).get("similarity_threshold", 0)
    if not (0.0 <= sim <= 1.0):
        raise RuntimeError(
            f"[pipeline_config] topic_identity.similarity_threshold 必須在 [0, 1]，目前為 {sim}（路徑：{path}）"
        )
    # category_digest：驗證並補齊 per-category 預設值。_deep_merge 只合併頂層
    # 結構、不會替各類別缺的子鍵補值，故補齊的 owner 在這裡（010 contracts U2）。
    digest_defaults = {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}
    digests = config.get("category_digest") or {}
    for cat, raw_cfg in digests.items():
        if raw_cfg is None:
            raw_cfg = {}
        if not isinstance(raw_cfg, dict):
            raise RuntimeError(
                f"[pipeline_config] category_digest['{cat}'] 必須為 map，目前為 {raw_cfg!r}（路徑：{path}）"
            )
        merged = {**digest_defaults, **raw_cfg}
        for key in ("trigger_count", "max_articles"):
            val = merged[key]
            if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                raise RuntimeError(
                    f"[pipeline_config] category_digest['{cat}'].{key} 必須為正整數，"
                    f"目前為 {val!r}（路徑：{path}）"
                )
        floor = merged["quality_floor"]
        if isinstance(floor, bool) or not isinstance(floor, (int, float)) or not (0.0 <= floor <= 1.0):
            raise RuntimeError(
                f"[pipeline_config] category_digest['{cat}'].quality_floor 必須在 [0, 1]，"
                f"目前為 {floor!r}（路徑：{path}）"
            )
        digests[cat] = merged
    config["category_digest"] = digests


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


def load_source_default_categories(path: str | None = None) -> dict:
    """
    Returns {source_name_substring: major_category} from categories_traffic.yml's
    optional `source_defaults` key. Used as a fallback when title-token category
    assignment yields 'uncategorised'. Missing key or file → {} (feature off).
    """
    global _source_defaults_cache
    if _source_defaults_cache is not None:
        return _source_defaults_cache

    if path is None:
        path = os.environ.get("CATEGORIES_TRAFFIC_YML_PATH", "config/categories_traffic.yml")

    mapping: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        mapping = {str(k): str(v) for k, v in (raw.get("source_defaults") or {}).items()}
        if mapping:
            logger.info("[pipeline_config] source_defaults 載入：%d 條", len(mapping))
    else:
        logger.warning("[pipeline_config] source_defaults 略過，分類檔不存在：%s", path)

    _source_defaults_cache = mapping
    return mapping


def load_relevance_rules(path: str | None = None) -> dict:
    """
    Returns {major_category: {"require_any": [...], "exclude_any": [...]}} from
    categories_traffic.yml's optional `relevance_rules` key (feature 012). Used by the
    weekly relevance gate (src/filter.py partition_by_relevance). Mirrors the shape of
    load_source_default_categories().

    Fail-open (see data-model §1): missing file/key → {}; a category whose spec is not a
    dict, or whose require/exclude values are not lists, is skipped (that category simply
    isn't gated) rather than raising — the gate must never kill a whole category on a
    config typo.
    """
    global _relevance_rules_cache
    if _relevance_rules_cache is not None:
        return _relevance_rules_cache

    if path is None:
        path = os.environ.get("CATEGORIES_TRAFFIC_YML_PATH", "config/categories_traffic.yml")

    rules: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw_rules = raw.get("relevance_rules") or {}
        if isinstance(raw_rules, dict):
            for cat, spec in raw_rules.items():
                if not isinstance(spec, dict):
                    logger.warning(
                        "[pipeline_config] relevance_rules.%s 非 dict，略過該類別（fail-open）", cat
                    )
                    continue
                entry: dict = {}
                for key in ("require_any", "exclude_any"):
                    vals = spec.get(key)
                    if isinstance(vals, list):
                        entry[key] = [str(t) for t in vals if t]
                if entry:
                    rules[str(cat)] = entry
        else:
            logger.warning("[pipeline_config] relevance_rules 非 dict，整組略過（fail-open）")
        if rules:
            logger.info("[pipeline_config] relevance_rules 載入：%d 個類別", len(rules))
    else:
        logger.warning("[pipeline_config] relevance_rules 略過，分類檔不存在：%s", path)

    _relevance_rules_cache = rules
    return rules


def reset_caches() -> None:
    """Reset module-level caches. Used in tests to reload config between test cases."""
    global _pipeline_config_cache, _category_taxonomy_cache, _source_defaults_cache
    global _relevance_rules_cache
    _pipeline_config_cache = None
    _category_taxonomy_cache = None
    _source_defaults_cache = None
    _relevance_rules_cache = None
