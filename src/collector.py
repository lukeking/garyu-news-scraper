"""
collector.py
抓取多來源新聞：台灣機車交通（traffic）和 FFXIV 遊戲資訊（ffxiv）
來源分別由 config/sources_traffic.yml 和 config/sources_ffxiv.yml 設定。
支援的 type：rss、ptt、web、html_patch、html_forum
"""

import re
import calendar
import feedparser
import requests
import yaml
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin
import time
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GaryuNewsBot/1.0; +mailto:lukeking0325@gmail.com)",
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

_CONFIG_DIR = os.path.join(os.path.dirname(__file__), "..", "config")
SOURCES_FILE = os.path.join(_CONFIG_DIR, "sources_traffic.yml")
FFXIV_SOURCES_FILE = os.path.join(_CONFIG_DIR, "sources_ffxiv.yml")

_THREAD_HREF_PATTERN = re.compile(r"threads/\d+")


# ── 設定載入 ──────────────────────────────────────────────────

def load_sources() -> list:
    if not os.path.exists(SOURCES_FILE):
        raise FileNotFoundError(
            f"找不到 {SOURCES_FILE}。"
            "請確認 GitHub Variable SOURCES_TRAFFIC_YML 有設定，"
            "且 weekly.yml 有寫入該檔案的步驟。"
        )
    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    logger.info("載入 %d 個啟用交通來源", len(sources))
    return sources


def load_ffxiv_sources() -> list:
    """
    載入 FFXIV 來源設定。
    優先讀 config/sources_ffxiv.yml；若檔案不存在但 SOURCES_FFXIV_YML 環境變數有值，
    則先寫入檔案再載入。兩者皆無時回傳空列表（不中斷流程）。
    """
    env_content = os.environ.get("SOURCES_FFXIV_YML", "").strip()
    if env_content and not os.path.exists(FFXIV_SOURCES_FILE):
        try:
            os.makedirs(os.path.dirname(FFXIV_SOURCES_FILE), exist_ok=True)
            with open(FFXIV_SOURCES_FILE, "w", encoding="utf-8") as f:
                f.write(env_content)
            logger.info("SOURCES_FFXIV_YML 已寫入 %s", FFXIV_SOURCES_FILE)
        except OSError as e:
            logger.warning("無法寫入 %s：%s", FFXIV_SOURCES_FILE, e)

    if not os.path.exists(FFXIV_SOURCES_FILE):
        logger.warning("找不到 FFXIV 來源設定（%s），略過 FFXIV 收集", FFXIV_SOURCES_FILE)
        return []

    with open(FFXIV_SOURCES_FILE, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    sources = [s for s in config.get("sources", []) if s.get("enabled", True)]
    logger.info("載入 %d 個啟用 FFXIV 來源", len(sources))
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
    return False


def _entry_to_dict(entry, source_name: str, content_type: str = "traffic") -> dict:
    pub = ""
    if entry.get("published_parsed"):
        ts = calendar.timegm(entry["published_parsed"])
        pub = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    elif entry.get("published"):
        pub = entry["published"]
    return {
        "title": entry.get("title", "").strip(),
        "link": entry.get("link", "").strip(),
        "summary": entry.get("summary", "").strip()[:500],
        "source": source_name,
        "published": pub,
        "content_type": content_type,
    }


def _fetch_rss_bytes(url: str) -> bytes:
    """用 requests 完整下載 RSS，再交給 feedparser 解析，避免 IncompleteRead。
    遇到 429 時依 Retry-After（或指數退避）重試，最多 3 次。"""
    rss_headers = {
        "User-Agent": "GaryuNewsBot/1.0 (+mailto:lukeking0325@gmail.com)",
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
        "Accept-Encoding": "gzip, deflate",
    }
    for attempt in range(3):
        resp = requests.get(url, headers=rss_headers, timeout=20)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** (attempt + 2)))
            logger.warning("429 from %s，%d 秒後重試（第 %d 次）", url, wait, attempt + 1)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.content
    resp.raise_for_status()
    return resp.content


def _abs_url(href: str, base_url: str) -> str:
    """將相對路徑轉為絕對 URL。"""
    return urljoin(base_url, href)


# ── YouTube ヘルパー ──────────────────────────────────────────

def _parse_iso8601_duration(duration: str) -> int:
    """Parse an ISO 8601 duration string (e.g. 'PT1M30S') and return total seconds."""
    import re as _re
    m = _re.match(
        r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?",
        duration or "",
    )
    if not m:
        return 0
    days, hours, minutes, seconds = (int(v or 0) for v in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _build_youtube_client():
    """Return a YouTube Data API v3 resource, or None if the key is missing."""
    api_key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not api_key:
        logger.error("[youtube] YOUTUBE_API_KEY 未設定，略過所有 YouTube 來源")
        return None
    try:
        from googleapiclient.discovery import build
        return build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    except Exception as e:
        logger.error("[youtube] 無法建立 API 客戶端：%s", e)
        return None


# ── 各 type 抓取函式 ──────────────────────────────────────────

def _fetch_rss(source: dict) -> list:
    name = source["name"]
    url = source["url"]
    content_type = source.get("content_type", "traffic")
    articles = []
    try:
        raw = _fetch_rss_bytes(url)
        feed = feedparser.parse(raw)
        for entry in feed.entries:
            if content_type == "traffic" and not _is_recent(entry):
                continue
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            is_google_news = "news.google.com" in url
            text = (title + summary).lower()
            if content_type == "ffxiv" or is_google_news or any(kw in text for kw in MOTORCYCLE_KEYWORDS):
                articles.append(_entry_to_dict(entry, name, content_type))
        logger.info("%s: %d 筆", name, len(articles))
    except Exception as e:
        logger.warning("%s 失敗: %s", name, e)
    return articles


def _fetch_ptt(source: dict) -> list:
    name = source["name"]
    board = source["board"]
    min_pushes = source.get("min_pushes", 5)
    content_type = source.get("content_type", "traffic")
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
                    "content_type": content_type,
                })
        logger.info("%s: %d 筆熱門文章", name, len(articles))
    except Exception as e:
        logger.warning("%s 失敗: %s", name, e)
    return articles


def _fetch_web(source: dict) -> list:
    name = source["name"]
    url = source["url"]
    max_items = source.get("max_items", 10)
    content_type = source.get("content_type", "traffic")
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
                href = _abs_url(a["href"], url)
                articles.append({
                    "title": title,
                    "link": href,
                    "summary": f"{name} 官方公告",
                    "source": name,
                    "published": "",
                    "content_type": content_type,
                })
                count += 1
                if count >= max_items:
                    break
        logger.info("%s: %d 筆公告", name, len(articles))
    except Exception as e:
        logger.warning("%s 失敗: %s", name, e)
    return articles


def _fetch_html_patch(source: dict) -> list:
    """
    抓取 Lodestone 風格的靜態新聞列表頁面。
    使用 source["selector"] CSS selector 定位每則新聞的外層容器，
    再用 title_selector 取標題文字，並跟蹤第一個 <a> 取連結。
    """
    name = source["name"]
    url = source["url"]
    selector = source.get("selector", "a")
    title_selector = source.get("title_selector", "a")
    max_items = source.get("max_items", 10)
    content_type = source.get("content_type", "ffxiv")
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for item in soup.select(selector):
            title_el = item.select_one(title_selector) or item.select_one("a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if len(title) < 3:
                continue
            link_el = item.select_one("a") or title_el
            href = link_el.get("href", "") if link_el else ""
            href = _abs_url(href, url)
            articles.append({
                "title": title,
                "link": href,
                "summary": "",
                "source": name,
                "published": "",
                "content_type": content_type,
            })
            if len(articles) >= max_items:
                break
        logger.info("%s: %d 筆", name, len(articles))
    except Exception as e:
        logger.warning("%s 失敗: %s", name, e)
    return articles


def _fetch_html_forum(source: dict) -> list:
    """
    抓取 vBulletin 討論板的帖子列表（僅標題+連結）。
    完整內文需登入，因此摘要固定設為 "[JP Forum] {標題}"。
    自動過濾不符合 threads/[ID]-[SLUG] 格式的連結。
    """
    name = source["name"]
    url = source["url"]
    max_items = source.get("max_items", 15)
    content_type = source.get("content_type", "ffxiv")
    articles = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        seen_links: set = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not _THREAD_HREF_PATTERN.search(href):
                continue
            title = a.get_text(strip=True)
            if len(title) < 3:
                continue
            href = _abs_url(href, url)
            base_href = href.split("?")[0].split("#")[0]
            if base_href in seen_links:
                continue
            seen_links.add(base_href)
            articles.append({
                "title": title,
                "link": href,
                "summary": f"[JP Forum] {title}",
                "source": name,
                "published": "",
                "content_type": content_type,
            })
            if len(articles) >= max_items:
                break
        logger.info("%s: %d 筆討論串", name, len(articles))
    except Exception as e:
        logger.warning("%s 失敗: %s", name, e)
    return articles


def _fetch_youtube(source: dict) -> list:
    """Fetch recent uploads from a YouTube channel and return article dicts."""
    name = source["name"]
    channel_id = source.get("channel_id", "")
    max_items = source.get("max_items", 5)
    lookback_days = source.get("lookback_days", 2)

    if not channel_id:
        logger.warning("[youtube] %s: channel_id 未設定，略過", name)
        return []

    youtube = _build_youtube_client()
    if youtube is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    articles = []

    try:
        from googleapiclient.errors import HttpError

        # Uploads playlist ID = "UU" + channel_id[2:]
        playlist_id = "UU" + channel_id[2:]

        # Step 1: fetch playlist items (1 quota unit)
        pl_resp = (
            youtube.playlistItems()
            .list(playlistId=playlist_id, part="snippet", maxResults=max_items)
            .execute()
        )
        items = pl_resp.get("items", [])

        # Filter by publish date and collect video IDs
        video_ids = []
        for item in items:
            published_str = item["snippet"].get("publishedAt", "")
            try:
                pub_dt = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except Exception:
                continue
            if pub_dt < cutoff:
                continue
            vid = item["snippet"]["resourceId"]["videoId"]
            video_ids.append(vid)

        if not video_ids:
            logger.info("[youtube] %s: lookback_days=%d 內無新影片", name, lookback_days)
            return []

        # Step 2: fetch duration + snippet for each video (1 unit per call)
        vids_resp = (
            youtube.videos()
            .list(id=",".join(video_ids), part="contentDetails,snippet")
            .execute()
        )

        for item in vids_resp.get("items", []):
            video_id = item["id"]
            snippet = item["snippet"]
            duration_str = item["contentDetails"].get("duration", "PT0S")

            # Skip Shorts (≤ 60 seconds)
            if _parse_iso8601_duration(duration_str) <= 60:
                logger.debug("[youtube] 略過 Short：%s", snippet.get("title", ""))
                continue

            title = snippet.get("title", "").strip()
            description = snippet.get("description", "").strip()
            published_at = snippet.get("publishedAt", "")
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            # Step 3: attempt transcript extraction; fall back to title + description
            try:
                from youtube_transcript_api import YouTubeTranscriptApi
                segments = YouTubeTranscriptApi.get_transcript(
                    video_id, languages=["zh-TW", "zh", "en", "ja"]
                )
                transcript = " ".join(s["text"] for s in segments)[:4000]
                summary = transcript
            except Exception as e:
                logger.warning(
                    "[youtube] 逐字稿取得失敗，使用標題+描述：%s（%s）", title, e
                )
                summary = title + "\n" + description[:500]

            articles.append({
                "title": title,
                "link": video_url,
                "summary": summary,
                "source": name,
                "published": published_at,
                "content_type": "traffic",
                "source_type": "youtube",
            })

        logger.info("[youtube] %s: %d 筆", name, len(articles))

    except Exception as e:
        try:
            from googleapiclient.errors import HttpError as _HttpError
            if isinstance(e, _HttpError) and e.status_code in (403, 429):
                logger.error("[youtube] %s: API 配額已耗盡（%s），略過此來源", name, e.status_code)
                return []
        except ImportError:
            pass
        logger.warning("[youtube] %s 失敗：%s", name, e)

    return articles


# ── 主入口 ────────────────────────────────────────────────────

FETCHERS = {
    "rss": _fetch_rss,
    "ptt": _fetch_ptt,
    "web": _fetch_web,
    "html_patch": _fetch_html_patch,
    "html_forum": _fetch_html_forum,
    "youtube": _fetch_youtube,
}


def collect_sources(sources: list) -> list:
    all_articles = []
    for source in sources:
        stype = source.get("type", "")
        fetcher = FETCHERS.get(stype)
        if not fetcher:
            logger.warning("未知的 type: %s（來源：%s），跳過", stype, source.get("name"))
            continue
        articles = fetcher(source)
        all_articles.extend(articles)
        time.sleep(1)
    logger.info("收集完成，共 %d 筆（去重前）", len(all_articles))
    return all_articles
