"""`scripts/measure_relevance.py` 的契約——在此之前這個檔零測試。跑真正的函式並用真的
partition_by_relevance / score_topic_buckets，只把資料當邊界。不碰 DB、不呼叫模型。
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))

import measure_relevance as mr  # noqa: E402

CATEGORY = "機車事故"
RULES = {CATEGORY: {"require_any": ["撞"]}}
STRICTER = {CATEGORY: {"require_any": ["自撞"]}}


def _article(link, title, source, day, quality=1.0):
    return {
        "link": link, "title": title, "source": source,
        "published": f"2026-08-{day:02d}T09:00:00Z",
        "major_category": CATEGORY, "initial_quality_score": quality,
    }


# 2 篇命中「撞」、2 篇沒有。四個來源、兩天——套閘後只剩 2 篇 2 來源 1 天，分數必然掉。
POOL = [
    _article("l1", "機車自撞1死2傷", "A", 3),
    _article("l2", "騎士遭撞送醫不治", "B", 3),
    _article("l3", "男子涉竊機車遭通緝", "C", 4),
    _article("l4", "毒駕羈押獲交保", "D", 4),
]
BY_LINK = {a["link"]: a for a in POOL}


def _report(links, bucket_size, label=f"{CATEGORY} · 中時"):
    return {
        "week_start_date": "2026-08-03", "topic_label": label,
        "source_article_count": bucket_size, "cumulative_score": 7.07,
        "source_article_links": list(links),
    }


def _config(threshold):
    return {"topic_scoring": {"min_threshold": threshold}}


def test_exact_means_the_whole_bucket_is_in_front_of_us():
    """`exact` 是兩個條件的合取，兩邊各自都會讓它變 False。"""
    whole = _report(["l1", "l2", "l3", "l4"], bucket_size=4)
    capped = _report(["l1", "l2", "l3", "l4"], bucket_size=28)
    pruned = _report(["l1", "l2", "l3", "l9"], bucket_size=4)

    got = {s["label"]: s for s in mr.gated_slates([whole], BY_LINK, RULES)}
    assert got[whole["topic_label"]]["exact"] is True

    # 桶比名單大：被擠掉的文章會遞補進空出來的位置，而我們看不到它們
    assert mr.gated_slates([capped], BY_LINK, RULES)[0]["exact"] is False

    # 有列被清掉：那個洞會被靜靜當成一個比較小的桶
    got_pruned = mr.gated_slates([pruned], BY_LINK, RULES)[0]
    assert got_pruned["exact"] is False
    assert got_pruned["unresolved"] == 1

    # 沒有規則的類別完全不套閘（fail-open），所以連記錄都不該產生
    assert mr.gated_slates([_report(["l1"], 1, label="道安政策 · 彙整")], BY_LINK, RULES) == []


def test_gate_can_starve_a_bucket_under_min_threshold():
    """閘只會移除，所以原本勉強過線的桶可能掉下去——連同它的 on-topic 文章一起死。"""
    slates = mr.gated_slates([_report(["l1", "l2", "l3", "l4"], 4)], BY_LINK, RULES)
    before = 4.0 * math.log(5) * math.log(3)
    after = 2.0 * math.log(3) * math.log(2)
    assert before > 2.0 > after, "前提：門檻要落在套閘前後之間，這個測試才有意義"

    dead = mr.replay(slates, RULES, _config(2.0))[0]
    assert dead["survives"] is False
    assert dead["after"] == [], "死掉的桶不發布，on-topic 也一起損失"
    assert dead["before_score"] == pytest.approx(before), "套閘前的分數要重算得出來"

    alive = mr.replay(mr.gated_slates([_report(["l1", "l2", "l3", "l4"], 4)], BY_LINK, RULES),
                      RULES, _config(1.0))[0]
    assert alive["survives"] is True
    assert [a["link"] for a in alive["after"]] == ["l1", "l2"]


def test_non_exact_slate_is_unjudged_not_dead():
    """桶比名單大時算出來的分數會嚴重低估，那會憑空生出一個「不發布」的判決。"""
    slates = mr.gated_slates([_report(["l1", "l2", "l3", "l4"], 28)], BY_LINK, RULES)
    got = mr.replay(slates, RULES, _config(2.0))[0]

    assert got["survives"] is None, "不可判定，不是判定為死"
    assert got["after_score"] is None
    assert got["borderline"] is False


def test_replay_is_re_runnable_so_the_counterfactual_is_real():
    """反事實必須被建構：換一組規則重跑要真的重建世界，不能留上一輪的殘留。"""
    slates = mr.gated_slates([_report(["l1", "l2", "l3", "l4"], 4)], BY_LINK, RULES)
    keys = ("gate_kept", "gate_dropped", "after_score", "survives", "borderline", "after")

    mr.replay(slates, RULES, _config(1.0))
    first = {k: repr(slates[0][k]) for k in keys}

    mr.replay(slates, STRICTER, _config(1.0))
    strict = {k: repr(slates[0][k]) for k in keys}
    assert strict != first, "前提：這組規則要真的改變結果"
    assert [a["link"] for a in slates[0]["gate_kept"]] == ["l1"], "只剩「自撞」那篇"

    mr.replay(slates, RULES, _config(1.0))
    assert {k: repr(slates[0][k]) for k in keys} == first, "回到原規則要逐鍵還原，不能有殘留"
