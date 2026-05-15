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
    from src.pipeline_config import load_pipeline_config
    from src.storage import expire_buffer_articles, get_traffic_buffer, upsert_hot_topic_report
    from src.analyzer import cluster_traffic_articles, score_topic_buckets, select_hot_topics, analyze_hot_topic
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

    # FR-020: minimum 3 articles required
    if len(articles) < 3:
        logger.info("buffer 文章不足 3 篇，本週跳過熱點分析（目前 %d 篇）", len(articles))
        return

    # 4. Cluster
    buckets = cluster_traffic_articles(articles, config)
    logger.info("分群結果：%d 個 bucket", len(buckets))

    # 5. Score
    bucket_scores = score_topic_buckets(buckets, config)
    for bid, score in sorted(bucket_scores.items(), key=lambda x: x[1], reverse=True):
        logger.info("  %s: score=%.3f (%d 篇)", bid, score, len(buckets[bid]))

    # 6. Select hot topics
    hot_topic_ids = select_hot_topics(bucket_scores, config)
    logger.info("本週熱點 topic：%s", hot_topic_ids)

    if not hot_topic_ids:
        logger.info("無 bucket 達到 min_threshold，跳過本週熱點發布")
        return

    # 7. Analyze and persist each hot topic
    published_reports = []
    for bid in hot_topic_ids:
        bucket_articles = buckets[bid]
        # Use the major_category of the first article as topic label, or bucket_id as fallback
        topic_label = bucket_articles[0].get("major_category", bid) if bucket_articles else bid

        logger.info("正在分析熱點：%s (%d 篇文章)", topic_label, len(bucket_articles))
        try:
            report_text = analyze_hot_topic(bucket_articles, topic_label, week_start)
        except Exception as e:
            logger.error("Gemini 分析失敗，跳過 %s：%s", topic_label, e)
            continue

        if not report_text:
            logger.warning("熱點 %s 分析結果為空，跳過", topic_label)
            continue

        source_links = [a.get("link", "") for a in bucket_articles if a.get("link")]
        distinct_sources = len({a.get("source", "") for a in bucket_articles})
        distinct_days = len({(a.get("published") or "")[:10] for a in bucket_articles if a.get("published")})

        report = {
            "week_start_date": week_start,
            "topic_label": topic_label,
            "report_text": report_text,
            "source_article_count": len(bucket_articles),
            "source_article_links": source_links,
            "cumulative_score": bucket_scores[bid],
            "distinct_sources": distinct_sources,
            "distinct_days": distinct_days,
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
