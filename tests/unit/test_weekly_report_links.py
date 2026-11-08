"""018 T043：週報 main() 存進資料庫的 source_article_links，跟報告與 prompt 裡的 [i] 一一對得上。
真的 analyze_hot_topic／analyze_category_digest 跑過 main()；只換掉 _call_gemini 與 src.* 的 I/O。"""
import importlib.util
import os
import re
import sys
from unittest.mock import patch

import dotenv

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _ROOT)

import src.analyzer as analyzer  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "weekly_links_under_test", os.path.join(_ROOT, "scripts", "traffic_weekly_analysis.py"))
weekly = importlib.util.module_from_spec(_SPEC)
# 模組層會 load_dotenv()；先擋掉，免得真的憑證進到整個 pytest 行程
with patch.object(dotenv, "load_dotenv", lambda *a, **k: False):
    _SPEC.loader.exec_module(weekly)

CONFIG = {
    "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
    "topic_scoring": {"min_threshold": 1.5, "max_hot_topics": 3, "novelty_growth_pct": 0.5,
                      "category_min_threshold": {"道安政策": 1.0}},
    "topic_identity": {"similarity_threshold": 0.3},
    "buffer": {"max_age_weeks": 8},
    "category_digest": {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}},
}


def tokens(title):
    if title.startswith("p"):
        return frozenset({f"{title}x", f"{title}y"})
    bucket, variant = title.split("_")
    return frozenset({bucket, f"{bucket}{variant}"})


def policy(i):
    summary = "" if i % 2 else f"交通部說明第{i}項新制，明年一月起分階段上路，各縣市配合宣導。"
    return {"link": f"https://p/{i}", "title": f"p{i}", "major_category": "道安政策", "initial_quality_score": 0.3,
            "source": f"政{i}", "published": "2026-07-06T00:00:00", "summary": summary}


def moto(variant, q, summary, day):
    return {"link": f"https://m/1{variant}", "title": f"m1_{variant}", "major_category": "機車事故",
            "initial_quality_score": q, "source": f"車{variant}", "published": f"{day}T00:00:00", "summary": summary}


ARTICLES = [policy(i) for i in range(12)] + [
    moto("a", 0.7, "機車行經路口與轎車碰撞，騎士送醫。", "2026-07-01"),
    moto("b", 0.9, "", "2026-07-02"),
]
LISTED_ID = re.compile(r"^\[(\d+)\] (?:報導日：[^\n]*\n\s*)?標題：(.*)$", re.M)
TAIL_ID = re.compile(r"^- (.*) \[(\d+)\]$", re.M)


def run_weekly():
    upserts, calls = [], []

    def gemini(prompt, api_key, **kw):
        calls.append((kw.get("system_prompt"), prompt))
        return "### 本期概覽\n本週重點。"

    with patch("src.pipeline_config.load_pipeline_config", return_value=CONFIG), \
         patch("src.pipeline_config.load_relevance_rules", return_value={}), \
         patch("src.storage.expire_buffer_articles", return_value=0), \
         patch("src.storage.get_traffic_buffer", return_value=ARTICLES), \
         patch("src.storage.get_recent_hot_topic_reports", return_value=[]), \
         patch("src.storage.upsert_hot_topic_report", side_effect=upserts.append), \
         patch("src.storage.mark_articles_analyzed", side_effect=lambda links: len(links), create=True), \
         patch("src.publisher.publish_hot_topic_reports"), \
         patch.object(analyzer, "_get_api_key", lambda: "test-key"), \
         patch.object(analyzer, "_call_gemini", side_effect=gemini), \
         patch.object(weekly.time, "sleep"), \
         patch("src.filter.normalise_title", side_effect=tokens):
        weekly.main()
    reports = {r["topic_label"]: r for r in upserts}
    prompts = {system: prompt for system, prompt in calls}
    return reports, prompts


def stored_titles(report):
    return [link["title"] for link in report["source_article_links"]]


def test_hot_report_links_follow_the_prompt_ids():
    reports, prompts = run_weekly()
    hot = next(r for label, r in reports.items() if label.startswith("機車事故"))
    ids = {int(i): title for i, title in LISTED_ID.findall(prompts[analyzer.HOT_TOPIC_SYSTEM_PROMPT])}
    assert sorted(ids) == list(range(1, len(hot["source_article_links"]) + 1))
    assert stored_titles(hot) == [ids[i] for i in sorted(ids)]
    assert stored_titles(hot) == ["m1_b", "m1_a"]  # 分數順序，不是 buffer 的順序


def test_digest_report_links_follow_the_prompt_and_title_only_ids():
    reports, prompts = run_weekly()
    digest = reports["道安政策 · 彙整"]
    ids = {int(i): title for i, title in LISTED_ID.findall(prompts[analyzer.DIGEST_SYSTEM_PROMPT])}
    tail = {int(i): title for title, i in TAIL_ID.findall(digest["report_text"])}
    assert ids and tail and not set(ids) & set(tail)
    every = {**ids, **tail}
    assert sorted(every) == list(range(1, len(digest["source_article_links"]) + 1))
    assert stored_titles(digest) == [every[i] for i in sorted(every)]
    assert f"本期收錄 {len(digest['source_article_links'])} 篇報導" in digest["report_text"]
    # 有摘要的在前、只有標題的在後，跟 buffer 裡交錯的順序不同
    assert stored_titles(digest) != [a["title"] for a in ARTICLES if a["title"] in every.values()]
