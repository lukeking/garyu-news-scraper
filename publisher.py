"""
publisher.py
將分析結果發布至 docs/ 目錄：
  - docs/data/YYYY-WNN.json   本週資料
  - docs/data/index.json      所有週別索引（供首頁載入）
  - docs/data/tags.json       累積標籤庫（含使用者手動標籤，供下週 AI 參考）
  - docs/feed.xml             RSS feed
  - docs/week/YYYY-WNN.html   本週靜態頁面（Pagefind 索引用）

同時寫入 Supabase（若環境變數已設定）作為持久化備份。
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


# ── Supabase 持久化 ───────────────────────────────────────────

def _save_to_supabase(articles: list, week_id: str) -> bool:
    """
    將本週文章寫入 Supabase。
    若環境變數未設定則跳過；若已設定但寫入失敗則拋出例外（供 CI 與後續驗證步驟一致）。
    回傳 True 表示成功，False 表示未設定 Supabase。
    """
    try:
        from storage import is_configured, upsert_articles
    except ImportError:
        logger.warning("storage.py 未找到，跳過 Supabase 寫入")
        return False

    if not is_configured():
        logger.info("Supabase 未設定（需 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY），跳過寫入")
        return False

    try:
        count = upsert_articles(articles, week_id)
        logger.info("✓ Supabase 寫入完成：%d 筆（week_id=%s）", count, week_id)
        return True
    except Exception as e:
        logger.exception("✗ Supabase 寫入失敗：%s", e)
        raise RuntimeError(
            "Supabase 寫入失敗：請確認使用 service role key（非 anon），且 articles 表與 RLS 設定正確"
        ) from e


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
        importance = analysis.get("importance", "中")
        imp_dot = {"高": "🔴", "中": "🟡", "低": "🟢"}.get(importance, "")
        color = {"高": "#C0392B", "中": "#D68910", "低": "#27AE60"}.get(importance, "#555")
        src = article.get("source", "")
        src_label = "Google News" if src.startswith("Google News") else src
        tag_spans = "".join(f'<span class="tag">{t}</span>' for t in tags)
        reason = analysis.get("importance_reason", "")
        cards.append(f"""
<div class="card card-{importance}" data-pagefind-body data-week="{week_id}" data-importance="{importance}">
  <div class="card-header">
    <div class="card-meta">
      <span class="imp-badge imp-{importance}">{imp_dot} {importance}重要</span>
      <span class="src-badge">{src_label}</span>
      <span style="color:#999;font-size:12px;">{article.get("published","")}</span>
    </div>
    <a class="card-title" href="{article.get("link","#")}" target="_blank" rel="noopener">{i}. {article.get("title","")}</a>
  </div>
  <div class="card-body">
    <p class="sec-label" style="color:{color}">📋 摘要</p>
    <p class="sec-text">{analysis.get("summary","")}</p>
    <p class="sec-label" style="color:{color}">🔍 深度分析</p>
    <p class="sec-text">{analysis.get("analysis","")}</p>
  </div>
  {f'<div class="card-tags">{tag_spans}</div>' if tags else ""}
  <div class="card-footer">
    <span class="reason">💡 {reason}</span>
    <a class="read-more" href="{article.get("link","#")}" target="_blank" rel="noopener" style="color:{color}">閱讀原文 →</a>
  </div>
</div>""")

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{week_id} 台灣機車交通週報</title>
<style>
  :root {{
    --high:#C0392B; --high-bg:#FFF0F0;
    --mid:#D68910;  --mid-bg:#FFFBF0;
    --low:#27AE60;  --low-bg:#F0FFF4;
    --accent:#1A3C6E; --accent2:#2980B9;
    --tag-bg:#E8F4FD; --tag-text:#1A5276;
  }}
  *{{ box-sizing:border-box; margin:0; padding:0; }}
  body{{ background:#F5F6FA; color:#1a1a2e; font-family:'Helvetica Neue',Arial,sans-serif; }}
  .site-header{{
    background:linear-gradient(135deg,var(--accent) 0%,var(--accent2) 100%);
    color:#fff; padding:24px 20px;
  }}
  .site-header h1{{ font-size:1.4rem; font-weight:800; margin-bottom:4px; }}
  .site-header p{{ font-size:0.85rem; opacity:0.85; }}
  .back-link{{ display:inline-block; margin-bottom:8px; font-size:13px; color:rgba(255,255,255,0.8); text-decoration:none; }}
  .back-link:hover{{ color:#fff; }}
  .main{{ max-width:820px; margin:0 auto; padding:24px 16px 48px; }}
  .card{{
    background:#fff; border-radius:10px; margin-bottom:20px;
    box-shadow:0 2px 8px rgba(0,0,0,0.07); overflow:hidden;
    border:1.5px solid transparent;
  }}
  .card-高{{ border-color:#C0392B30; background:var(--high-bg); }}
  .card-中{{ border-color:#D6891030; background:var(--mid-bg); }}
  .card-低{{ border-color:#27AE6030; background:var(--low-bg); }}
  .card-header{{ padding:14px 18px 10px; border-bottom:1px solid rgba(0,0,0,0.06); }}
  .card-meta{{ display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin-bottom:6px; }}
  .imp-badge{{ font-size:12px; font-weight:700; }}
  .imp-高{{ color:var(--high); }} .imp-中{{ color:var(--mid); }} .imp-低{{ color:var(--low); }}
  .src-badge{{
    display:inline-block; padding:2px 8px; border-radius:4px;
    font-size:11px; font-weight:600; color:#fff; background:#4285F4;
  }}
  .card-title{{ font-size:15px; font-weight:700; color:#1a1a2e; text-decoration:none; line-height:1.5; display:block; }}
  .card-title:hover{{ color:var(--accent2); }}
  .card-body{{ padding:12px 18px 0; }}
  .sec-label{{ font-size:11px; font-weight:700; letter-spacing:0.5px; margin:0 0 4px; }}
  .sec-text{{ font-size:13px; line-height:1.75; color:#333; margin:0 0 10px; }}
  .card-tags{{ padding:0 18px 10px; display:flex; gap:6px; flex-wrap:wrap; }}
  .tag{{ font-size:11px; background:var(--tag-bg); color:var(--tag-text); border-radius:10px; padding:2px 8px; }}
  .card-footer{{ padding:8px 18px 14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }}
  .reason{{ font-size:12px; color:#666; font-style:italic; }}
  .read-more{{ font-size:12px; font-weight:600; text-decoration:none; white-space:nowrap; }}
  .site-footer{{ text-align:center; padding:20px; font-size:12px; color:#aaa; border-top:1px solid #e0e0e0; margin-top:8px; }}
</style>
</head>
<body>
<header class="site-header">
  <a class="back-link" href="../index.html">← 回週報首頁</a>
  <h1>🏍️ 台灣機車交通週報 {week_id}</h1>
  <p>{now.strftime('%Y 年 %m 月 %d 日')}，共 {len(articles)} 則新聞</p>
</header>
<main class="main">
{"".join(cards)}
</main>
<footer class="site-footer">由 GitHub Actions + Gemini AI 自動產生 · 每週一更新</footer>
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

    # 寫入 Supabase（失敗不中斷）
    _save_to_supabase(articles, week_id)

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