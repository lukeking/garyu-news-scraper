"""
filter.py
機車關鍵字過濾 + 去重複 + 標題正規化 + Jaccard 相似度 + 類別指派
"""

import hashlib
import logging
import os
import re
from datetime import datetime, timedelta, timezone


def _parse_published(published: str) -> datetime:
    """Parse a published string in either ISO 8601 or RFC 2822 format."""
    try:
        return datetime.fromisoformat(published)
    except ValueError:
        pass
    from email.utils import parsedate_to_datetime
    return parsedate_to_datetime(published)

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

    # 信號 2：published 欄位解析後超過 14 天。
    # 帶 lookback_days 的來源已在收集端以自身視窗做過新鮮度閘（_is_recent），
    # 14 天啟發式不適用，否則會抵銷 per-source lookback（15–30 天文章收了又丟）。
    published = article.get("published", "")
    if published and not article.get("lookback_days"):
        try:
            pub_dt = _parse_published(published)
            cutoff = datetime.now(pub_dt.tzinfo) - timedelta(days=14)
            if pub_dt < cutoff:
                return True
        except Exception:
            pass

    return False


# ── 跨週新鮮度過濾 ────────────────────────────────────────────

FRESHNESS_THRESHOLD_DAYS = 30


def _normalize_title_for_fingerprint(title: str) -> str:
    return re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip())


def title_fingerprint(article: dict) -> str:
    """sha256 of the article's normalized title — cross-week dedup signal."""
    normalized = _normalize_title_for_fingerprint(article.get("title", ""))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _extract_url_date(url: str):
    """Extract a publication date from common TW/JP news URL patterns. Returns datetime.date or None."""
    m = re.search(r'/(\d{4})[/-](\d{2})[/-](\d{2})/', url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            pass
    m = re.search(r'[/_-](\d{4})(\d{2})(\d{2})[/_.\-]', url)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date()
        except ValueError:
            pass
    return None


def _is_too_old_by_age(article: dict, threshold_days: int = FRESHNESS_THRESHOLD_DAYS):
    """
    Returns (True, reason) if the article exceeds the age threshold; (False, "") otherwise.
    Google News: checks URL-embedded date. Direct RSS: checks pubDate.
    Returns (False, "") when age cannot be determined — article is included (known limitation).
    """
    link = article.get("link", "")
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=threshold_days)).date()

    if "news.google.com" in link:
        extracted = _extract_url_date(link)
        if extracted is None:
            return False, ""
        if extracted < cutoff_date:
            return True, f"URL date: {extracted}"
        return False, ""
    else:
        published = article.get("published", "")
        if not published:
            return False, ""
        try:
            pub_dt = _parse_published(published)
            if pub_dt.date() < cutoff_date:
                return True, f"pubDate: {pub_dt.date()}"
        except Exception:
            pass
        return False, ""


def freshness_filter(
    articles: list,
    existing_fingerprints: set,
    threshold_days: int = FRESHNESS_THRESHOLD_DAYS,
) -> list:
    """
    Two-layer freshness filter (FR-001, FR-002, FR-003):
      1. Cross-week fingerprint dedup: exclude if title fingerprint in existing_fingerprints
      2. Age gate: exclude if article is older than threshold_days
    Gracefully handles empty existing_fingerprints (Supabase failure path, FR-004).
    """
    result = []
    for article in articles:
        fp = title_fingerprint(article)
        if fp in existing_fingerprints:
            logger.info("跨週去重跳過：%s (fingerprint match)", article.get("title", "")[:50])
            continue
        too_old, reason = _is_too_old_by_age(article, threshold_days)
        if too_old:
            logger.info("過時文章跳過：%s (%s)", article.get("title", "")[:50], reason)
            continue
        result.append(article)
    return result


def filter_and_deduplicate(articles: list, throttle: bool = True) -> list:
    seen_hashes = set()
    topic_counts: dict = {}  # topic_key -> 已收錄篇數
    result = []
    stale_count = 0

    # 建立 topic_throttle 查找表 {key: max_count}
    topic_limits = {"+".join(kws): limit for kws, limit in TOPIC_THROTTLE}

    for article in articles:
        if not article.get("title"):
            continue
        if _is_stale_article(article):
            stale_count += 1
            logger.debug("舊聞跳過：%s", article.get("title", "")[:40])
            continue
        # FFXIV 來源已由來源設定過濾，跳過機車關鍵字檢查；
        # relevance_exempt 來源（政策/深度來源，來源本身即主題篩選）亦豁免
        is_ffxiv = article.get("content_type") == "ffxiv"
        is_youtube = article.get("source_type") == "youtube"
        relevant = is_ffxiv or article.get("relevance_exempt") or _is_relevant(article)
        if not relevant:
            if is_youtube:
                logger.debug("[youtube] 關鍵字篩選已過濾：%s", article.get("title", "")[:60])
            continue
        if is_youtube:
            logger.debug("[youtube] 關鍵字篩選通過：%s", article.get("title", "")[:60])

        h = _make_hash(article)
        if h in seen_hashes:
            continue

        if throttle:
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

    if throttle:
        skipped_topics = {k: v for k, v in topic_counts.items() if v >= topic_limits.get(k, 99)}
        if skipped_topics:
            logger.info("主題限流統計：%s", skipped_topics)

    logger.info(f"過濾後剩 {len(result)} 筆（原 {len(articles)} 筆）")
    return result


# ── 標題正規化 + Jaccard 相似度 + 類別指派 (US4 / Traffic Pipeline) ─────────

# 全型→半型數字對照
_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")

# 中文數字→阿拉伯數字（簡單一位數，足應付新聞標題）
_ZH_DIGIT_MAP = {"零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
                 "五": "5", "六": "6", "七": "7", "八": "8", "九": "9",
                 "十": "10", "百": "100", "千": "1000"}
_ZH_DIGIT_RE = re.compile(r"([零一二三四五六七八九十百千])(?=[人名死傷歲輛起件條])")

# 媒體標籤 / 記者署名模式
_MEDIA_TAG_RE = re.compile(r"[【〔\[［].*?[】〕\]］]|（[^）]*?報導[^）]*?）|／[^\s]{2,6}報導.*$")
_LINK_SUFFIX_RE = re.compile(r"（?相關報導.*$|連結.*$|更多報導.*$")

_jieba_loaded = False


def _load_jieba() -> None:
    global _jieba_loaded
    if _jieba_loaded:
        return
    try:
        import jieba  # noqa: F401
        userdict_path = os.environ.get("JIEBA_USERDICT_PATH", "config/jieba_userdict.txt")
        if os.path.exists(userdict_path):
            jieba.load_userdict(userdict_path)
            logger.info("[filter] jieba 自訂詞典已載入：%s", userdict_path)
        else:
            logger.warning("[filter] jieba 自訂詞典不存在，使用預設分詞：%s", userdict_path)
        _jieba_loaded = True
    except ImportError:
        logger.warning("[filter] jieba 未安裝，將使用字元級 tokenisation")
        _jieba_loaded = True


def normalise_title(title: str) -> frozenset:
    """
    正規化文章標題並回傳 token frozenset，用於 Jaccard 相似度計算。
    步驟：
      1. 移除媒體標籤 【…】 〔…〕 [… ] 及記者署名
      2. 移除「相關報導」「連結」等尾綴
      3. 全型數字 → 半型
      4. 中文數詞 → 阿拉伯數字（人/死/傷等單位前的數詞）
      5. 使用 jieba 分詞，過濾長度 < 2 的 token
    """
    t = _clean_html(title)
    t = _MEDIA_TAG_RE.sub("", t)
    t = _LINK_SUFFIX_RE.sub("", t)
    t = t.translate(_FULLWIDTH_DIGITS)
    t = _ZH_DIGIT_RE.sub(lambda m: _ZH_DIGIT_MAP.get(m.group(1), m.group(1)), t)
    t = t.strip()

    _load_jieba()
    try:
        import jieba
        tokens = jieba.lcut(t)
    except ImportError:
        tokens = list(t)

    return frozenset(tok for tok in tokens if len(tok) >= 2)


def compute_jaccard(set_a: frozenset, set_b: frozenset) -> float:
    """Jaccard 相似度：|A∩B| / |A∪B|。任一集合為空時回傳 0.0。"""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def assign_category(title_tokens: frozenset, taxonomy: dict) -> str:
    """
    依類別分類詞典指派 major_category。
    按詞典定義順序，第一個關鍵字有交集的類別獲勝。
    無任何交集時回傳 'uncategorised'。
    """
    for label, keywords in taxonomy.items():
        kw_set = frozenset(keywords)
        if title_tokens & kw_set:
            return label
    return "uncategorised"


def resolve_source_default(source: str, mapping: dict) -> str:
    """
    Fallback category for an article whose title matched no category.
    The first mapping key found as a substring of `source` wins; otherwise
    'uncategorised'. Lets low-frequency deep sources (e.g. 報導者/天下), whose
    editorial titles carry no category token, aggregate into a policy bucket.
    """
    src = source or ""
    for key, category in mapping.items():
        if key and key in src:
            return category
    return "uncategorised"


def _first_hit(title: str, tokens) -> str:
    """回傳 tokens 中第一個（小寫）為 _clean_html(title) 子字串的 token；皆未命中回傳 None。"""
    clean = _clean_html(title or "").lower()
    for tok in tokens or []:
        if tok and str(tok).lower() in clean:
            return tok
    return None


def _hit(title: str, tokens) -> bool:
    """標題（去 HTML、小寫）是否含 tokens 任一子字串。空 tokens → False。"""
    return _first_hit(title, tokens) is not None


def is_topic_relevant(article: dict, rule: dict) -> bool:
    """
    純函數相關性判定（whitelist-dominant，見 data-model §1；feature 012）。
      - require_any 存在：on-topic = 命中任一 require token（子字串）。
        **exclude_any 在此不生效**——邊界「肇事逃逸/毒駕撞死」由 require 命中解掉。
      - 只有 exclude_any：純黑名單支，未命中 exclude 才 on-topic。
      - 皆無（空 dict / 缺欄）或規則非 dict：fail-open，全通過（不套閘）。
    子字串比對（與 blocked_content_keywords 同法），不用 jieba 切詞。零外部呼叫。
    """
    if not isinstance(rule, dict):
        return True
    req = rule.get("require_any") or []
    exc = rule.get("exclude_any") or []
    title = article.get("title", "")
    if req:
        return _hit(title, req)
    if exc:
        return not _hit(title, exc)
    return True


def partition_by_relevance(articles: list, rules: dict) -> tuple:
    """
    依 per-category 相關性規則把候選集切成 (on_topic, off_topic)（feature 012，§3）。
    每篇原地附上診斷用 `_relevance_reason`（僅 log/診斷）；不改 major_category、不動其他欄位、
    不寫 DB、不呼叫任何網路/AI。各 list 內保留輸入順序。
    類別缺規則（或規則非 dict）→ fail-open，判 on_topic、reason 'no-rule'。
    """
    rules = rules or {}
    on_topic, off_topic = [], []
    for article in articles:
        rule = rules.get(article.get("major_category"))
        if not isinstance(rule, dict):          # 缺鍵 / 格式錯 → 不套閘
            article["_relevance_reason"] = "no-rule"
            on_topic.append(article)
            continue
        req = rule.get("require_any") or []
        exc = rule.get("exclude_any") or []
        title = article.get("title", "")
        if is_topic_relevant(article, rule):
            if req:
                article["_relevance_reason"] = f"kept:{_first_hit(title, req)}"
            elif exc:
                article["_relevance_reason"] = "kept:no-exclude-hit"
            else:
                article["_relevance_reason"] = "kept:no-rule-fields"
            on_topic.append(article)
        else:
            if req:
                article["_relevance_reason"] = "excluded:no-require-hit"
            else:
                article["_relevance_reason"] = f"excluded:{_first_hit(title, exc)}"
            off_topic.append(article)
    return on_topic, off_topic


def compute_quality_score(article: dict, category_keywords: list, config: dict) -> float:
    """
    計算文章初始品質分數（0.0–1.0），不使用 AI。
    公式：kw_match_ratio × w1 + norm_word_count × w2 + source_weight × w3
    """
    weights = config.get("quality_score_weights", {})
    w1 = weights.get("keyword_match_ratio", 0.4)
    w2 = weights.get("normalised_word_count", 0.3)
    w3 = weights.get("source_weight", 0.3)

    title = article.get("title", "")
    body = article.get("summary", "") or ""
    combined = title + " " + body
    word_count = len(combined.replace(" ", ""))

    if category_keywords:
        matched = sum(1 for kw in category_keywords if kw in combined.lower())
        kw_ratio = min(matched / len(category_keywords), 1.0)
    else:
        kw_ratio = 0.0

    norm_wc = min(word_count, 500) / 500.0

    source = article.get("source", "")
    source_weights = config.get("source_weights", {})
    src_weight = source_weights.get(source, 0.5)

    score = kw_ratio * w1 + norm_wc * w2 + src_weight * w3
    return min(max(score, 0.0), 1.0)


def game_deduplicate(articles: list, config: dict) -> list:
    """
    FFXIV 遊戲新聞去重複：
      1. 排除包含關係（A 標題是 B 標題的子集）
      2. 排除 Jaccard > game_threshold 的相似標題
    回傳最多 20 篇，依發布時間降冪排序（最新在前）。
    """
    game_threshold = config.get("jaccard", {}).get("game_threshold", 0.50)

    # 預先計算 token set
    token_sets = []
    for a in articles:
        ts = normalise_title(a.get("title", ""))
        token_sets.append(ts)

    retained_indices: list[int] = []
    retained_token_sets: list[frozenset] = []

    for i, (article, ts_i) in enumerate(zip(articles, token_sets)):
        duplicate = False
        for j, ts_j in enumerate(retained_token_sets):
            if not ts_i or not ts_j:
                continue
            # 包含關係：短標題 token set 是長標題 token set 的子集
            if ts_i <= ts_j or ts_j <= ts_i:
                duplicate = True
                break
            if compute_jaccard(ts_i, ts_j) > game_threshold:
                duplicate = True
                break
        if not duplicate:
            retained_indices.append(i)
            retained_token_sets.append(ts_i)

    retained = [articles[i] for i in retained_indices]

    # 依發布時間排序（最新在前）
    def _pub_key(a):
        pub = a.get("published", "")
        if pub:
            try:
                return _parse_published(pub)
            except Exception:
                pass
        return datetime.min.replace(tzinfo=timezone.utc)

    retained.sort(key=_pub_key, reverse=True)
    return retained[:20]