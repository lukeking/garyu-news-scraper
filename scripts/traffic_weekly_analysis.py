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
# 不發布（spec 020）：main.py 寫的這次收集清單、這支寫的兩個產物、不產生的站台檔
_COLLECTED_FILE = "collected.json"
_SELECTION_FILE = "selection.json"
_REPORTS_FILE = "traffic_reports.json"
_HOT_TOPICS_FILE = "pages/traffic/hot_topics.json"
_BRIEF_FIELDS = ("title", "link", "source", "published", "major_category", "initial_quality_score", "summary")
_NULLS_FIRST = datetime.max.replace(tzinfo=timezone.utc)


def _week_start_date() -> str:
    """Return the ISO date (YYYY-MM-DD) of this week's Monday in Taiwan time."""
    now = datetime.now(_TW_TZ)
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")


def main():
    from src import run_mode
    from src.analyzer import get_call_counts

    # 模式先驗：不認得的值在讀任何東西之前就丟錯
    mode = run_mode.current()
    if mode != run_mode.FORMAL:
        logger.info(run_mode.start_line())
    start = get_call_counts()
    try:
        _run(mode)
    finally:
        now = get_call_counts()
        line = run_mode.end_line(now["generative"] - start["generative"], now["embedding"] - start["embedding"])
        if line:
            logger.info(line)


def _run(mode: str) -> None:
    from src import run_mode
    from src.pipeline_config import (
        load_pipeline_config, load_relevance_rules, load_category_taxonomy,
    )
    from src.filter import partition_by_relevance
    from src.storage import (
        expire_buffer_articles, get_traffic_buffer, upsert_hot_topic_report,
        get_recent_hot_topic_reports, mark_articles_analyzed,
    )
    from src.analyzer import analyze_hot_topic, analyze_category_digest
    from src.topic_scoring import (
        cluster_traffic_articles, score_topic_buckets,
        select_hot_topics_with_novelty,
        select_digest_pool, log_digest_pool_composition, log_digest_pool_concentration,
        log_digest_pool_sources,
    )
    from src.publisher import publish_hot_topic_reports

    dry = mode != run_mode.FORMAL
    logger.info("=== 週交通熱點分析開始 ===")

    # 1. Load config
    # 分類法注入設定載入，讓 category_digest.*.include_categories 的存在性檢查
    # 在正式環境真的生效（013 C1-4）。刻意不在 pipeline_config 內部載分類法——
    # 見該函式的 docstring。
    config = load_pipeline_config(known_categories=set(load_category_taxonomy()))
    max_age_weeks = config.get("buffer", {}).get("max_age_weeks", 8)
    week_start = _week_start_date()
    logger.info("分析週次開始日：%s", week_start)

    # 2. Expire old buffer articles
    expired = expire_buffer_articles()
    if not dry:  # 不發布時沒有清理，略過那一行由 expire_buffer_articles 印
        logger.info("已清理過期 buffer：%d 筆", expired)

    # 3. Fetch buffer
    articles = get_traffic_buffer(max_age_weeks)
    logger.info("buffer 中有 %d 篇待分析文章", len(articles))
    if dry:
        articles = _overlay_collected(articles)

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
    digest_pools = []  # 不發布：每個彙整類別的池，寫進選材產物
    for cat in sorted(digest_cfgs):
        dcfg = digest_cfgs[cat]
        selected, pool_all, effective = select_digest_pool(articles, cat, dcfg, excluded_links)
        trigger_count = int(dcfg.get("trigger_count", 10))
        is_trigger = effective >= trigger_count and selected
        # 013 C3：池組成逐類別留痕（含零篇類別，理由見該函式 docstring）。
        # 印在觸發判定之前，故未觸發時仍看得到組成。
        log_digest_pool_composition(logger, cat, dcfg, pool_all)
        log_digest_pool_concentration(logger, cat, pool_all)
        log_digest_pool_sources(logger, cat, pool_all)
        logger.info(
            "digest[%s] pool=%d effective=%d threshold=%d → %s",
            cat, len(pool_all), effective, trigger_count,
            "TRIGGER" if is_trigger else "accumulate",
        )
        if dry:
            digest_pools.append((cat, trigger_count, selected, pool_all, effective))
        if is_trigger:
            triggered_digests.append((cat, selected, pool_all, effective))
    # 同週多 digest 超額：依有效篇數降冪取足；落選 digest 不消耗、留待下週
    triggered_digests.sort(key=lambda t: t[3], reverse=True)
    triggered_digests = triggered_digests[:max_hot_topics]
    # digest 先佔席次，一般 bucket 取剩餘（FR-007：反餓死，不與 bucket 比分數）
    hot_topic_ids = hot_topic_ids[:max_hot_topics - len(triggered_digests)]
    if dry:
        _dump_selection(mode, week_start, buckets, bucket_scores, hot_topic_ids, digest_pools, triggered_digests)

    if not hot_topic_ids and not triggered_digests:
        logger.info("無 bucket 達到 min_threshold，跳過本週熱點發布")
        return
    if mode == run_mode.DRY_INPUT:
        logger.info(run_mode.stop_line("熱點分析"))
        return

    # 7. Analyze and persist each hot topic
    published_reports = []
    outputs = []  # 不發布：每份報告的全文與 check_report() 的命中
    for bid in hot_topic_ids:
        bucket_articles = buckets[bid]
        topic_label, signature = _hot_topic_label(bid, bucket_articles)

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
        if dry:
            outputs.append(_report_output(report, "hot", bucket_articles))

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
        if dry:
            outputs.append(_report_output(report, "digest", selected))

        # 消耗：upsert 已標記選材 links，這裡補標池內殘餘（含低品質文），池歸零。
        # mark 失敗時 helper 記 ERROR 回 0——殘餘下週重入池，同鍵 upsert 冪等。
        selected_links = {a.get("link") for a in selected if a.get("link")}
        residual = [
            a.get("link") for a in pool_all
            if a.get("link") and a.get("link") not in selected_links
        ]
        marked = mark_articles_analyzed(residual)
        if not dry:  # 不發布時沒有消耗；略過的筆數由 upsert_hot_topic_report、mark_articles_analyzed 印
            logger.info("digest[%s] consumed=%d", cat, len(selected_links) + marked)

    # 8. Publish（不發布時站台檔不產生，報告全文寫進 ANALYSIS_OUTPUT_DIR）
    if dry:
        if published_reports:
            logger.info(run_mode.skip_write_line(f"站台檔 {_HOT_TOPICS_FILE}", len(published_reports)))
        _dump_reports(mode, week_start, outputs)
        logger.info("=== 週交通熱點分析完成，產生 %d 份報告，沒有發布 ===", len(published_reports))
        return
    if published_reports:
        try:
            publish_hot_topic_reports(published_reports)
        except Exception as e:
            logger.error("publish_hot_topic_reports 失敗：%s", e)

    logger.info("=== 週交通熱點分析完成，共發布 %d 個熱點 ===", len(published_reports))


def _hot_topic_label(bid, bucket_articles: list) -> tuple:
    from src.topic_scoring import topic_token_signature

    # Topic label = "<major_category> · <top representative term>" so distinct
    # buckets within a category don't collide on the (week, topic_label) key.
    major_category = bucket_articles[0].get("major_category", bid) if bucket_articles else bid
    signature = topic_token_signature(bucket_articles)
    return (f"{major_category} · {signature[0]}" if signature else major_category), signature


def _published_utc(value):
    """published 解析成 UTC；沒時區的當 UTC（timestamptz 在 UTC 的 session 下也這樣讀），沒有或解析不了回 None。"""
    from src.filter import _parse_published

    if not value:
        return None
    try:
        dt = _parse_published(value)
    except (TypeError, ValueError):
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _stored_published(value):
    """存進 buffer 再讀回來的樣子（UTC 的 ISO 字串），日期的 [:10] 才跟 buffer 的列對得上；解析不了的照原樣。"""
    dt = _published_utc(value)
    return dt.isoformat() if dt else value


def _overlay_collected(buffer: list) -> list:
    """不發布：buffer 疊上 main.py 這次收集的清單（正式執行時它們先寫進 buffer 才被讀到）。同一個 link 留 buffer 那份
    （正式的寫入不覆寫既有列）；排成 get_traffic_buffer 的順序：新到舊、沒日期的在最前。疊不上也印一行。"""
    import json

    head = f"[不發布] 分析的輸入：buffer {len(buffer)} 篇，"
    out_dir = os.environ.get("TRAFFIC_POOL_DIR", "").strip()
    if not out_dir:
        logger.info("%s沒有疊上這次收集的清單（未設 TRAFFIC_POOL_DIR）", head)
        return buffer
    path = os.path.join(out_dir, _COLLECTED_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)["articles"]
    except FileNotFoundError:
        logger.info("%s沒有疊上這次收集的清單（找不到 %s）", head, path)
        return buffer
    except (OSError, ValueError) as e:
        logger.warning("%s沒有疊上這次收集的清單（讀不了 %s：%s）", head, path, e)
        return buffer
    links = {a.get("link") for a in buffer}
    added = [{**r, "published": _stored_published(r.get("published"))} for r in rows if r.get("link") not in links]
    logger.info("%s加上這次收集的 %d 篇（其中 %d 篇 buffer 裡已經有）", head, len(rows), len(rows) - len(added))
    return sorted(buffer + added, key=lambda a: _published_utc(a.get("published")) or _NULLS_FIRST, reverse=True)


def _brief(article: dict) -> dict:
    return {k: article.get(k) for k in _BRIEF_FIELDS}


def _dump_selection(mode, week_start, buckets, bucket_scores, hot_topic_ids, digest_pools, triggered_digests) -> None:
    """不發布：選出的熱點 bucket、每個彙整類別的池（篇數、來源分布、入選）寫進 TRAFFIC_POOL_DIR。
    selected_for_analysis 是扣完席次之後、這次真的會分析的那幾類。"""
    from collections import Counter
    from src import artifacts

    def build():
        reported = {cat for cat, *_ in triggered_digests}
        hot = []
        for bid in hot_topic_ids:
            label, _ = _hot_topic_label(bid, buckets[bid])
            hot.append({"bucket_id": bid, "topic_label": label, "score": bucket_scores[bid],
                        "article_count": len(buckets[bid]), "articles": [_brief(a) for a in buckets[bid]]})
        digests = []
        for cat, trigger_count, selected, pool_all, effective in digest_pools:
            per_src = sorted(Counter(a.get("source") for a in pool_all).items(), key=lambda kv: (-kv[1], str(kv[0])))
            digests.append({
                "category": cat, "selected_for_analysis": cat in reported, "pool_count": len(pool_all),
                "effective_count": effective, "trigger_count": trigger_count,
                "sources": [{"source": s, "count": n} for s, n in per_src],
                "selected": [_brief(a) for a in selected],
            })
        data = {"run_mode": mode, "week_start_date": week_start, "hot_topics": hot, "digests": digests}
        return data, f"熱點 {len(hot)} 個，彙整 {len(reported)} 類"

    artifacts.write_json(logger, "交通熱點選材", "TRAFFIC_POOL_DIR", build, _SELECTION_FILE)


def _check_hits(report: dict, template: str, articles: list) -> dict:
    """check_report() 的輸入照 scripts/replay_report_review.py 的 run_checks 組：來源依報告的 [i] 排、摘要截到生成時的長度。"""
    from src import analyzer
    from src.report_review import check_report, is_title_only

    by_link = {a.get("link"): a for a in articles}
    ordered = [by_link[item["link"]] for item in report["source_article_links"]]
    chars = analyzer.DIGEST_SUMMARY_CHARS if template == "digest" else analyzer.HOT_SUMMARY_CHARS
    sources = [{"link": a.get("link"), "title": a.get("title"), "published": (a.get("published") or "")[:10],
                "summary": (a.get("summary") or "")[:chars]} for a in ordered]
    title_only = [i for i, a in enumerate(ordered, 1) if is_title_only(a.get("title") or "", a.get("summary") or "")]
    return check_report(report["report_text"], template=template, sources=sources, title_only_ids=title_only)


def _report_output(report: dict, template: str, articles: list) -> dict:
    """不發布：一份報告的全文加上 check_report() 的命中；命中沒有逐條判定過，也不擋任何東西。
    檢查自己丟錯時報告照樣留下，那一份標成沒有跑完並印一行。"""
    try:
        check = {"status": "未經逐條判定", "hits": _check_hits(report, template, articles)}
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
        logger.warning("check_report() 沒有跑完，%s 的報告照樣留下：%s", report.get("topic_label"), error)
        check = {"status": "檢查沒有跑完", "error": error}
    return {"template": template, **report, "check_report": check}


def _dump_reports(mode: str, week_start: str, outputs: list) -> None:
    from src import artifacts

    def build():
        data = {"run_mode": mode, "week_start_date": week_start, "report_count": len(outputs), "reports": outputs}
        return data, f"{len(outputs)} 份報告"

    artifacts.write_json(logger, "報告全文", "ANALYSIS_OUTPUT_DIR", build, _REPORTS_FILE)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("traffic_weekly_analysis.py 執行失敗")
        sys.exit(1)
