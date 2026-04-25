"""
filter.py
機車關鍵字過濾 + 去重複
"""

import hashlib
import logging
import re

logger = logging.getLogger(__name__)

# 必須包含的機車相關關鍵字（至少命中一個）
MUST_INCLUDE = [
    "機車", "摩托車", "重機", "白牌", "紅牌", "黃牌",
    "gogoro", "電動機車", "考照", "機車路權", "騎士",
    "普通重型", "大型重型", "機車道", "機車停車",
    "機車違規", "機車事故", "肇事逃逸",
    "交通事故.*機車", "機車.*交通",
]

# 排除明顯不相關的關鍵字（命中則丟棄）
EXCLUDE_KEYWORDS = [
    "汽車貸款廣告", "二手車廣告", "保險推銷",
]

# PTT 排除的文章類型
PTT_EXCLUDE_PREFIXES = ["[公告]", "[版規]", "Fw:", "[Fw]"]


def _clean_html(text: str) -> str:
    """移除 HTML 標籤"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_relevant(article: dict) -> bool:
    title = _clean_html(article.get("title", ""))
    summary = _clean_html(article.get("summary", ""))
    combined = title + " " + summary

    # PTT 排除公告文
    if article.get("source", "").startswith("PTT"):
        for prefix in PTT_EXCLUDE_PREFIXES:
            if title.startswith(prefix):
                return False

    # 排除名單
    for kw in EXCLUDE_KEYWORDS:
        if kw in combined:
            return False

    # 必要關鍵字（用 re 支援簡單 pattern）
    for kw in MUST_INCLUDE:
        if re.search(kw, combined):
            return True

    return False


def _make_hash(article: dict) -> str:
    """用標題做 hash 去重複"""
    title = re.sub(r"\s+", "", article.get("title", "")).lower()
    # 移除常見前綴差異，例如 [即時] [焦點]
    title = re.sub(r"^\[.*?\]", "", title)
    return hashlib.md5(title.encode("utf-8")).hexdigest()


def filter_and_deduplicate(articles: list) -> list:
    seen_hashes = set()
    result = []

    for article in articles:
        if not article.get("title"):
            continue
        if not _is_relevant(article):
            continue

        h = _make_hash(article)
        if h in seen_hashes:
            continue

        seen_hashes.add(h)
        result.append(article)

    logger.info(f"過濾後剩 {len(result)} 筆（原 {len(articles)} 筆）")
    return result