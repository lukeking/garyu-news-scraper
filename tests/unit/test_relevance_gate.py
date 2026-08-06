"""
Unit tests for the relevance gate — is_topic_relevant() / partition_by_relevance() — US1 (012).

子字串比對（不用 jieba），whitelist-dominant：類別有 require_any 時 exclude_any 不生效。
規則以參數傳入，不載入 YAML、不 import pipeline_config。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.filter import is_topic_relevant, partition_by_relevance

# ── inline rules（本 seed 為白名單；閘以參數收規則）──────────────────────────
MOTO_RULE = {
    "require_any": ["撞", "車禍", "事故", "肇事", "送醫", "不治", "傷", "亡", "死", "失控"],
}
BOTH_RULE = {                       # 兩名單都給 → require 主導、exclude 不生效
    "require_any": ["撞"],
    "exclude_any": ["毒駕"],
}
BLACKLIST_RULE = {                  # 只給 exclude_any → 純黑名單支
    "exclude_any": ["廣告", "促銷"],
}


# ── is_topic_relevant (pure predicate) ────────────────────────────────────────

def test_require_pass_real_accident():
    """(a) 真事故：擦撞送醫不治 / 自撞1死2傷 命中 require token → on-topic。"""
    assert is_topic_relevant({"title": "騎士遭撞擦撞送醫不治"}, MOTO_RULE) is True
    assert is_topic_relevant({"title": "機車自撞1死2傷"}, MOTO_RULE) is True


def test_no_accident_token_excluded():
    """(b) 純刑案：涉竊/通緝、毒駕羈押（無事故 token）→ off-topic，因 require 未命中（非靠 exclude）。"""
    assert is_topic_relevant({"title": "男子涉竊機車遭通緝"}, MOTO_RULE) is False
    assert is_topic_relevant({"title": "毒駕羈押獲交保"}, MOTO_RULE) is False


def test_boundary_crime_and_accident_kept():
    """(c) 邊界（刑案∩事故）：肇事逃逸 / 毒駕撞死 命中 require token → kept（回歸關鍵案）。"""
    assert is_topic_relevant({"title": "駕駛肇事逃逸被起訴"}, MOTO_RULE) is True
    assert is_topic_relevant({"title": "毒駕撞死路人送辦"}, MOTO_RULE) is True


def test_whitelist_dominant_both_fields_kept():
    """(d) 兩名單都給、且都命中 → kept：exclude_any 在 require_any 存在時不生效。"""
    # "毒駕撞死人" 同時命中 require(撞) 與 exclude(毒駕)；whitelist 主導 → kept。
    assert is_topic_relevant({"title": "毒駕撞死人"}, BOTH_RULE) is True


def test_exclude_only_hit_excluded():
    """(e) 純黑名單支：只給 exclude_any，命中 → excluded。"""
    assert is_topic_relevant({"title": "新車促銷廣告出爐"}, BLACKLIST_RULE) is False


def test_exclude_only_no_hit_kept():
    """(e) 純黑名單支：只給 exclude_any，未命中 → kept。"""
    assert is_topic_relevant({"title": "機車事故釀2傷"}, BLACKLIST_RULE) is True


def test_fail_open_empty_and_malformed_rule():
    """(f) 空/畸形規則 → 不套閘（kept），且不得爆炸。"""
    assert is_topic_relevant({"title": "任意標題"}, {}) is True          # 空 dict
    assert is_topic_relevant({"title": "任意標題"}, None) is True        # 缺規則
    assert is_topic_relevant({"title": "任意標題"}, ["not", "dict"]) is True  # 非 dict，不爆炸


# ── partition_by_relevance (pure partition) ───────────────────────────────────

def test_partition_splits_on_and_off():
    """kept（含邊界）進 on_topic、離題進 off_topic，各自保留輸入順序，每篇附非空 _relevance_reason。"""
    rules = {"機車事故": MOTO_RULE}
    arts = [
        {"title": "機車自撞1死2傷", "major_category": "機車事故"},      # kept
        {"title": "駕駛肇事逃逸被起訴", "major_category": "機車事故"},  # 邊界 → kept
        {"title": "男子涉竊機車遭通緝", "major_category": "機車事故"},  # off
        {"title": "毒駕羈押獲交保", "major_category": "機車事故"},      # off
    ]
    on, off = partition_by_relevance(arts, rules)
    assert [a["title"] for a in on] == ["機車自撞1死2傷", "駕駛肇事逃逸被起訴"]
    assert [a["title"] for a in off] == ["男子涉竊機車遭通緝", "毒駕羈押獲交保"]
    for a in arts:
        assert a.get("_relevance_reason")  # present & non-empty


def test_partition_no_rule_category_kept():
    """(f) 該類別無規則 → 不套閘、kept、reason 'no-rule'。"""
    rules = {"機車事故": MOTO_RULE}
    arts = [{"title": "某政策評論投書", "major_category": "道安政策"}]
    on, off = partition_by_relevance(arts, rules)
    assert len(on) == 1 and off == []
    assert on[0]["_relevance_reason"] == "no-rule"


def test_partition_purity_preserves_major_category():
    """(g) 純函數：不改 major_category、不動其他欄位、原地標註（唯一新增 _relevance_reason）。"""
    rules = {"機車事故": MOTO_RULE}
    art = {"title": "男子涉竊機車遭通緝", "major_category": "機車事故", "quality_score": 0.9}
    on, off = partition_by_relevance([art], rules)
    assert off and off[0] is art               # 同一 dict，未複製
    assert art["major_category"] == "機車事故"  # 類別未被改動
    assert art["quality_score"] == 0.9          # 其他欄位不動
    assert "_relevance_reason" in art           # 唯一新增欄位


def test_partition_high_score_offtopic_still_excluded():
    """(h) C2：高品質分數但離題（毒駕羈押、無事故 token）仍落 off_topic — 相關性先於任何分數。"""
    rules = {"機車事故": MOTO_RULE}
    art = {"title": "毒駕羈押", "major_category": "機車事故", "quality_score": 0.99}
    on, off = partition_by_relevance([art], rules)
    assert on == []
    assert len(off) == 1 and off[0]["title"] == "毒駕羈押"
