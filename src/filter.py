"""
filter.py
機車關鍵字過濾 + 去重複
"""

import hashlib
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 必須包含的機車相關關鍵字（至少命中一個）
MUST_INCLUDE = [
    "機車", "摩托車", "重機", "白牌", "紅牌", "黃牌",
    "gogoro", "電動機車", "考照", "機車路權", "騎士",
    "普通重型", "大型重型", "機車道", "機車停車",
    "機車違規", "機車事故", "肇事逃逸",
    "交通事故.*機車", "機車.*交通",
]

# 排除明顯不相關的關鍵字
EXCLUDE_KEYWORDS = [
    "汽車貸款廣告", "二手車廣告", "保險推銷",
]

# PTT 排除的文章類型
PTT_EXCLUDE_PREFIXES = ["[公告]", "[版規]", "Fw:", "[Fw]"]

# 同主題去重：標題中若包含這些核心詞組，視為同一主題
# 格式：(主題識別詞組, 最多保留篇數)
TOPIC_THROTTLE = [
    (["淡江大橋", "機車道"], 3),
]


def _clean_html(text: str) -> str:
    """移除 HTML 標籤"""
    return re.sub(r"<[^>]+>", "", text).strip()


def _is_relevant(article: dict) -> bool:
    title = _clean_html(article.get("title", ""))
    summary = _clean_html(article.get("summary", ""))
    combined = title + " " + summary

    if article.get("source", "").startswith("PTT"):
        for prefix in PTT_EXCLUDE_PREFIXES:
            if title.startswith(prefix):
                return False

    for kw in EXCLUDE_KEYWORDS:
        if kw in combined:
            return False

    for kw in MUST_INCLUDE:
        if re.search(kw, combined):
            return True

    return False


def _make_hash(article: dict) -> str:
    """用標題做 hash 去重複"""
    title = re.sub(r"\s+", "", article.get("title", "")).lower()
    title = re.sub(r"^\[.*?\]", "", title)
    return hashlib.md5(title.encode("utf-8")).hexdigest()


def _topic_key(title: str) -> str | None:
    """
    判斷文章屬於哪個需要限流的主題，回傳主題識別字串或 None。
    """
    for keywords, _ in TOPIC_THROTTLE:
        if all(kw in title for kw in keywords):
            return "+".join(keywords)
    return None

def _extract_year_from_text(text: str) -> int | None:
    """從標題或摘要抓出明確的年份"""
    matches = re.findall(r'\b(20\d{2})\b', text)
    for m in matches:
        year = int(m)
        if 2020 <= year <= datetime.now().year + 1:
            return year
    return None

def _is_stale_article(article: dict) -> bool:
    """
    判斷文章是否為舊聞：
    1. 標題或摘要中出現明確的舊年份
    2. published 欄位有值且超過 14 天（給一點容錯空間）
    """
    current_year = datetime.now().year
    title = article.get("title", "")
    summary = article.get("summary", "")

    # 信號 1：文字中出現的年份明顯過舊
    year = _extract_year_from_text(title + " " + summary)
    if year and year < current_year - 1:
        return True

    # 信號 2：published 欄位解析後超過 14 天
    published = article.get("published", "")
    if published:
        try:
            from email.utils import parsedate_to_datetime
            pub_dt = parsedate_to_datetime(published)
            cutoff = datetime.now(pub_dt.tzinfo) - timedelta(days=14)
            if pub_dt < cutoff:
                return True
        except Exception:
            pass

    return False


def filter_and_deduplicate(articles: list) -> list:
    seen_hashes = set()
    topic_counts: dict = {}  # topic_key -> 已收錄篇數
    result = []

    # 建立 topic_throttle 查找表 {key: max_count}
    topic_limits = {"+".join(kws): limit for kws, limit in TOPIC_THROTTLE}

    for article in articles:
        if not article.get("title"):
            continue
        # ── 新增：舊聞過濾 ──
        if _is_stale_article(article):
            stale_count += 1
            logger.debug("舊聞跳過：%s", article.get("title", "")[:40])
            continue
        if not _is_relevant(article):
            continue

        h = _make_hash(article)
        if h in seen_hashes:
            continue

        title = _clean_html(article.get("title", ""))
        tkey = _topic_key(title)

        if tkey is not None:
            current = topic_counts.get(tkey, 0)
            limit = topic_limits.get(tkey, 99)
            if current >= limit:
                logger.debug("主題限流（%s）跳過：%s", tkey, title[:40])
                continue
            topic_counts[tkey] = current + 1

        seen_hashes.add(h)
        result.append(article)

    skipped_topics = {k: v for k, v in topic_counts.items() if v >= topic_limits.get(k, 99)}
    if skipped_topics:
        logger.info("主題限流統計：%s", skipped_topics)

    logger.info(f"過濾後剩 {len(result)} 筆（原 {len(articles)} 筆）")
    return result