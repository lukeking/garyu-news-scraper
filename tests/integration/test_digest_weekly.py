"""
Integration tests for the category-digest path in scripts/traffic_weekly_analysis.py
— US1/US2/US3 + SC-004 (010). All I/O is mocked at the src.* seams; main() runs for
real so the actual wiring (trigger stats, seat allocation, consumption order, logs)
is what gets exercised.
"""
import importlib.util
import logging
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_SPEC = importlib.util.spec_from_file_location(
    "traffic_weekly_analysis_under_test",
    os.path.join(_ROOT, "scripts", "traffic_weekly_analysis.py"),
)
weekly = importlib.util.module_from_spec(_SPEC)
# The script's module level calls load_dotenv() — that would inject real
# credentials into the whole pytest process and un-skip the credential-gated
# live tests. Neutralise it before exec: this suite must stay offline.
import dotenv  # noqa: E402

with patch.object(dotenv, "load_dotenv", lambda *a, **k: False):
    _SPEC.loader.exec_module(weekly)


def _config(digest=None, max_hot_topics=3):
    return {
        "jaccard": {"merge_threshold": 0.45, "cluster_lower": 0.20},
        "topic_scoring": {
            "min_threshold": 1.5, "max_hot_topics": max_hot_topics,
            "novelty_growth_pct": 0.5, "category_min_threshold": {"道安政策": 1.0},
        },
        "topic_identity": {"similarity_threshold": 0.3},
        "buffer": {"max_age_weeks": 8},
        "category_digest": digest if digest is not None else {},
    }


# Deterministic tokens (no jieba): policy titles never overlap (all singletons);
# each moto bucket k holds two articles sharing only its own "motok" token.
def _tokens(title):
    if title.startswith("p"):
        return frozenset({f"{title}x", f"{title}y"})
    if title.startswith("m"):
        bucket, variant = title.split("_")
        return frozenset({bucket, f"{bucket}{variant}"})
    return frozenset()


def _policy(idx, q=0.3, pub="2026-07-06"):
    return {
        "link": f"https://p/{idx}", "title": f"p{idx}", "major_category": "道安政策",
        "initial_quality_score": q, "source": f"政{idx}",
        "published": f"{pub}T00:00:00", "summary": "x",
    }


def _moto(bucket, variant, q):
    day = "2026-07-01" if variant == "a" else "2026-07-02"
    return {
        "link": f"https://m/{bucket}{variant}", "title": f"m{bucket}_{variant}",
        "major_category": "機車事故", "initial_quality_score": q,
        "source": f"車{bucket}{variant}", "published": f"{day}T00:00:00", "summary": "x",
    }


def _moto_buckets():
    """Three qualifying 機車事故 buckets, scores descending: m1 > m2 > m3 (all ≥ 1.5)."""
    return [
        _moto(1, "a", 0.9), _moto(1, "b", 0.9),
        _moto(2, "a", 0.8), _moto(2, "b", 0.8),
        _moto(3, "a", 0.7), _moto(3, "b", 0.7),
    ]


def _digest_stub(pool, label, week_start, max_articles):
    return "彙整內文", [
        {"title": a["title"], "link": a["link"], "summary": ""} for a in pool
    ]


def _run(config, articles, digest_stub=_digest_stub, mark_returns_len=True,
         upsert_raises=None):
    """Run weekly.main() with all I/O mocked; return recorded calls."""
    upserts, marks, published = [], [], []

    def _upsert(report):
        if upsert_raises is not None:
            raise upsert_raises
        upserts.append(report)

    def _mark(links):
        marks.append(list(links))
        return len(links) if mark_returns_len else 0

    with patch("src.pipeline_config.load_pipeline_config", return_value=config), \
         patch("src.storage.expire_buffer_articles", return_value=0), \
         patch("src.storage.get_traffic_buffer", return_value=articles), \
         patch("src.storage.get_recent_hot_topic_reports", return_value=[]), \
         patch("src.storage.upsert_hot_topic_report", side_effect=_upsert), \
         patch("src.storage.mark_articles_analyzed", side_effect=_mark, create=True), \
         patch("src.analyzer.analyze_hot_topic",
               side_effect=lambda arts, label, ws: ("熱點內文", [
                   {"title": a["title"], "link": a["link"], "summary": ""} for a in arts
               ])), \
         patch("src.analyzer.analyze_category_digest", side_effect=digest_stub, create=True), \
         patch("src.publisher.publish_hot_topic_reports", side_effect=published.append), \
         patch.object(weekly.time, "sleep"), \
         patch("src.filter.normalise_title", side_effect=_tokens):
        weekly.main()
    return upserts, marks, published


# ── US1 (a): trigger → digest published, regular buckets take remaining seats ──

def test_trigger_publishes_digest_and_reserves_seat(caplog):
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(12)] + _moto_buckets()

    with caplog.at_level(logging.INFO):
        upserts, _, _ = _run(_config(digest_cfg), articles)

    labels = [r["topic_label"] for r in upserts]
    assert "道安政策 · 彙整" in labels
    # digest takes one seat: only the top-2 moto buckets publish, m3 is squeezed out
    assert "機車事故 · m1" in labels and "機車事故 · m2" in labels
    assert len(labels) == 3 and "機車事故 · m3" not in labels

    digest = next(r for r in upserts if r["topic_label"] == "道安政策 · 彙整")
    assert digest["topic_token_signature"] == []
    assert abs(digest["cumulative_score"] - 12 * 0.3) < 1e-9
    assert digest["latest_source_date"] == "2026-07-06"
    assert digest["source_article_count"] == 12
    assert f"digest[道安政策] pool=12 effective=12 threshold=10" in caplog.text
    assert "→ TRIGGER" in caplog.text


# ── US1 (b): below threshold → accumulate log, zero behaviour change ──────────

def test_below_threshold_accumulates_with_log(caplog):
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(5)] + _moto_buckets()

    with caplog.at_level(logging.INFO):
        upserts, marks, _ = _run(_config(digest_cfg), articles)

    labels = [r["topic_label"] for r in upserts]
    assert labels == ["機車事故 · m1", "機車事故 · m2", "機車事故 · m3"]
    assert marks == []  # nothing consumed
    assert "digest[道安政策] pool=5 effective=5 threshold=10 → accumulate" in caplog.text


# ── US2: consume-on-success, zero overlap, failure semantics ──────────────────

def test_consume_marks_residual_and_logs(caplog):
    """成功發布後：殘餘（垃圾文）被 mark，consumed = 選材＋殘餘。"""
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(12)] + \
               [_policy(100 + i, q=0.05) for i in range(3)]  # 垃圾文（低於 floor）

    with caplog.at_level(logging.INFO):
        upserts, marks, _ = _run(_config(digest_cfg), articles)

    assert [r["topic_label"] for r in upserts] == ["道安政策 · 彙整"]
    # 殘餘 = 3 篇垃圾文的 links（選材 12 篇由既有 upsert 路徑標記）
    assert len(marks) == 1
    assert sorted(marks[0]) == sorted(f"https://p/{100 + i}" for i in range(3))
    assert "digest[道安政策] consumed=15" in caplog.text


def test_two_runs_zero_overlap_and_empty_pool_accumulates(caplog):
    """第二跑（池已消耗、新批文章）→ 新 digest 與第一跑零交集；池空跑 → accumulate。"""
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}

    run1_arts = [_policy(i) for i in range(12)]
    upserts1, _, _ = _run(_config(digest_cfg), run1_arts)

    run2_arts = [_policy(200 + i) for i in range(10)]  # 消耗後的新累積批
    upserts2, _, _ = _run(_config(digest_cfg), run2_arts)

    links1 = {a["link"] for a in upserts1[0]["source_article_links"]}
    links2 = {a["link"] for a in upserts2[0]["source_article_links"]}
    assert links1 and links2 and not (links1 & links2)  # SC-002

    # 池空（僅剩非政策文避開 <3 早退）→ accumulate、無 digest
    with caplog.at_level(logging.INFO):
        upserts3, marks3, _ = _run(_config(digest_cfg), _moto_buckets())
    assert "道安政策 · 彙整" not in [r["topic_label"] for r in upserts3]
    assert marks3 == []
    assert "digest[道安政策] pool=0 effective=0 threshold=10 → accumulate" in caplog.text


def test_gemini_empty_skips_without_consume(caplog):
    """Gemini 回空 → 不 upsert、不消耗（池下週重試）。"""
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(12)]

    with caplog.at_level(logging.INFO):
        upserts, marks, _ = _run(
            _config(digest_cfg), articles,
            digest_stub=lambda pool, label, ws, k: ("", []),
        )
    assert upserts == [] and marks == []
    assert "池不消耗" in caplog.text


def test_upsert_failure_skips_consume():
    """持久化 raise → 不消耗，run 正常結束不炸。"""
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(12)]

    upserts, marks, _ = _run(_config(digest_cfg), articles,
                             upsert_raises=RuntimeError("db down"))
    assert upserts == [] and marks == []


def test_mark_failure_rerun_same_conflict_key():
    """殘餘標記失敗 → 重跑（池未清）再觸發，同 (week, label) 鍵 → upsert 冪等。"""
    digest_cfg = {"道安政策": {"trigger_count": 10, "quality_floor": 0.18, "max_articles": 15}}
    articles = [_policy(i) for i in range(12)] + [_policy(100, q=0.05)]

    upserts1, _, _ = _run(_config(digest_cfg), articles, mark_returns_len=False)
    upserts2, _, _ = _run(_config(digest_cfg), articles, mark_returns_len=False)

    key1 = (upserts1[0]["week_start_date"], upserts1[0]["topic_label"])
    key2 = (upserts2[0]["week_start_date"], upserts2[0]["topic_label"])
    assert key1 == key2  # 同 conflict key → DB 端 on_conflict 冪等，不產生第二筆
