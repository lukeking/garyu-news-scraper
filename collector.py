"""
collector.py
抓取多來源台灣機車交通新聞
來源由 sources.yml 設定，支援三種 type：rss、ptt、web
"""

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TrafficNewsBot/1.0; +mailto:lukeking0325@gmail.com)",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

PTT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.ptt.cc/bbs/index.html",
}

MOTORCYCLE_KEYWORDS = [
    "機車", "摩托車", "重機", "白牌", "紅牌", "黃牌",
    "gogoro", "電動機車", "考照", "機車路權",
    "機車事故", "騎士", "機車違規", "機車新制",
    "普通重型", "大型重型",
]

DAYS_BACK = 7
CUTOFF = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

SOURCES_FILE = os.path.join(os.path.dirname(__file__), "sources.yml")


# ── 設定載入 ──────────────────────────────────────────────────

def load_sources() -> list:
    if not os.path.exists(SOURCES_FILE):
        raise FileNotFoundError(
            f"找不到 {SOURCES_FILE}。"
            "請確認 GitHub Variable SOURCES_YML 有設定，"
            "且 weekly.yml 有寫入該檔案的步驟。"
        )
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    logger.info(f"載入 {len(sources)} 個啟用來源")
    return sources


# ── 共用工具 ──────────────────────────────────────────────────

def _is_recent(entry) -> bool:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt >= CUTOFF
            except Exception:
                pass
    return True


def _entry_to_dict(entry, source_name: str) -> dict:
    return {
        "title": entry.get("title", "").strip(),
        "link": entry.get("link", "").strip(),
        "summary": entry.get("summary", "").strip()[:500],
        "source": source_name,
        "published": entry.get("published", ""),
    }


def _fetch_rss_bytes(url: str) -> bytes:
    """用 requests 完整下載 RSS，再交給 feedparser 解析，避免 IncompleteRead。"""
    rss_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FeedFetcher/1.0)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Encoding": "gzip, deflate",
    }
    resp = requests.get(url, headers=rss_headers, timeout=20)
    resp.raise_for_status()
    return resp.content


# ── 各 type 抓取函式 ──────────────────────────────────────────

def _fetch_rss(source: dict) -> list:
    name = source["name"]
    url = source["url"]
    articles = []
    try:
        raw = _fetch_rss_bytes(url)
        feed = feedparser.parse(raw)
        for entry in feed.entries:
            if not _is_recent(entry):
                continue
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            # Google News 來源不需要二次過濾（query 已鎖定主題）
            # 其他新聞網 RSS 需要關鍵字過濾
            is_google_news = "news.google.com" in url
            text = (title + summary).lower()
            if is_google_news or any(kw in text for kw in MOTORCYCLE_KEYWORDS):
                articles.append(_entry_to_dict(entry, name))
        logger.info(f"{name}: {len(articles)} 筆")
    except Exception as e:
        logger.warning(f"{name} 失敗: {e}")
    return articles


def _fetch_ptt(source: dict) -> list:
    name = source["name"]
    board = source["board"]
    min_pushes = source.get("min_pushes", 5)
    articles = []
    url = f"https://www.ptt.cc/bbs/{board}/index.html"
    try:
        session = requests.Session()
        session.cookies.set("over18", "1", domain="www.ptt.cc")
        resp = session.get(url, headers=PTT_HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for div in soup.select("div.r-ent"):
            title_tag = div.select_one("div.title a")
            if not title_tag:
                continue
            title = title_tag.text.strip()
            link = "https://www.ptt.cc" + title_tag["href"]
            push_tag = div.select_one("div.nrec span")
            push_count = 0
            if push_tag:
                try:
                    push_count = int(push_tag.text.strip())
                except ValueError:
                    push_count = 10 if push_tag.text.strip() == "爆" else 0
            if push_count >= min_pushes:
                articles.append({
                    "title": title,
                    "link": link,
                    "summary": f"PTT {board} 推文數：{push_count}",
                    "source": name,
                    "published": "",
                })
        logger.info(f"{name}: {len(articles)} 筆熱門文章")
    except Exception as e:
        logger.warning(f"{name} 失敗: {e}")
    return articles


def _fetch_web(source: dict) -> list:
    name = source["name"]
    url = source["url"]
    max_items = source.get("max_items", 10)
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        count = 0
        for a in soup.select("a[href]"):
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue
            if any(kw in title for kw in MOTORCYCLE_KEYWORDS):
                href = a["href"]
                if href.startswith("/"):
                    base = "/".join(url.split("/")[:3])
                    href = base + href
                articles.append({
                    "title": title,
                    "link": href,
                    "summary": f"{name} 官方公告",
                    "source": name,
                    "published": "",
                })
                count += 1
                if count >= max_items:
                    break
        logger.info(f"{name}: {len(articles)} 筆公告")
    except Exception as e:
        logger.warning(f"{name} 失敗: {e}")
    return articles


# ── 主入口 ────────────────────────────────────────────────────

FETCHERS = {
    "rss": _fetch_rss,
    "ptt": _fetch_ptt,
    "web": _fetch_web,
}

def collect_all() -> list:
    logger.info("=== 開始收集新聞 ===")
    sources = load_sources()
    all_articles = []

    for source in sources:
        stype = source.get("type", "")
        fetcher = FETCHERS.get(stype)
        if not fetcher:
            logger.warning(f"未知的 type: {stype}（來源：{source.get('name')}），跳過")
            continue
        articles = fetcher(source)
        all_articles.extend(articles)
        time.sleep(1)

    logger.info(f"=== 收集完成，共 {len(all_articles)} 筆（去重前）===")
    return all_articles