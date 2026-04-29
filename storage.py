"""
storage.py
Supabase 持久化儲存層
負責將每週分析結果寫入 Supabase PostgreSQL，並支援跨週查詢。

Schema（請在 Supabase SQL Editor 執行）：
    CREATE TABLE articles (
        id          SERIAL PRIMARY KEY,
        week_id     TEXT NOT NULL,
        title       TEXT NOT NULL,
        link        TEXT UNIQUE,
        source      TEXT,
        published   TEXT,
        summary     TEXT,
        analysis    JSONB,
        created_at  TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX idx_articles_week_id ON articles(week_id);
    CREATE INDEX idx_articles_importance ON articles((analysis->>'importance'));
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """取得或初始化 Supabase client（lazy init，避免 import 時即連線）"""
    global _client
    if _client is not None:
        return _client

    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")

    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL 或 SUPABASE_KEY 環境變數未設定。"
            "請在 GitHub Secrets 中新增這兩個變數。"
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
        rows.append({
            "week_id": week_id,
            "title": a.get("title", ""),
            "link": a.get("link", ""),
            "source": a.get("source", ""),
            "published": a.get("published", ""),
            "summary": analysis.get("summary", ""),
            "analysis": analysis,
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
    return bool(
        os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY")
    )