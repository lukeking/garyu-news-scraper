"""
Unit tests for select_digest_pool — US1/US3 (010):
pool composition, effective-count trigger metric, quality-desc selection,
excluded_links (FR-006), and quality-floor boundaries (FR-008).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.analyzer import select_digest_pool

_CFG = {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}


def _art(idx, q=0.3, cat="道安政策"):
    return {
        "link": f"https://example.com/{idx}",
        "title": f"文章{idx}",
        "major_category": cat,
        "initial_quality_score": q,
        "source": f"來源{idx}",
        "published": "2026-07-01T00:00:00",
        "summary": "x",
    }


# ── US1: pool composition / selection / trigger metric ───────────────────────

def test_pool_filters_by_category():
    arts = [_art(1), _art(2, cat="機車事故"), _art(3)]
    selected, pool_all, eff = select_digest_pool(arts, "道安政策", _CFG, set())
    assert {a["link"] for a in pool_all} == {arts[0]["link"], arts[2]["link"]}
    assert eff == 2
    assert {a["link"] for a in selected} == {arts[0]["link"], arts[2]["link"]}


def test_selected_quality_desc_capped_at_max_articles():
    arts = [_art(i, q=0.20 + i * 0.01) for i in range(20)]  # 0.20..0.39, all valid
    selected, pool_all, eff = select_digest_pool(arts, "道安政策", _CFG, set())
    assert eff == 20
    assert len(pool_all) == 20
    assert len(selected) == 15
    qualities = [a["initial_quality_score"] for a in selected]
    assert qualities == sorted(qualities, reverse=True)
    # the 5 lowest-quality valid articles are the ones dropped
    assert min(qualities) > 0.24


def test_excluded_links_removed_everywhere():
    arts = [_art(i) for i in range(12)]
    excluded = {arts[0]["link"], arts[1]["link"]}
    selected, pool_all, eff = select_digest_pool(arts, "道安政策", _CFG, excluded)
    assert eff == 10
    assert len(pool_all) == 10
    assert not excluded & {a["link"] for a in pool_all}
    assert not excluded & {a["link"] for a in selected}


def test_pool_all_includes_low_quality_but_not_selected_nor_counted():
    arts = [_art(1, q=0.3), _art(2, q=0.05)]
    selected, pool_all, eff = select_digest_pool(arts, "道安政策", _CFG, set())
    assert len(pool_all) == 2          # 消耗涵蓋垃圾文
    assert eff == 1                    # 觸發計數不含
    assert {a["link"] for a in selected} == {arts[0]["link"]}  # 選材不含


def test_empty_pool_and_fully_excluded():
    assert select_digest_pool([], "道安政策", _CFG, set()) == ([], [], 0)
    arts = [_art(1), _art(2)]
    excluded = {a["link"] for a in arts}
    assert select_digest_pool(arts, "道安政策", _CFG, excluded) == ([], [], 0)


# ── US3: quality-floor boundaries（真實邊界值：垃圾 0.165 vs 最弱實文 0.193）────

def test_floor_excludes_known_junk_includes_weakest_real():
    junk = _art(1, q=0.165)      # 實案：「友善列印 - 新竹市政府交通處」
    weakest = _art(2, q=0.193)   # 實案：最弱的真實政策文
    selected, pool_all, eff = select_digest_pool([junk, weakest], "道安政策", _CFG, set())
    assert eff == 1
    assert {a["link"] for a in selected} == {weakest["link"]}
    assert len(pool_all) == 2    # 垃圾文仍在池內，會隨清池被消耗


def test_floor_exact_boundary_is_inclusive():
    at_floor = _art(1, q=0.18)
    selected, _, eff = select_digest_pool([at_floor], "道安政策", _CFG, set())
    assert eff == 1 and selected == [at_floor]


def test_custom_floor_applies():
    cfg = {**_CFG, "quality_floor": 0.30}
    arts = [_art(1, q=0.25), _art(2, q=0.35)]
    selected, pool_all, eff = select_digest_pool(arts, "道安政策", cfg, set())
    assert eff == 1
    assert {a["link"] for a in selected} == {arts[1]["link"]}
    assert len(pool_all) == 2


# ── 013: include_categories（匯流兄弟政策類別）─────────────────────────────
# 契約見 specs/013-policy-digest-pool-merge/contracts/digest-pool.md C1-5/C1-6、C2-*。


def _merge_cfg(cats, **over):
    return {**_CFG, "include_categories": cats, **over}


def test_merged_categories_enter_pool_and_effective():
    """C2-1／C2-2：兄弟類別文章進入 pool_all 與 effective 計數。"""
    arts = [
        _art(1, q=0.30, cat="道安政策"),
        _art(2, q=0.35, cat="路權政策"),
        _art(3, q=0.32, cat="科技執法"),
        _art(4, q=0.31, cat="交通工程"),
        _art(5, q=0.40, cat="機車事故"),   # 不在清單內 → 不得進池
    ]
    cfg = _merge_cfg(["路權政策", "科技執法", "交通工程"])
    selected, pool_all, effective = select_digest_pool(arts, "道安政策", cfg, set())

    assert {a["major_category"] for a in pool_all} == {
        "道安政策", "路權政策", "科技執法", "交通工程",
    }
    assert len(pool_all) == 4
    assert effective == 4
    assert "機車事故" not in {a["major_category"] for a in selected}


def test_merged_respects_excluded_links():
    """C2-4／INV-3：匯流不得繞過既有排除清單。"""
    arts = [_art(1, cat="道安政策"), _art(2, cat="路權政策")]
    cfg = _merge_cfg(["路權政策"])
    selected, pool_all, effective = select_digest_pool(
        arts, "道安政策", cfg, {"https://example.com/2"}
    )
    links = {a["link"] for a in pool_all}
    assert "https://example.com/2" not in links
    assert len(pool_all) == 1 and effective == 1
    assert "https://example.com/2" not in {a["link"] for a in selected}


def test_self_inclusion_does_not_double_count():
    """C1-5／INV-6：清單含主類別自己時去重，同一 link 至多出現一次。"""
    arts = [_art(1, cat="道安政策"), _art(2, cat="路權政策")]
    cfg = _merge_cfg(["道安政策", "路權政策"])
    selected, pool_all, effective = select_digest_pool(arts, "道安政策", cfg, set())
    assert len(pool_all) == 2
    assert len({a["link"] for a in pool_all}) == 2
    assert effective == 2
    assert len(selected) == 2


def test_list_order_does_not_affect_output():
    """C1-6：清單順序不影響任何輸出（含 selected 的排列）。"""
    arts = [
        _art(1, q=0.30, cat="道安政策"),
        _art(2, q=0.35, cat="路權政策"),
        _art(3, q=0.32, cat="科技執法"),
    ]
    a = select_digest_pool(arts, "道安政策", _merge_cfg(["路權政策", "科技執法"]), set())
    b = select_digest_pool(arts, "道安政策", _merge_cfg(["科技執法", "路權政策"]), set())
    assert [x["link"] for x in a[0]] == [x["link"] for x in b[0]]
    assert [x["link"] for x in a[1]] == [x["link"] for x in b[1]]
    assert a[2] == b[2]


def test_unknown_category_in_list_contributes_nothing():
    """設定含不存在的類別名時，選材端只是比不到（零篇），不得爆炸。
    留痕的責任在設定載入端的 WARNING（見 test_pipeline_config）。"""
    arts = [_art(1, cat="道安政策")]
    cfg = _merge_cfg(["不存在的類別"])
    selected, pool_all, effective = select_digest_pool(arts, "道安政策", cfg, set())
    assert len(pool_all) == 1 and effective == 1 and len(selected) == 1


# ── 013 US3: 可逆性（INV-1／INV-2）────────────────────────────────────────


def test_absent_include_categories_is_byte_identical_to_before():
    """INV-1／C2-6 ＝ FR-002「預設關閉」。

    ⚠️ **這條是整個「預設不改變行為」保證的唯一守門員。** 若它是空的，
    任何人把 include_categories 的預設從 [] 改成非空都不會有東西擋——
    而那會靜默改變已發布的週報內容。
    """
    arts = [
        _art(1, q=0.30, cat="道安政策"),
        _art(2, q=0.35, cat="路權政策"),
        _art(3, q=0.20, cat="道安政策"),
        _art(4, q=0.10, cat="道安政策"),   # 低於 floor
    ]
    without_key = select_digest_pool(arts, "道安政策", _CFG, set())
    empty_list = select_digest_pool(arts, "道安政策", _merge_cfg([]), set())

    for a, b in zip(without_key, empty_list):
        assert a == b
    selected, pool_all, effective = without_key
    # 逐篇相同 ＝ 兄弟類別文章一篇都不得進來
    assert [x["link"] for x in pool_all] == [
        "https://example.com/1", "https://example.com/3", "https://example.com/4",
    ]
    assert effective == 2
    assert [x["link"] for x in selected] == [
        "https://example.com/1", "https://example.com/3",
    ]


def test_merge_does_not_mutate_major_category():
    """INV-2 ＝ FR-003：選材不得改寫文章的分類標記。

    012 的 partition_by_relevance 會原地附加 `_relevance_reason`；本功能刻意
    **不**沿用那個做法——匯流只影響成員判定，buffer list 的細分類必須保留。
    """
    arts = [
        _art(1, cat="道安政策"),
        _art(2, cat="路權政策"),
        _art(3, cat="科技執法"),
    ]
    before = [a["major_category"] for a in arts]
    before_keys = [set(a.keys()) for a in arts]

    select_digest_pool(arts, "道安政策", _merge_cfg(["路權政策", "科技執法"]), set())

    assert [a["major_category"] for a in arts] == before == [
        "道安政策", "路權政策", "科技執法",
    ]
    assert [set(a.keys()) for a in arts] == before_keys, "不得在輸入物件上新增欄位"
