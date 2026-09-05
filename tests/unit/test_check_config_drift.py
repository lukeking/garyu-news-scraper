"""`scripts/check_config_drift.py` 的測試。

**為什麼判準是「解析後的值」而不是「逐字相同」**：2026-09-05 實測 prod 的
`PIPELINE_CONFIG_YML` 有 104/105 行是 CRLF，而 `pipeline_config.example.yml` 是 LF
且刻意多 14 行註解。逐字比對會天天誤報，天天誤報的檢查最後一定會被關掉——
所以第一條測試（註解與行尾不同仍判為相符）是這支腳本能不能活下去的關鍵。
"""
import io
import os
import sys

import pytest

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import check_config_drift as drift  # noqa: E402


def _write(path, text, crlf=False):
    data = text.encode("utf-8")
    if crlf:
        data = data.replace(b"\n", b"\r\n")
    io.open(path, "wb").write(data)
    return str(path)


# ── 判準本身：值相同就算相符，格式差異不算漂移 ──────────────────────────────

def test_same_values_different_comments_and_line_endings_is_not_drift(tmp_path):
    """這條是整支腳本的判準。壞掉的話檢查會天天誤報，然後被關掉。"""
    runtime = _write(tmp_path / "r.yml", "buffer:\n  max_age_weeks: 8\n", crlf=True)
    example = _write(
        tmp_path / "e.yml",
        "# 這裡有一段 example 才有的長註解，說明這個值是怎麼推導出來的\nbuffer:\n"
        "  max_age_weeks: 8   # 超過這個週數就從 buffer 過期\n",
    )

    assert drift.compare(runtime, example) == []


# ── 真正的漂移要被抓到，而且要指出是哪一個鍵 ────────────────────────────────

def test_changed_scalar_is_reported_with_its_key_path(tmp_path):
    runtime = _write(tmp_path / "r.yml", "topic_scoring:\n  min_threshold: 1.5\n")
    example = _write(tmp_path / "e.yml", "topic_scoring:\n  min_threshold: 1.2\n")

    problems = drift.compare(runtime, example)

    assert len(problems) == 1
    assert "topic_scoring.min_threshold" in problems[0], "報告要指出是哪一個鍵漂了"
    assert "1.5" in problems[0] and "1.2" in problems[0], "兩邊的值都要印出來"


def test_key_present_on_only_one_side_is_reported(tmp_path):
    runtime = _write(tmp_path / "r.yml", "buffer:\n  max_age_weeks: 8\n  daily_enrich: true\n")
    example = _write(tmp_path / "e.yml", "buffer:\n  max_age_weeks: 8\n")

    problems = drift.compare(runtime, example)

    assert len(problems) == 1
    assert "buffer.daily_enrich" in problems[0]


def test_list_difference_is_reported_with_index(tmp_path):
    """來源／關鍵字清單是 list，漂移最常發生在這裡——路徑要帶索引才定位得到。"""
    runtime = _write(tmp_path / "r.yml", 'blocked_sources:\n  - "三立"\n  - "民視"\n')
    example = _write(tmp_path / "e.yml", 'blocked_sources:\n  - "三立"\n')

    problems = drift.compare(runtime, example)

    assert len(problems) == 1
    assert "blocked_sources[1]" in problems[0]


# ── 讀不到 ≠ 沒問題 ────────────────────────────────────────────────────────

def test_missing_runtime_file_is_a_failure_not_a_silent_skip(tmp_path):
    """靜靜跳過的檢查與通過的檢查在輸出上長得一樣——所以讀不到必須判為失敗。"""
    example = _write(tmp_path / "e.yml", "a: 1\n")

    problems = drift.compare(str(tmp_path / "does_not_exist.yml"), example)

    assert len(problems) == 1
    assert "讀不到" in problems[0]


def test_missing_example_file_is_a_failure(tmp_path):
    runtime = _write(tmp_path / "r.yml", "a: 1\n")

    problems = drift.compare(runtime, str(tmp_path / "does_not_exist.yml"))

    assert len(problems) == 1
    assert "讀不到" in problems[0]


def test_unparseable_yaml_is_a_failure(tmp_path):
    runtime = _write(tmp_path / "r.yml", "a: [1, 2\n")   # 未閉合
    example = _write(tmp_path / "e.yml", "a: 1\n")

    problems = drift.compare(runtime, example)

    assert len(problems) == 1
    assert "不是合法 YAML" in problems[0]


# ── 清單本身：sources_* 刻意不在裡面 ────────────────────────────────────────

def test_only_declared_mirrors_are_checked(tmp_path):
    """`sources_traffic` / `sources_ffxiv` 的 example 是**格式範本**不是 prod 鏡像
    （檔頭自稱「格式範例，說明所有支援的欄位與 type」；2026-09-05 實測 prod 33 個
    來源 vs example 24 個）。把它們加進來會得到一個天天紅然後被忽略的檢查。

    這條是守門員：有人日後「順手補完」清單時它會紅，並被迫先讀上面這段理由。
    """
    checked = {runtime for runtime, _ in drift.MIRRORED}

    assert checked == {"config/categories_traffic.yml", "config/pipeline_config.yml"}
