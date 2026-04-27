"""
publisher.py
將分析結果發布至 docs/ 目錄：
  - docs/data/YYYY-WNN.json   本週資料
  - docs/data/index.json      所有週別索引（供首頁載入）
  - docs/data/tags.json       累積標籤庫（含使用者手動標籤，供下週 AI 參考）
  - docs/feed.xml             RSS feed
  - docs/week/YYYY-WNN.html   本週靜態頁面（Pagefind 索引用）
GitHub Actions 後續執行 Pagefind 建立搜尋索引。
"""

import json
import os
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))
DOCS_DIR = Path(__file__).parent / "docs"
DATA_DIR = DOCS_DIR / "data"
WEEK_DIR = DOCS_DIR / "week"
SITE_URL = os.environ.get("SITE_URL", "https://lukeking.github.io/traffic-issue-scraper")


def _now_tw():
    return datetime.now(TW_TZ)


def _week_id(dt=None):
    dt = dt or _now_tw()
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


# ── JSON 資料 ──────────────────────────────────────────────────

def _load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_week_data(articles: list) -> str:
    """儲存本週 JSON，回傳 week_id"""
    week_id = _week_id()
    now = _now_tw()
    data = {
        "week_id": week_id,
        "generated_at": now.isoformat(),
        "date_label": now.strftime("%Y 年 %m 月 %d 日"),
        "article_count": len(articles),
        "articles": articles,
    }
    path = DATA_DIR / f"{week_id}.json"
    _save_json(path, data)
    logger.info("週資料已儲存：%s", path)
    return week_id


def update_index(week_id: str, articles: list):
    """更新 index.json，記錄每週的 week_id、日期、文章數"""
    path = DATA_DIR / "index.json"
    index = _load_json(path, [])

    # 移除同一週的舊記錄（重跑時覆蓋）
    index = [w for w in index if w.get("week_id") != week_id]

    now = _now_tw()
    index.append({
        "week_id": week_id,
        "date_label": now.strftime("%Y/%m/%d"),
        "article_count": len(articles),
        "high_count": sum(1 for a in articles if a.get("analysis", {}).get("importance") == "高"),
    })
    index.sort(key=lambda x: x["week_id"], reverse=True)
    _save_json(path, index)
    logger.info("index.json 已更新，共 %d 週記錄", len(index))


def update_tags(articles: list):
    """
    累積標籤庫：
      - ai_tags: AI 自動產生的標籤（含出現次數）
      - user_tags: 使用者手動新增的標籤（網頁操作後寫回此檔）
    下週 AI 分析時會讀取 user_tags 加入 prompt。
    """
    path = DATA_DIR / "tags.json"
    store = _load_json(path, {"ai_tags": {}, "user_tags": []})

    for article in articles:
        for tag in article.get("analysis", {}).get("tags", []):
            store["ai_tags"][tag] = store["ai_tags"].get(tag, 0) + 1

    # user_tags 由網頁端操作，publisher 只讀不寫，保持原樣
    _save_json(path, store)
    logger.info("tags.json 已更新，AI 標籤 %d 種", len(store["ai_tags"]))
    return store


# ── RSS Feed ──────────────────────────────────────────────────

def _escape_xml(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_feed(all_weeks_articles: list, week_id: str):
    """產生 RSS feed（最新 3 週的文章）"""
    now_rfc = _now_tw().strftime("%a, %d %b %Y %H:%M:%S +0800")

    items = []
    for article in all_weeks_articles[:60]:  # 最多 60 篇
        analysis = article.get("analysis", {})
        tags = analysis.get("tags", [])
        categories = "".join(f"    <category>{_escape_xml(t)}</category>\n" for t in tags)
        summary = _escape_xml(analysis.get("summary", ""))
        analysis_text = _escape_xml(analysis.get("analysis", ""))
        description = f"{summary}\n\n{analysis_text}".strip()
        importance = analysis.get("importance", "中")
        title = f"[{importance}重要] {_escape_xml(article.get('title', ''))}"
        link = _escape_xml(article.get("link", "#"))
        pub_date = _escape_xml(article.get("published", now_rfc))

        items.append(f"""  <item>
    <title>{title}</title>
    <link>{link}</link>
    <description><![CDATA[{description}]]></description>
    <pubDate>{pub_date}</pubDate>
    <guid isPermaLink="true">{link}</guid>
{categories}  </item>""")

    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>台灣機車交通週報</title>
  <link>{SITE_URL}</link>
  <description>每週自動彙整台灣機車交通相關新聞，含 AI 摘要與深度分析</description>
  <language>zh-tw</language>
  <lastBuildDate>{now_rfc}</lastBuildDate>
  <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
  <ttl>10080</ttl>
{chr(10).join(items)}
</channel>
</rss>"""

    out = DOCS_DIR / "feed.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(feed, encoding="utf-8")
    logger.info("feed.xml 已產生，共 %d 則", len(items))


# ── 週別靜態 HTML（供 Pagefind 索引）──────────────────────────

def build_week_html(articles: list, week_id: str):
    """
    產生 docs/week/YYYY-WNN.html。
    這份 HTML 不是給人直接看的頁面，而是讓 Pagefind 能夠索引每篇文章的內容。
    網站的 SPA 首頁（index.html）會動態載入 JSON 呈現。
    """
    WEEK_DIR.mkdir(parents=True, exist_ok=True)
    now = _now_tw()
    cards = []
    for i, article in enumerate(articles, 1):
        analysis = article.get("analysis", {})
        tags = analysis.get("tags", [])
        tag_html = " ".join(f'<span class="tag">{t}</span>' for t in tags)
        importance = analysis.get("importance", "中")
        cards.append(f"""
<article data-pagefind-body data-week="{week_id}" data-importance="{importance}">
  <h2>{i}. {article.get('title', '')}</h2>
  <p class="meta">
    <span class="source">{article.get('source', '')}</span>
    <span class="importance">{importance}重要</span>
    <span class="tags">{tag_html}</span>
  </p>
  <p class="summary">{analysis.get('summary', '')}</p>
  <p class="analysis">{analysis.get('analysis', '')}</p>
  <a href="{article.get('link', '#')}" target="_blank" rel="noopener">閱讀原文</a>
</article>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>{week_id} 台灣機車交通週報</title>
</head>
<body>
<header>
  <h1>台灣機車交通週報 {week_id}</h1>
  <p>{now.strftime('%Y 年 %m 月 %d 日')}，共 {len(articles)} 則</p>
</header>
{"".join(cards)}
</body>
</html>"""

    out = WEEK_DIR / f"{week_id}.html"
    out.write_text(html, encoding="utf-8")
    logger.info("週別 HTML 已產生：%s", out)


# ── 主入口 ────────────────────────────────────────────────────

def publish(articles: list):
    """
    articles: 已分析完的文章列表（含 analysis.tags）
    """
    logger.info("=== 開始發布 ===")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    week_id = save_week_data(articles)
    update_index(week_id, articles)
    tags_store = update_tags(articles)

    # 載入所有週資料，供 RSS 使用（最新 3 週）
    index = _load_json(DATA_DIR / "index.json", [])
    recent_articles = []
    for week in index[:3]:
        wid = week["week_id"]
        wdata = _load_json(DATA_DIR / f"{wid}.json", {})
        recent_articles.extend(wdata.get("articles", []))

    build_feed(recent_articles, week_id)
    build_week_html(articles, week_id)

    logger.info("=== 發布完成，week_id=%s ===", week_id)
    return week_id