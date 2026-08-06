"""
scripts/traffic_weekly_analysis.py
Monday weekly runner: cluster buffered traffic articles, score topics, generate
Gemini deep-analysis for top hot topics, persist to hot_topic_reports, publish.
"""
import logging
import sys
import os
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("traffic_weekly_analysis")

_TW_TZ = timezone(timedelta(hours=8))
_GEMINI_DELAY = 2.5


def _week_start_date() -> str:
    """Return the ISO date (YYYY-MM-DD) of this week's Monday in Taiwan time."""
    now = datetime.now(_TW_TZ)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def main():
    from src.pipeline_config import load_pipeline_config, load_relevance_rules
    from src.filter import partition_by_relevance
    from src.storage import (
        expire_buffer_articles, get_traffic_buffer, upsert_hot_topic_report,
        get_recent_hot_topic_reports, mark_articles_analyzed,
    )
    from src.analyzer import (
        cluster_traffic_articles, score_topic_buckets, analyze_hot_topic,
        select_hot_topics_with_novelty, topic_token_signature,
        select_digest_pool, analyze_category_digest,
    )
    from src.publisher import publish_hot_topic_reports

    logger.info("=== 週交通熱點分析開始 ===")

    # 1. Load config
    config = load_pipeline_config()
    max_age_weeks = config.get("buffer", {}).get("max_age_weeks", 8)
    week_start = _week_start_date()
    logger.info("分析週次開始日：%s", week_start)

    # 2. Expire old buffer articles
    expired = expire_buffer_articles()
    logger.info("已清理過期 buffer：%d 筆", expired)

    # 3. Fetch buffer
    articles = get_traffic_buffer(max_age_weeks)
    logger.info("buffer 中有 %d 篇待分析文章", len(articles))

    # FR-020: minimum 3 articles required（以原始 buffer 計，維持既有語意，不受相關性閘影響）
    if len(articles) < 3:
        logger.info("buffer 文章不足 3 篇，本週跳過熱點分析（目前 %d 篇）", len(articles))
        return

    # 3b. 相關性選材閘（feature 012）：clustering 前把「含類別關鍵字但主題離題」的文章
    #     （刑案／車媒行銷）排除，使其不會被發布為事故熱點。per-category whitelist-dominant：
    #     目前只有 機車事故 有規則，無規則的類別（道安政策…digest 路徑）fail-open 全通過、不受影響。
    #     off-topic 文章不進 bucket 也不進 digest 池 → 不會被 mark_articles_analyzed → 留在 buffer，
    #     僅排除於「本週報告」（可逆、可稽核）。
    relevance_rules = load_relevance_rules()
    if relevance_rules:
        on_topic, off_topic = partition_by_relevance(articles, relevance_rules)
        if off_topic:
            logger.info("相關性閘：%d 篇通過、%d 篇離題排除於選材（仍留 buffer）",
                        len(on_topic), len(off_topic))
            for a in off_topic:
                logger.info("  [off-topic] %s｜%s｜%s",
                            (a.get("title") or "")[:50], a.get("major_category", ""),
                            a.get("_relevance_reason", ""))
        articles = on_topic

    # 4. Cluster
    buckets = cluster_traffic_articles(articles, config)
    logger.info("分群結果：%d 個 bucket", len(buckets))

    # 5. Score
    bucket_scores = score_topic_buckets(buckets, config)
    for bid, score in sorted(bucket_scores.items(), key=lambda x: x[1], reverse=True):
        logger.info("  %s: score=%.3f (%d 篇)", bid, score, len(buckets[bid]))

    # 6. Select hot topics with novelty gate (gate-then-cap).
    #    Fetch prior reports for comparison; fail-open (treat all as novel) on read error.
    try:
        prior_reports = get_recent_hot_topic_reports(max_age_weeks, exclude_week=week_start)
    except Exception as e:
        logger.warning("讀取 prior reports 失敗，novelty 退化為全部視為新：%s", e)
        prior_reports = []
    hot_topic_ids = select_hot_topics_with_novelty(buckets, bucket_scores, prior_reports, config)
    logger.info("本週熱點 topic（通過 novelty gate）：%s", hot_topic_ids)

    # 6b. Category digest（feature 010）：量觸發＋消耗。
    #     排除名單以「未扣席次前」的 gate 入選為準——決定性、單一 pass，
    #     被 digest 擠掉的尾名 bucket 文章留在 buffer（未標 analyzed）下週再競爭。
    digest_cfgs = config.get("category_digest") or {}
    max_hot_topics = int(config.get("topic_scoring", {}).get("max_hot_topics", 3))
    excluded_links = {
        a.get("link")
        for bid in hot_topic_ids
        for a in buckets.get(bid, [])
        if a.get("link")
    }
    triggered_digests = []
    for cat in sorted(digest_cfgs):
        dcfg = digest_cfgs[cat]
        selected, pool_all, effective = select_digest_pool(articles, cat, dcfg, excluded_links)
        trigger_count = int(dcfg.get("trigger_count", 10))
        is_trigger = effective >= trigger_count and selected
        logger.info(
            "digest[%s] pool=%d effective=%d threshold=%d → %s",
            cat, len(pool_all), effective, trigger_count,
            "TRIGGER" if is_trigger else "accumulate",
        )
        if is_trigger:
            triggered_digests.append((cat, selected, pool_all, effective))
    # 同週多 digest 超額：依有效篇數降冪取足；落選 digest 不消耗、留待下週
    triggered_digests.sort(key=lambda t: t[3], reverse=True)
    triggered_digests = triggered_digests[:max_hot_topics]
    # digest 先佔席次，一般 bucket 取剩餘（FR-007：反餓死，不與 bucket 比分數）
    hot_topic_ids = hot_topic_ids[:max_hot_topics - len(triggered_digests)]

    if not hot_topic_ids and not triggered_digests:
        logger.info("無 bucket 達到 min_threshold，跳過本週熱點發布")
        return

    # 7. Analyze and persist each hot topic
    published_reports = []
    for bid in hot_topic_ids:
        bucket_articles = buckets[bid]
        # Topic label = "<major_category> · <top representative term>" so distinct
        # buckets within a category don't collide on the (week, topic_label) key.
        major_category = bucket_articles[0].get("major_category", bid) if bucket_articles else bid
        signature = topic_token_signature(bucket_articles)
        topic_label = f"{major_category} · {signature[0]}" if signature else major_category

        logger.info("正在分析熱點：%s (%d 篇文章)", topic_label, len(bucket_articles))
        try:
            report_text, source_links = analyze_hot_topic(bucket_articles, topic_label, week_start)
        except Exception as e:
            logger.error("Gemini 分析失敗，跳過 %s：%s", topic_label, e)
            continue

        if not report_text:
            logger.warning("熱點 %s 分析結果為空，跳過", topic_label)
            continue
        distinct_sources = len({a.get("source", "") for a in bucket_articles})
        day_set = {(a.get("published") or "")[:10] for a in bucket_articles if a.get("published")}
        distinct_days = len(day_set)
        latest_source_date = max(day_set) if day_set else None

        report = {
            "week_start_date": week_start,
            "topic_label": topic_label,
            "report_text": report_text,
            "source_article_count": len(bucket_articles),
            "source_article_links": source_links,
            "cumulative_score": bucket_scores[bid],
            "distinct_sources": distinct_sources,
            "distinct_days": distinct_days,
            "topic_token_signature": signature,
            "latest_source_date": latest_source_date,
        }

        try:
            upsert_hot_topic_report(report)
            published_reports.append(report)
        except Exception as e:
            logger.error("持久化 hot_topic_report 失敗，跳過：%s", e)
            continue

        # Respect Gemini rate limits between calls
        if bid != hot_topic_ids[-1]:
            time.sleep(_GEMINI_DELAY)

    # 7b. Digest 發布（feature 010）：多事件彙整，失敗即跳過該類（池不消耗）
    for idx, (cat, selected, pool_all, _effective) in enumerate(triggered_digests):
        # Respect Gemini rate limits across regular + digest calls
        if hot_topic_ids or idx > 0:
            time.sleep(_GEMINI_DELAY)
        dcfg = digest_cfgs[cat]
        topic_label = f"{cat} · 彙整"
        logger.info("正在彙整：%s（選材 %d 篇／池 %d 篇）", topic_label, len(selected), len(pool_all))
        try:
            report_text, source_links = analyze_category_digest(
                selected, topic_label, week_start, int(dcfg.get("max_articles", 15)),
            )
        except Exception as e:
            logger.error("Gemini 彙整失敗，跳過 %s（池不消耗）：%s", topic_label, e)
            continue
        if not report_text:
            logger.warning("彙整 %s 分析結果為空，跳過（池不消耗）", topic_label)
            continue

        day_set = {(a.get("published") or "")[:10] for a in selected if a.get("published")}
        report = {
            "week_start_date": week_start,
            "topic_label": topic_label,
            "report_text": report_text,
            "source_article_count": len(selected),
            "source_article_links": source_links,
            "cumulative_score": sum(float(a.get("initial_quality_score") or 0) for a in selected),
            "distinct_sources": len({a.get("source", "") for a in selected}),
            "distinct_days": len(day_set),
            # 空簽章：digest 永不成為 novelty prior basis（010 research D2）
            "topic_token_signature": [],
            "latest_source_date": max(day_set) if day_set else None,
        }
        try:
            upsert_hot_topic_report(report)
            published_reports.append(report)
        except Exception as e:
            logger.error("持久化 digest 失敗，跳過 %s（池不消耗）：%s", topic_label, e)
            continue

        # 消耗：upsert 已標記選材 links，這裡補標池內殘餘（含低品質文），池歸零。
        # mark 失敗時 helper 記 ERROR 回 0——殘餘下週重入池，同鍵 upsert 冪等。
        selected_links = {a.get("link") for a in selected if a.get("link")}
        residual = [
            a.get("link") for a in pool_all
            if a.get("link") and a.get("link") not in selected_links
        ]
        marked = mark_articles_analyzed(residual)
        logger.info("digest[%s] consumed=%d", cat, len(selected_links) + marked)

    # 8. Publish
    if published_reports:
        try:
            publish_hot_topic_reports(published_reports)
        except Exception as e:
            logger.error("publish_hot_topic_reports 失敗：%s", e)

    logger.info("=== 週交通熱點分析完成，共發布 %d 個熱點 ===", len(published_reports))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("traffic_weekly_analysis.py 執行失敗")
        sys.exit(1)
