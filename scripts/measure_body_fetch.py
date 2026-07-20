"""正文抓取可行性測量（診斷用，唯讀）。

目的：回答「從 GitHub Actions 的 IP 抓新聞正文，會不會被大規模擋」——這是
spec 009 把全文抓取列 Out of Scope 時的疑慮，但當時沒有實測數字。

本腳本**不寫任何資料**：文章清單取自公開的 Worker API（免憑證），抓取結果只
印到 log。決定是否要把正文接進管線之前，先用真實環境的數字對照本地基準。

本地基準（2026-07-20，122 篇，家用 IP）：有真實網址者 84% 取得導言，
僅 2 個 403。若 Actions 上的數字接近，代表沒有技術障礙。

用法：python scripts/measure_body_fetch.py [week_id]
"""
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

API = "https://garyu-news-scraper.lukeking0325.workers.dev/api"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
WORKERS = 6
TIMEOUT = 15
# 導言夠長就停：測量的是「抓不抓得到」，不是要完整正文
LEDE_TARGET = 260
LEDE_MAX = 400
NOISE_RE = re.compile(r"(記者.{0,8}／|責任編輯|版權|訂閱|追蹤我們|延伸閱讀)")


def norm(s: str) -> str:
    return "".join(c for c in (s or "") if unicodedata.category(c)[0] in "LN")


def is_echo(title: str, summary: str) -> bool:
    """摘要只是複讀標題 → 這一列在 UI 上等同只有標題（同 pages/shared/app.js 判準）。"""
    nt, ns = norm(title), norm(summary)
    return len(ns) <= len(nt) + 24 and (nt in ns or ns in nt)


def extract_lede(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for bad in soup(["script", "style", "nav", "header", "footer", "aside", "figure"]):
        bad.decompose()
    node = soup.find("article")
    if not node:
        best, best_len = None, 0
        for div in soup.find_all(["div", "section", "main"]):
            ln = sum(len(p.get_text(strip=True)) for p in div.find_all("p", recursive=False))
            if ln > best_len:
                best, best_len = div, ln
        node = best
    if not node:
        return ""
    paras = []
    for p in node.find_all("p"):
        t = re.sub(r"\s+", " ", p.get_text(strip=True))
        if len(t) < 20 or NOISE_RE.search(t):
            continue
        paras.append(t)
        if sum(len(x) for x in paras) > LEDE_TARGET:
            break
    return " ".join(paras)[:LEDE_MAX]


def probe(article: dict) -> dict:
    link = article.get("link") or ""
    host = urlparse(link).netloc
    if "news.google.com" in host:
        return {"status": "gn_unresolved", "host": host, "article": article, "lede": ""}
    try:
        resp = requests.get(link, headers={"User-Agent": UA}, timeout=TIMEOUT)
    except Exception as e:
        return {"status": f"err:{type(e).__name__}", "host": host, "article": article, "lede": ""}
    if resp.status_code != 200:
        return {"status": f"http_{resp.status_code}", "host": host, "article": article, "lede": ""}
    try:
        lede = extract_lede(resp.text)
    except Exception as e:
        return {"status": f"parse_err:{type(e).__name__}", "host": host, "article": article, "lede": ""}
    return {"status": "ok" if lede else "no_lede", "host": host, "article": article, "lede": lede}


def main() -> int:
    week_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not week_id:
        weeks = requests.get(f"{API}/weeks?content_type=traffic", timeout=TIMEOUT).json()
        week_id = weeks[0]["week_id"]
    print(f"=== 正文抓取測量：{week_id} ===", flush=True)

    detail = requests.get(f"{API}/weeks/{week_id}?content_type=traffic", timeout=TIMEOUT).json()
    articles = detail.get("articles", [])
    if not articles:
        print("該週無文章，中止")
        return 1

    started = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(probe, articles))
    elapsed = time.time() - started

    n = len(results)
    print(f"\n樣本 {n} 篇，{WORKERS} 併發，耗時 {elapsed:.0f}s\n")

    print("抓取結果：")
    for status, count in Counter(r["status"] for r in results).most_common():
        print(f"  {status:24s} {count:3d}  = {100 * count / n:3.0f}%")

    resolved = [r for r in results if r["status"] != "gn_unresolved"]
    ok = [r for r in resolved if r["status"] == "ok"]
    print(f"\n有真實網址 {len(resolved)}/{n} 篇")
    if resolved:
        print(f"  → 成功取得導言 {len(ok)} = {100 * len(ok) / len(resolved):.0f}%  （本地基準 84%）")
    if ok:
        lens = sorted(len(r["lede"]) for r in ok)
        print(f"  → 導言長度中位數 {lens[len(lens) // 2]} 字")

    # 這才是重點：原本 UI 上只有標題的列，正文能不能救回來
    echo = [r for r in results
            if is_echo(r["article"]["title"],
                       (r["article"].get("analysis") or {}).get("summary")
                       or r["article"].get("summary") or "")]
    echo_real = [r for r in echo if r["status"] != "gn_unresolved"]
    echo_ok = [r for r in echo_real if r["status"] == "ok"]
    print(f"\n原本只複讀標題的 {len(echo)} 篇（其中有真實網址 {len(echo_real)} 篇）")
    if echo_real:
        print(f"  → 正文救回 {len(echo_ok)} = {100 * len(echo_ok) / len(echo_real):.0f}%  （本地基準 64%）")

    blocked = Counter(r["host"] for r in results
                      if r["status"].startswith("http_4") or r["status"].startswith("http_5")
                      or r["status"].startswith("err"))
    print(f"\n被擋／失敗的網域（本地基準：僅 3 個網域各 1 次）：")
    if not blocked:
        print("  無")
    for host, count in blocked.most_common():
        print(f"  {count:3d}  {host}")

    print("\n--- 導言樣本 ---")
    for r in echo_ok[:3] or ok[:3]:
        print(f"\n「{r['article']['title'][:44]}」\n  → {r['lede'][:160]}")

    print("\n（本腳本唯讀，未寫入任何資料）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
