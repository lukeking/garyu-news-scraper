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


# ── US2 (T007): whole-bucket FR-003 + source-independence FR-007 ───────────────

from src.analyzer import cluster_traffic_articles  # noqa: E402

_CLUSTER_CONFIG = {"jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20}}


def test_whole_bucket_all_offtopic_yields_no_bucket():
    """(T007a / FR-003) 某類別候選全數離題 → on_topic 無該類別 → 不成桶、不發布。
    金線式整席行銷（油耗/市佔/銷量，無事故 token）錨定。"""
    rules = {"機車事故": MOTO_RULE}
    arts = [
        {"title": "新機車油耗排名出爐", "major_category": "機車事故", "source": "地球黃金線"},
        {"title": "電動機車市佔率再創新高", "major_category": "機車事故", "source": "地球黃金線"},
        {"title": "機車銷量戰報 掛牌數第一", "major_category": "機車事故", "source": "地球黃金線"},
    ]
    on, off = partition_by_relevance(arts, rules)
    assert on == [] and len(off) == 3
    buckets = cluster_traffic_articles(on, _CLUSTER_CONFIG)
    assert all(
        a.get("major_category") != "機車事故"
        for arts_ in buckets.values() for a in arts_
    )  # 該類別無桶


def test_car_media_real_accident_survives_source_ignored():
    """(T007b / FR-007) 來源是車媒但確為真事故（含事故 token）→ 保留：閘只看內容不看來源。
    對照組：同一車媒的行銷稿（無事故 token）→ 離題。"""
    rules = {"機車事故": MOTO_RULE}
    real = {"title": "機車追撞休旅車 騎士2傷送醫", "major_category": "機車事故", "source": "地球黃金線"}
    mktg = {"title": "新車油耗市佔戰報", "major_category": "機車事故", "source": "地球黃金線"}
    assert is_topic_relevant(real, MOTO_RULE) is True   # 車媒的真事故不被連坐
    assert is_topic_relevant(mktg, MOTO_RULE) is False  # 同源行銷稿仍離題
    on, off = partition_by_relevance([real, mktg], rules)
    assert [a["title"] for a in on] == ["機車追撞休旅車 騎士2傷送醫"]
    assert [a["title"] for a in off] == ["新車油耗市佔戰報"]
