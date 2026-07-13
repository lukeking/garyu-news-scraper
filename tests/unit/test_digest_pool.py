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
