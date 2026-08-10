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
    assert cfg == {
        "trigger_count": 10,
        "quality_floor": 0.18,
        "max_articles": 15,
        "include_categories": [],
    }


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


# ── include_categories（013 匯流清單）──────────────────────────────
# 契約見 specs/013-policy-digest-pool-merge/contracts/digest-pool.md C1-1..C1-4。


def test_include_categories_defaults_to_empty_list(tmp_path):
    """C1-1：缺鍵補 []。這是 FR-002「預設關閉」的結構保證——空清單使有效類別
    集合退化為 {主類別}，行為與本功能不存在時相同。"""
    config = _load(tmp_path, "category_digest:\n  道安政策:\n    trigger_count: 8\n")
    assert config["category_digest"]["道安政策"]["include_categories"] == []


def test_include_categories_passed_through(tmp_path):
    config = _load(tmp_path, (
        "category_digest:\n"
        "  道安政策:\n"
        "    include_categories: [路權政策, 科技執法]\n"
    ))
    cfg = config["category_digest"]["道安政策"]
    assert cfg["include_categories"] == ["路權政策", "科技執法"]


@pytest.mark.parametrize("bad_yaml", [
    # C1-2：非 list
    "category_digest:\n  道安政策:\n    include_categories: 路權政策\n",
    "category_digest:\n  道安政策:\n    include_categories: 5\n",
    "category_digest:\n  道安政策:\n    include_categories: {a: 1}\n",
    # C1-3：元素非字串
    "category_digest:\n  道安政策:\n    include_categories: [路權政策, 5]\n",
    "category_digest:\n  道安政策:\n    include_categories: [[路權政策]]\n",
])
def test_include_categories_invalid_type_raises(tmp_path, bad_yaml):
    """C1-2／C1-3：型別錯誤是設定錯誤，直接 RuntimeError。"""
    with pytest.raises(RuntimeError):
        _load(tmp_path, bad_yaml)


def _load_with_known(tmp_path, yaml_text, known):
    reset_caches()
    p = tmp_path / "pipeline_config.yml"
    p.write_text(yaml_text, encoding="utf-8")
    try:
        return load_pipeline_config(str(p), known_categories=known)
    finally:
        reset_caches()


_KNOWN = {"道安政策", "路權政策", "科技執法", "交通工程", "機車事故"}


def test_unknown_category_warns_but_does_not_abort(tmp_path, caplog):
    """C1-4：類別名合法但不存在於分類法 → WARNING 且流程繼續。

    ⚠️ 這條守的是憲章原則 I「silent failures are forbidden」。
    spec 初稿寫「忽略該項」，靜默忽略會直接違憲；fail-soft（不因打錯字讓整份
    週報掛掉）與「錯誤要留痕」的交集就是 WARNING。**若把 logger.warning 拿掉，
    這條必須變紅**——否則它就是空的。
    """
    import logging

    with caplog.at_level(logging.WARNING):
        config = _load_with_known(tmp_path, (
            "category_digest:\n"
            "  道安政策:\n"
            "    include_categories: [路權政策, 不存在的類別]\n"
        ), _KNOWN)
    # 不中止，且值原樣保留（下游以集合比對，比不到就是零篇）
    assert config["category_digest"]["道安政策"]["include_categories"] == [
        "路權政策", "不存在的類別",
    ]
    assert any("不存在的類別" in r.message for r in caplog.records), (
        "未知類別名必須留下 WARNING 痕跡（憲章 I：禁止靜默失敗）"
    )


def test_known_categories_do_not_warn(tmp_path, caplog):
    """反面：全部合法時不得產生噪音警告，否則 WARNING 會失去訊號價值。"""
    import logging

    with caplog.at_level(logging.WARNING):
        _load_with_known(tmp_path, (
            "category_digest:\n"
            "  道安政策:\n"
            "    include_categories: [路權政策, 科技執法, 交通工程]\n"
        ), _KNOWN)
    assert not [r for r in caplog.records if "include_categories" in r.message]


def test_existence_check_skipped_without_taxonomy(tmp_path, caplog):
    """`known_categories=None`（預設）時跳過存在性檢查，不得 raise、不得 WARNING。

    ⚠️ 這條是 CI 相容性的守門員：`.github/workflows/tests.yml` 只跑
    `pytest tests/unit`，**不寫任何 config 檔**，而 `load_category_taxonomy` 在
    檔案缺席時會 RuntimeError。若哪天有人把分類法載入直接寫進
    `load_pipeline_config`，這條會變紅——那正是它存在的理由。
    """
    import logging

    with caplog.at_level(logging.WARNING):
        config = _load(tmp_path, (
            "category_digest:\n"
            "  道安政策:\n"
            "    include_categories: [完全不存在的類別]\n"
        ))
    assert config["category_digest"]["道安政策"]["include_categories"] == ["完全不存在的類別"]
    assert not [r for r in caplog.records if "include_categories" in r.message]
