"""
collector.py
抓取多來源台灣機車交通新聞
來源：Google News RSS、PTT 機車板/重機板、主流新聞網 RSS、交通部公告
"""

import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TrafficNewsBot/1.0)",
    "Accept-Language": "zh-TW,zh;q=0.9",
}

# 只收集最近 7 天的新聞
DAYS_BACK = 7
CUTOFF = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)


def _is_recent(entry) -> bool:
    """檢查文章是否在時間範圍內"""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                dt = datetime(*t[:6], tzinfo=timezone.utc)
                return dt >= CUTOFF
            except Exception:
                pass
    return True  # 無法判斷時間就保留


def _entry_to_dict(entry, source: str) -> dict:
    return {
        "title": entry.get("title", "").strip(),
        "link": entry.get("link", "").strip(),
        "summary": entry.get("summary", "").strip()[:500],
        "source": source,
        "published": entry.get("published", ""),
    }


# ── 1. Google News RSS ─────────────────────────────────────────────────────────

GOOGLE_NEWS_QUERIES = [
    "機車 交通",
    "重機 台灣",
    "白牌機車",
    "紅牌 黃牌 機車",
    "機車 事故 台灣",
    "機車 法規 交通部",
    "Gogoro 電動機車",
    "機車 路權",
]

def fetch_google_news() -> list:
    articles = []
    for query in GOOGLE_NEWS_QUERIES:
        url = (
            f"https://news.google.com/rss/search"
            f"?q={requests.utils.quote(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        )
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                if _is_recent(entry):
                    articles.append(_entry_to_dict(entry, "Google News"))
            logger.info(f"Google News [{query}]: {len(feed.entries)} 筆")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Google News [{query}] 失敗: {e}")
    return articles


# ── 2. PTT 機車板 / 重機板 ────────────────────────────────────────────────────

PTT_BOARDS = ["biker", "注意:機車版已搬移至 car-moto，請改訂閱 car-moto"]
PTT_BOARDS = ["biker", "car-moto"]

def _fetch_ptt_board(board: str) -> list:
    articles = []
    url = f"https://www.ptt.cc/bbs/{board}/index.html"
    try:
        resp = requests.get(url, headers={**HEADERS, "Cookie": "over18=1"}, timeout=10)
        soup = BeautifulSoup(resp.text, "lxml")
        for div in soup.select("div.r-ent"):
            title_tag = div.select_one("div.title a")
            if not title_tag:
                continue
            title = title_tag.text.strip()
            link = "https://www.ptt.cc" + title_tag["href"]
            # 推文數
            push_tag = div.select_one("div.nrec span")
            push_count = 0
            if push_tag:
                try:
                    push_count = int(push_tag.text.strip())
                except ValueError:
                    push_count = 10 if push_tag.text.strip() == "爆" else 0
            # 只收推文數 >= 5 的文章
            if push_count >= 5:
                articles.append({
                    "title": title,
                    "link": link,
                    "summary": f"PTT {board} 推文數：{push_count}",
                    "source": f"PTT/{board}",
                    "published": "",
                })
        logger.info(f"PTT/{board}: {len(articles)} 筆熱門文章")
    except Exception as e:
        logger.warning(f"PTT/{board} 失敗: {e}")
    return articles

def fetch_ptt() -> list:
    articles = []
    for board in PTT_BOARDS:
        articles.extend(_fetch_ptt_board(board))
        time.sleep(1)
    return articles


# ── 3. 主流新聞網 RSS ──────────────────────────────────────────────────────────

NEWS_RSS_FEEDS = [
    ("聯合新聞網", "https://udn.com/rssfeed/news/2/0?ch=news"),
    ("中時新聞網", "https://www.chinatimes.com/rss/real_time.xml"),
    ("自由時報",   "https://news.ltn.com.tw/rss/all.xml"),
    ("TVBS新聞",   "https://news.tvbs.com.tw/rss/news"),
    ("ETtoday",    "https://feeds.feedburner.com/ettoday/realtime"),
]

MOTORCYCLE_KEYWORDS = [
    "機車", "摩托車", "重機", "白牌", "紅牌", "黃牌",
    "gogoro", "電動機車", "考照", "機車路權",
    "機車事故", "騎士", "機車違規", "機車新制",
    "普通重型", "大型重型",
]

def fetch_news_rss() -> list:
    articles = []
    for name, url in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            count = 0
            for entry in feed.entries:
                if not _is_recent(entry):
                    continue
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                text = (title + summary).lower()
                if any(kw in text for kw in MOTORCYCLE_KEYWORDS):
                    articles.append(_entry_to_dict(entry, name))
                    count += 1
            logger.info(f"{name} RSS: {count} 筆相關文章")
            time.sleep(0.5)
        except Exception as e:
            logger.warning(f"{name} RSS 失敗: {e}")
    return articles


# ── 4. 交通部 / 公路局公告 ────────────────────────────────────────────────────

MOT_URLS = [
    ("交通部", "https://www.motc.gov.tw/ch/home.jsp?id=14&parentpath=0,2"),
    ("公路局", "https://www.thb.gov.tw/sites/ch/modules/news/news_list?Type=2"),
]

def fetch_mot_announcements() -> list:
    articles = []
    for name, url in MOT_URLS:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "lxml")
            # 嘗試找各種新聞連結格式
            links = soup.select("a[href]")
            count = 0
            for a in links:
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
                    if count >= 10:
                        break
            logger.info(f"{name}: {count} 筆公告")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"{name} 失敗: {e}")
    return articles


# ── 主入口 ────────────────────────────────────────────────────────────────────

def collect_all() -> list:
    logger.info("=== 開始收集新聞 ===")
    all_articles = []
    all_articles.extend(fetch_google_news())
    all_articles.extend(fetch_ptt())
    all_articles.extend(fetch_news_rss())
    all_articles.extend(fetch_mot_announcements())
    logger.info(f"=== 收集完成，共 {len(all_articles)} 筆（去重前）===")
    return all_articles