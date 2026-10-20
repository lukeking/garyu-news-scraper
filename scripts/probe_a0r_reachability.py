"""GNS-20261019-a0r 的可達性探針：論壇 lastpost RSS、討論串頁面、Lodestone category/3。
唯讀、免憑證，結果只印到 log。用法：python scripts/probe_a0r_reachability.py"""
import os
import re
import sys
import time

import feedparser
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.collector import HEADERS, _fetch_html_patch, _fetch_rss_bytes

FORUM_RSS = "https://forum.square-enix.com/ffxiv/external.php?type=RSS2&forumids={}&lastpost=1"
FORUMS = {"537": "PLL", "550": "TANK", "551": "DPS", "552": "HEALER", "553": "その他バトルシステム"}
THREAD_FROM = ("553", "551")
LODESTONE = {
    "name": "Lodestone category/3",
    "url": "https://jp.finalfantasyxiv.com/lodestone/news/category/3",
    "selector": "li.news__list",
    "title_selector": "p.news__list--title",
    "max_items": 30,
}
PAUSE = 1.0


def squash(html: str) -> str:
    return re.sub(r"\s+", "", BeautifulSoup(html, "lxml").get_text())


def stamp(entry) -> str:
    t = entry.get("published_parsed")
    return time.strftime("%Y-%m-%d %H:%M", t) if t else "-"


def probe_rss(fid: str):
    try:
        feed = feedparser.parse(_fetch_rss_bytes(FORUM_RSS.format(fid)))
    except Exception as e:
        print(f"[rss] {fid} {FORUMS[fid]} FAIL {type(e).__name__}: {e}")
        return False, None
    entries = feed.entries
    full = sum(1 for e in entries if e.get("content"))
    times = sorted(stamp(e) for e in entries)
    span = f"{times[0]}～{times[-1]}" if times else "-"
    print(f"[rss] {fid} {FORUMS[fid]} ok items={len(entries)} content_encoded={full} pubDate={span}")
    return True, (entries[0] if entries else None)


def probe_thread(fid: str, entry) -> bool:
    link = entry.get("link", "")
    try:
        resp = requests.get(link, headers=HEADERS, timeout=15)
    except Exception as e:
        print(f"[thread] {fid} FAIL {type(e).__name__}: {e} link={link}")
        return False
    posts = BeautifulSoup(resp.text, "lxml").select('[id^="post_message_"]')
    snippet = squash(entry.content[0].value)[:40] if entry.get("content") else ""
    found = bool(snippet) and snippet in squash(resp.text)
    print(f"[thread] {fid} status={resp.status_code} link={link} final={resp.url} "
          f"posts={len(posts)} rss_text_found={found}")
    return resp.ok and found


def main() -> None:
    rss_ok, firsts = 0, {}
    for fid in FORUMS:
        ok, first = probe_rss(fid)
        rss_ok += ok
        firsts[fid] = first
        time.sleep(PAUSE)

    thread_ok = 0
    for fid in THREAD_FROM:
        if firsts.get(fid) is None:
            print(f"[thread] {fid} 略過：RSS 沒有可用的第一串")
            continue
        thread_ok += probe_thread(fid, firsts[fid])
        time.sleep(PAUSE)

    items = _fetch_html_patch(LODESTONE)
    first_title = items[0]["title"] if items else "-"
    print(f"[lodestone] category/3 items={len(items)} first={first_title}")

    print(f"[probe] done: rss ok {rss_ok}/{len(FORUMS)}, thread text found {thread_ok}/{len(THREAD_FROM)}, "
          f"lodestone {len(items)} 筆")


if __name__ == "__main__":
    main()
