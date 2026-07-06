"""
storage.py
Supabase 持久化儲存層
負責將每週分析結果寫入 Supabase PostgreSQL，並支援跨週查詢。

資料表定義見 supabase_schema.sql；既有庫加欄請執行
supabase_migrations/001_add_content_fingerprint.sql。
"""

import hashlib
import os
import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

_client = None

# 正規化 title / source / published 後 sha256，供無 URL 文章穩定 upsert（與列表順序無關）
_FINGERPRINT_SEP = "\x01"


def _normalize_fingerprint_part(s: str) -> str:
    if not s:
        return ""
    t = str(s).strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def content_fingerprint_for_article(article: dict) -> str:
    """回傳 64 字元 hex（sha256），僅依 title + source + published，與 week 無關。"""
    raw = _FINGERPRINT_SEP.join(
        [
            _normalize_fingerprint_part(article.get("title", "")),
            _normalize_fingerprint_part(article.get("source", "")),
            _normalize_fingerprint_part(str(article.get("published") or "")),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def stable_synthetic_link(week_id: str, article: dict) -> Tuple[str, str]:
    """
    無有效 link 時使用。link 與 content_fingerprint 對應同一 sha256，供 DB 索引與除錯。
    """
    fp = content_fingerprint_for_article(article)
    link = f"urn:traffic-issue-scraper:{week_id}:{fp}"
    return link, fp


def _title_fingerprint(title: str) -> str:
    """sha256 of normalized title — cross-week dedup signal stored in content_fingerprint column."""
    normalized = re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_existing_title_fingerprints() -> set:
    """
    Fetch all title fingerprints from Supabase for cross-week dedup.
    Returns empty set if Supabase is not configured or the query fails (FR-004).
    """
    if not is_configured():
        return set()
    try:
        client = _get_client()
        resp = (
            client.table("articles")
            .select("content_fingerprint")
            .not_.is_("content_fingerprint", "null")
            .execute()
        )
        return {row["content_fingerprint"] for row in (resp.data or [])}
    except Exception as e:
        logger.warning("跨週指紋查詢失敗：%s", e)
        return set()


def supabase_api_key() -> str:
    """
    REST API 用的金鑰。週報 / 後台寫入請用 service role（略過 RLS）；
    若誤用 anon key 且 articles 表啟用 RLS，會出現 42501 row-level security。
    """
    return (
        (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        or (os.environ.get("SUPABASE_KEY") or "").strip()
    )


def _get_client():
    """取得或初始化 Supabase client（lazy init，避免 import 時即連線）"""
    global _client
    if _client is not None:
        return _client

    url = (os.environ.get("SUPABASE_URL") or "").strip()
    key = supabase_api_key()

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 或金鑰未設定。"
            "GitHub Actions 請設定 secrets：SUPABASE_URL 與 SUPABASE_SERVICE_ROLE_KEY（service role，非 anon）。"
        )

    try:
        from supabase import create_client
        _client = create_client(url, key)
        logger.info("Supabase client 初始化成功：%s", url)
        return _client
    except ImportError:
        raise RuntimeError(
            "supabase 套件未安裝。請執行 pip install supabase 或更新 requirements.txt。"
        )


def upsert_articles(articles: list, week_id: str) -> int:
    """
    將本週文章 upsert 至 Supabase。
    以 link 作為唯一鍵（衝突時更新），支援重跑覆蓋。

    回傳：成功寫入的筆數
    """
    if not articles:
        logger.warning("upsert_articles：articles 為空，跳過")
        return 0

    client = _get_client()

    rows = []
    for a in articles:
        analysis = a.get("analysis", {})
        link = (a.get("link") or "").strip()
        if not link:
            link, _ = stable_synthetic_link(week_id, a)
            logger.warning("文章無有效 link，使用指紋占位鍵：%s…", link[:56])
        rows.append({
            "week_id": week_id,
            "title": a.get("title", ""),
            "link": link,
            "source": a.get("source", ""),
            "published": a.get("published") or None,
            "summary": analysis.get("summary", ""),
            "analysis": analysis,
            "content_fingerprint": _title_fingerprint(a.get("title", "")),
            "content_type": a.get("content_type", "traffic"),
            "image_url": a.get("image") or None,
        })

    try:
        resp = (
            client.table("articles")
            .upsert(rows, on_conflict="link")
            .execute()
        )
        count = len(resp.data) if resp.data else 0
        logger.info("✓ Supabase upsert 完成：%d 筆（week_id=%s）", count, week_id)
        return count
    except Exception as e:
        logger.error("✗ Supabase upsert 失敗：%s", e)
        err = str(e).lower()
        if "row-level security" in err or "42501" in err:
            logger.error(
                "提示：此錯誤通常表示使用了 anon public key。"
                "請改為 SUPABASE_SERVICE_ROLE_KEY（Settings → API → service_role secret）。"
            )
        raise


def get_week(week_id: str) -> list:
    """
    從 Supabase 取得指定週的所有文章，依重要性排序。
    重要性順序：高 > 中 > 低
    """
    client = _get_client()

    try:
        resp = (
            client.table("articles")
            .select("*")
            .eq("week_id", week_id)
            .order("created_at")
            .execute()
        )
        rows = resp.data or []
        logger.info("get_week(%s)：取得 %d 筆", week_id, len(rows))

        # 按重要性排序（DB 存的是 analysis JSONB）
        order = {"高": 0, "中": 1, "低": 2}
        rows.sort(
            key=lambda r: order.get(
                (r.get("analysis") or {}).get("importance", "中"), 1
            )
        )
        return rows
    except Exception as e:
        logger.error("get_week 失敗：%s", e)
        raise


def get_all_weeks() -> list:
    """
    取得所有已存在的週別清單（不含文章內容），按週別降冪排序。
    回傳格式：[{"week_id": "2026-W18", "count": 20, "high_count": 15}, ...]
    """
    client = _get_client()

    try:
        resp = (
            client.table("articles")
            .select("week_id, analysis")
            .execute()
        )
        rows = resp.data or []

        # 在 Python 端彙總（Supabase free tier 不支援 GROUP BY via REST）
        weeks: dict = {}
        for r in rows:
            wid = r.get("week_id", "")
            if not wid:
                continue
            if wid not in weeks:
                weeks[wid] = {"week_id": wid, "count": 0, "high_count": 0}
            weeks[wid]["count"] += 1
            importance = (r.get("analysis") or {}).get("importance", "中")
            if importance == "高":
                weeks[wid]["high_count"] += 1

        result = sorted(weeks.values(), key=lambda x: x["week_id"], reverse=True)
        logger.info("get_all_weeks：共 %d 週記錄", len(result))
        return result
    except Exception as e:
        logger.error("get_all_weeks 失敗：%s", e)
        raise


def ping() -> bool:
    """
    向 Supabase 發送輕量請求，防止免費 tier 因閒置暫停。
    回傳 True 表示連線正常。
    """
    try:
        client = _get_client()
        # 只取 1 筆，最輕量的查詢
        client.table("articles").select("id").limit(1).execute()
        logger.info("Supabase ping 成功")
        return True
    except Exception as e:
        logger.warning("Supabase ping 失敗：%s", e)
        return False


def is_configured() -> bool:
    """檢查環境變數是否已設定，不拋出例外"""
    return bool((os.environ.get("SUPABASE_URL") or "").strip() and supabase_api_key())


# ── Traffic Buffer (US1) ──────────────────────────────────────────────────────

def upsert_traffic_buffer(articles: list, week_id: str, max_age_weeks: int = 8) -> int:
    """
    Insert traffic articles into the buffer (articles table with content_type='traffic').
    Sets major_category, initial_quality_score, buffered_at, buffer_expires_at,
    hot_topic_analyzed=FALSE. Link is the conflict key; rows whose link already
    exists are skipped, never overwritten. Returns count of newly inserted rows.
    """
    from datetime import datetime, timezone, timedelta

    if not articles:
        return 0

    client = _get_client()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(weeks=max_age_weeks)

    seen_links: set = set()
    rows = []
    for a in articles:
        link = (a.get("link") or "").strip()
        if not link:
            link, _ = stable_synthetic_link(week_id, a)
        if link in seen_links:
            continue
        seen_links.add(link)
        rows.append({
            "week_id": week_id,
            "title": a.get("title", ""),
            "link": link,
            "source": a.get("source", ""),
            "published": a.get("published") or None,
            "summary": a.get("summary", ""),
            "analysis": {},
            # Title-only fingerprint — must match what freshness_filter compares
            # (filter.title_fingerprint); the composite title|source|published
            # variant made cross-week dedup a silent no-op for traffic.
            "content_fingerprint": _title_fingerprint(a.get("title", "")),
            "content_type": "traffic",
            "major_category": a.get("major_category"),
            "initial_quality_score": a.get("initial_quality_score"),
            "buffered_at": now.isoformat(),
            "buffer_expires_at": expires_at.isoformat(),
            "hot_topic_analyzed": False,
            "embedding": a.get("embedding"),
            "image_url": a.get("image") or None,
        })

    try:
        # ignore_duplicates: a re-fetched link must not overwrite the existing
        # row — the plain upsert was resetting hot_topic_analyzed to False,
        # re-weeking the row and extending its expiry on every re-collection.
        resp = (
            client.table("articles")
            .upsert(rows, on_conflict="link", ignore_duplicates=True)
            .execute()
        )
        count = len(resp.data) if resp.data else 0
        logger.info("✓ traffic buffer upsert 完成：%d 筆新增（week_id=%s）", count, week_id)
        return count
    except Exception as e:
        logger.error("✗ traffic buffer upsert 失敗：%s", e)
        raise


def get_traffic_buffer(max_age_weeks: int = 8) -> list:
    """
    Return unbuffered traffic articles from the last max_age_weeks weeks.
    Filters: content_type='traffic', hot_topic_analyzed=FALSE, buffer_expires_at > NOW().
    Ordered by published DESC.
    """
    from datetime import datetime, timezone

    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = (
            client.table("articles")
            .select("*")
            .eq("content_type", "traffic")
            .eq("hot_topic_analyzed", False)
            .gt("buffer_expires_at", now)
            .order("published", desc=True)
            .execute()
        )
        rows = resp.data or []
        logger.info("get_traffic_buffer：取得 %d 筆", len(rows))
        return rows
    except Exception as e:
        logger.error("get_traffic_buffer 失敗：%s", e)
        raise


def expire_buffer_articles() -> int:
    """
    Delete expired, unanalyzed traffic buffer articles.
    Removes rows where content_type='traffic', hot_topic_analyzed=FALSE,
    buffer_expires_at < NOW(). Returns count deleted.
    """
    from datetime import datetime, timezone

    client = _get_client()
    now = datetime.now(timezone.utc).isoformat()

    try:
        resp = (
            client.table("articles")
            .delete()
            .eq("content_type", "traffic")
            .eq("hot_topic_analyzed", False)
            .lt("buffer_expires_at", now)
            .execute()
        )
        count = len(resp.data) if resp.data else 0
        logger.info("expire_buffer_articles：刪除 %d 筆過期 buffer", count)
        return count
    except Exception as e:
        logger.error("expire_buffer_articles 失敗：%s", e)
        raise


def get_recent_hot_topic_reports(max_age_weeks: int = 8, exclude_week: str | None = None) -> list:
    """
    Return hot_topic_reports from the last max_age_weeks weeks for the novelty gate
    (feature 009). Excludes exclude_week (the current run's own week) so re-running
    the same week stays idempotent. Selects only the fields needed for comparison.
    Raises on read failure — caller decides fail-open behaviour.
    """
    from datetime import datetime, timezone, timedelta

    client = _get_client()
    cutoff = (datetime.now(timezone.utc) - timedelta(weeks=max_age_weeks)).date().isoformat()

    try:
        query = (
            client.table("hot_topic_reports")
            .select(
                "week_start_date, topic_label, cumulative_score, distinct_days, "
                "topic_token_signature, latest_source_date"
            )
            .gte("week_start_date", cutoff)
            .order("week_start_date", desc=True)
        )
        if exclude_week:
            query = query.neq("week_start_date", exclude_week)
        resp = query.execute()
        rows = resp.data or []
        logger.info(
            "get_recent_hot_topic_reports：取得 %d 筆（cutoff=%s, exclude=%s）",
            len(rows), cutoff, exclude_week,
        )
        return rows
    except Exception as e:
        logger.error("get_recent_hot_topic_reports 失敗：%s", e)
        raise


def upsert_hot_topic_report(report: dict) -> None:
    """
    Upsert one row to hot_topic_reports using (week_start_date, topic_label) as conflict key.
    After upsert, marks all source articles as hot_topic_analyzed=TRUE.
    """
    client = _get_client()

    row = {
        "week_start_date": report["week_start_date"],
        "topic_label": report["topic_label"],
        "report_text": report["report_text"],
        "source_article_count": report.get("source_article_count", 0),
        "source_article_links": report.get("source_article_links", []),
        "cumulative_score": float(report.get("cumulative_score", 0)),
        "distinct_sources": report.get("distinct_sources", 0),
        "distinct_days": report.get("distinct_days", 0),
        "topic_token_signature": report.get("topic_token_signature", []),
        "latest_source_date": report.get("latest_source_date"),
    }

    try:
        client.table("hot_topic_reports").upsert(
            row,
            on_conflict="week_start_date,topic_label",
        ).execute()
        logger.info(
            "✓ hot_topic_report upserted: %s / %s",
            report["week_start_date"], report["topic_label"],
        )
    except Exception as e:
        logger.error("✗ hot_topic_report upsert 失敗：%s", e)
        raise

    # Mark source articles as analyzed
    raw_links = report.get("source_article_links", [])
    links = [
        item["link"] if isinstance(item, dict) else item
        for item in raw_links
        if item
    ]
    if not links:
        return
    try:
        client.table("articles").update({"hot_topic_analyzed": True}).in_(
            "link", links
        ).execute()
        logger.info("已標記 %d 篇文章為 hot_topic_analyzed", len(links))
    except Exception as e:
        logger.warning("標記 hot_topic_analyzed 失敗：%s", e)