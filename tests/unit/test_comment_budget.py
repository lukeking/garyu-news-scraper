"""註解／docstring 區塊行數上限。超過就是該 refactor 的訊號，不是該多寫的訊號。

`LEGACY` 是**精確**的既有債務表：變壞會紅，變好也會紅，所以它不會腐朽成沒人更新的名單。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from comment_blocks import walk  # noqa: E402

_REPO = os.path.join(os.path.dirname(__file__), "..", "..")

MAX_LINES = 3

# 檔案 → (最長區塊行數, 超過 MAX_LINES 的區塊數)。兩個維度都是精確值。
# 還債時把對應那列一起改掉；整個檔清乾淨就把該列刪掉。
LEGACY = {
    ".design-sync/verify-bundle.mjs": (7, 1),
    "pages/shared/app.js": (9, 2),
    "scripts/auto_kb.py": (38, 8),
    "scripts/check_config_drift.py": (21, 2),
    "scripts/debug_dedup.py": (9, 1),
    "scripts/eval_gn_enrichment.py": (14, 1),
    "scripts/label_baseline.py": (16, 2),
    "scripts/measure_body_fetch.py": (13, 1),
    "scripts/measure_embed_dedup_gap.py": (24, 2),
    "scripts/measure_input_quality.py": (22, 11),
    "scripts/measure_relevance.py": (43, 11),
    "scripts/measure_source_uptake.py": (19, 5),
    "scripts/migrate_kb.py": (13, 1),
    "scripts/replay_digest_pool.py": (33, 1),
    "scripts/traffic_buffer.py": (17, 2),
    "scripts/traffic_weekly_analysis.py": (5, 3),
    "src/analyzer.py": (14, 19),
    "src/collector.py": (6, 6),
    "src/filter.py": (9, 11),
    "src/gn_resolver.py": (13, 5),
    "src/main.py": (5, 1),
    "src/pipeline/traffic.py": (6, 1),
    "src/pipeline_config.py": (11, 5),
    "src/publisher.py": (12, 6),
    "src/storage.py": (8, 13),
    "tests/integration/conftest.py": (16, 7),
    "tests/integration/test_digest_weekly.py": (6, 1),
    "tests/integration/test_game_feed.py": (4, 2),
    "tests/integration/test_novelty_weekly.py": (7, 1),
    "tests/integration/test_traffic_buffer.py": (6, 2),
    "tests/integration/test_weekly_analysis.py": (5, 2),
    "tests/js/harness.mjs": (12, 1),
    "tests/js/traffic-row.test.mjs": (15, 1),
    "tests/unit/test_auto_kb_patching.py": (18, 11),
    "tests/unit/test_check_config_drift.py": (7, 2),
    "tests/unit/test_comment_budget.py": (4, 1),
    "tests/unit/test_digest_consume.py": (7, 3),
    "tests/unit/test_digest_pool.py": (10, 4),
    "tests/unit/test_embed_dedup.py": (12, 2),
    "tests/unit/test_gn_resolver.py": (4, 1),
    "tests/unit/test_input_quality.py": (13, 4),
    "tests/unit/test_measure_embed_dedup_gap.py": (9, 2),
    "tests/unit/test_novelty_gate.py": (4, 1),
    "tests/unit/test_pipeline_config.py": (7, 3),
    "tests/unit/test_policy_source_gates.py": (5, 1),
    "tests/unit/test_relevance_gate.py": (6, 1),
    "tests/unit/test_relevance_token_table.py": (15, 4),
    "tests/unit/test_source_uptake.py": (6, 4),
    "tests/unit/test_text_normaliser.py": (4, 1),
    "tests/unit/test_traffic_buffer_daily_enrich.py": (6, 1),
    "tests/unit/test_weekly_selection.py": (12, 2),
    "workers/api/src/index.js": (7, 1),
}


def _current():
    out = {}
    for f, blocks in walk(_REPO).items():
        over = [n for _, n in blocks if n > MAX_LINES]
        if over:
            out[f] = (max(over), len(over))
    return out


def test_no_new_file_exceeds_the_budget():
    """沒登記在 LEGACY 的檔案，任何區塊都不得超過 MAX_LINES 行。"""
    new = sorted(set(_current()) - set(LEGACY))

    assert not new, (
        f"這些檔案有超過 {MAX_LINES} 行的註解／docstring 區塊：{new}\n"
        "先問：刪掉它會讓哪一條測試變紅？答不出來就是該刪的那幾行。"
        "刪不掉的寫進 commit／PR 內文，那裡不需要維護。"
    )


def test_legacy_files_do_not_get_worse():
    cur = _current()
    worse = {f: (LEGACY[f], cur[f]) for f in LEGACY if f in cur and cur[f] > LEGACY[f]}

    assert not worse, f"既有債務變大了（登記值 → 現值）：{worse}"


def test_legacy_table_is_exact_not_a_floor():
    """變好也要紅——否則這張表會慢慢變成一份沒人更新的名單，正是它要防的那種東西。"""
    cur = _current()
    stale = {f: (LEGACY[f], cur.get(f)) for f in LEGACY if cur.get(f) != LEGACY[f]}

    assert not stale, (
        f"LEGACY 與現況不符（登記值 → 現值，None 表示已清乾淨）：{stale}\n"
        "還完債就把那一列改掉或刪掉。"
    )
