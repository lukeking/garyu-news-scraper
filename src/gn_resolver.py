"""
gn_resolver.py
Google News RSS 連結還原與內容充實。

Google News 的 RSS <link> 是 news.google.com/rss/articles/<id> 轉址頁，
2024 年中後 id 不再內嵌原始 URL（base64 直解已失效），需要：
  1. GET 轉址頁，取出 c-wiz 節點的 data-n-a-{id,ts,sg} 三個參數
  2. POST 內部 API /_/DotsSplashUi/data/batchexecute（garturlreq）換回原始 URL
這是無文件的內部 API，Google 改版即斷；斷掉時 per-item fail-soft，
文章保持原樣（GN 連結＋標題式摘要），等同回到未充實前的現狀。

還原後順路抓 publisher 頁的 og:description / og:image 充實 summary 與 image。
"""

import json
import logging
import re
import time
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# GN 轉址頁對非瀏覽器 UA 可能不回 decode 參數，比照 collector 的 PTT_HEADERS 用瀏覽器 UA
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}

_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_GN_LINK_RE = re.compile(r"^https?://news\.google\.com/(?:rss/)?articles/")
_PARAM_RES = {
    "id": re.compile(r'data-n-a-id="([^"]+)"'),
    "ts": re.compile(r'data-n-a-ts="([^"]+)"'),
    "sg": re.compile(r'data-n-a-sg="([^"]+)"'),
}

_TIMEOUT = (5, 10)  # (connect, read)
_MIN_SUMMARY_LEN = 40  # og:description 短於此視為無充實價值


def is_gn_article_link(url: str) -> bool:
    return bool(_GN_LINK_RE.match(url or ""))


def _parse_batch_response(text: str):
    """batchexecute 回應是 )]}' 開頭的多行 chunk；找 Fbv4je 那行取出原始 URL。"""
    for line in text.splitlines():
        if "Fbv4je" not in line:
            continue
        try:
            outer = json.loads(line)
            payload = json.loads(outer[0][2])
            url = payload[1]
        except (ValueError, IndexError, TypeError, KeyError):
            return None
        if isinstance(url, str) and url.startswith("http") and "news.google.com" not in url:
            return url
    return None


def resolve_gn_link(session: requests.Session, link: str) -> str | None:
    """GN 轉址連結 → publisher 原始 URL；任何一步失敗回 None。"""
    resp = session.get(link, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    params = {}
    for key, pat in _PARAM_RES.items():
        m = pat.search(resp.text)
        if not m:
            logger.debug("GN decode 參數 %s 缺失：%s", key, link[:80])
            return None
        params[key] = m.group(1)

    inner = json.dumps([
        "garturlreq",
        [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None,
          None, None, None, 0, 1], "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
        params["id"], int(params["ts"]), params["sg"],
    ], separators=(",", ":"))
    freq = json.dumps([[["Fbv4je", inner, None, "generic"]]], separators=(",", ":"))
    resp = session.post(
        _BATCH_URL,
        data={"f.req": freq},
        headers={**_HEADERS,
                 "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return _parse_batch_response(resp.text)


def fetch_og_meta(session: requests.Session, url: str) -> tuple[str, str]:
    """publisher 頁的 (og:description, og:image)；抓不到的欄位回空字串。"""
    resp = session.get(url, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content[:400_000], "html.parser")

    def og(prop: str) -> str:
        tag = (soup.find("meta", attrs={"property": prop})
               or soup.find("meta", attrs={"name": prop}))
        return (tag.get("content") or "").strip() if tag else ""

    return og("og:description"), og("og:image")


def _record_error_domain(stats: dict, domain: str, status) -> None:
    """Record a failing domain→HTTP status, preferring a real status over None so a
    later transient error (no .response) can't clobber an earlier 403 for the same
    publisher. Set membership (which domains failed) is preserved either way — this
    is the block-list-expansion signal the daily runner watches. See specs/BACKLOG.md.
    """
    if stats["error_domains"].get(domain) is None:
        stats["error_domains"][domain] = status


def enrich_articles(articles: list, throttle: float = 0.4) -> dict:
    """就地充實 GN 來源的文章：link 換成 publisher URL、summary 換成
    og:description（僅當 ≥_MIN_SUMMARY_LEN 字且非標題複讀）、image 補 og:image。
    非 GN 連結不動。單篇任何失敗只記 log、保留原欄位。

    回傳統計 dict（gn_total/resolved/summary_filled/image_filled/errors），
    供 pipeline log 與 eval harness 共用。
    """
    stats = {"gn_total": 0, "resolved": 0, "summary_filled": 0,
             "image_filled": 0, "errors": 0, "error_domains": {}}
    session = requests.Session()
    for a in articles:
        link = (a.get("link") or "").strip()
        if not is_gn_article_link(link):
            continue
        stats["gn_total"] += 1
        real_url = ""
        try:
            real_url = resolve_gn_link(session, link)
            if not real_url:
                stats["errors"] += 1
                # Non-exception resolve failure = GN decode/API breakage, not a
                # publisher block. Record it under the GN domain so a total resolve
                # outage surfaces in 失敗網域 rather than an empty list that would
                # read as "nothing blocked". See specs/BACKLOG.md.
                _record_error_domain(stats, urlparse(link).netloc, None)
                continue
            a["link"] = real_url
            stats["resolved"] += 1

            desc, image = fetch_og_meta(session, real_url)
            title = (a.get("title") or "").strip()
            if len(desc) >= _MIN_SUMMARY_LEN and desc != title:
                a["summary"] = desc
                stats["summary_filled"] += 1
            if image.startswith("http") and not (a.get("image") or "").strip():
                a["image"] = image
                stats["image_filled"] += 1
        except Exception as e:
            stats["errors"] += 1
            # Record the *publisher* domain (not the news.google.com link) and the
            # HTTP status. When the daily runner hits these domains 7x/week, this is
            # the only way to see WHICH domain blocks us — the block-list expanding
            # into native media (ltn/cna/udn/chinatimes) is the reopen trigger for
            # the body-fetch decision. See specs/BACKLOG.md.
            domain = urlparse(real_url).netloc or urlparse(link).netloc
            status = getattr(getattr(e, "response", None), "status_code", None)
            _record_error_domain(stats, domain, status)
            logger.warning("GN 充實失敗（保留原欄位）：domain=%s status=%s：%s",
                           domain, status, e)
        finally:
            time.sleep(throttle)

    if stats["gn_total"]:
        blocked = (f"（失敗網域：{', '.join(sorted(stats['error_domains']))}）"
                   if stats["error_domains"] else "")
        logger.info(
            "GN 充實：%d 篇中 %d 還原連結、%d 補摘要、%d 補圖、%d 失敗%s",
            stats["gn_total"], stats["resolved"], stats["summary_filled"],
            stats["image_filled"], stats["errors"], blocked,
        )
    return stats
