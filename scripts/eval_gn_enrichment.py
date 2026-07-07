"""
eval_gn_enrichment.py
GN 充實驗收評分：對真實 feed 的活資料跑 src.gn_resolver.enrich_articles，
對照驗收基準打分。實作變更後重跑此腳本即可重新驗收。

基準（2026-07-07 與使用者議定）：
  1. 解碼成功率      ≥ 95%
  2. 充實摘要率      ≥ 70%（解碼成功者中 og:description ≥40 字且非標題複讀）
  3. 圖片取得率      ≥ 60%（解碼成功者中）
  4. 單篇平均延遲    ≤ 2.0s，p95 ≤ 5s（含 throttle）
  5. 優雅降級        0 未捕捉例外（整批跑完不炸）

用法：python3 scripts/eval_gn_enrichment.py [樣本數，預設 60]
"""
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import src.gn_resolver as gn

# 跨主題取樣：事故社會線、政策線、法規線各一（與 config/sources_traffic.yml 一致）
FEEDS = [
    ("GN 機車交通", "https://news.google.com/rss/search?q=%E6%A9%9F%E8%BB%8A+%E4%BA%A4%E9%80%9A&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
    ("GN 行人地獄", "https://news.google.com/rss/search?q=%E8%A1%8C%E4%BA%BA%E5%9C%B0%E7%8D%84&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
    ("GN 機車法規", "https://news.google.com/rss/search?q=%E6%A9%9F%E8%BB%8A+%E6%B3%95%E8%A6%8F+%E4%BA%A4%E9%80%9A%E9%83%A8&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
    ("GN 道安統計", "https://news.google.com/rss/search?q=%E9%81%93%E5%AE%89%20%E7%B5%B1%E8%A8%88&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"),
]


def sample_articles(n: int) -> list:
    import feedparser
    from src.collector import _entry_to_dict, _fetch_rss_bytes

    per_feed = max(1, n // len(FEEDS) + 1)
    articles, seen = [], set()
    for name, url in FEEDS:
        feed = feedparser.parse(_fetch_rss_bytes(url))
        entries = list(feed.entries)
        random.shuffle(entries)
        took = 0
        for e in entries:
            a = _entry_to_dict(e, name)
            if a["link"] in seen or not gn.is_gn_article_link(a["link"]):
                continue
            seen.add(a["link"])
            articles.append(a)
            took += 1
            if took >= per_feed:
                break
        print(f"  {name}: 取 {took} 篇（feed 共 {len(feed.entries)}）")
    return articles[:n]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    print(f"取樣 {len(FEEDS)} 個真實 feed、目標 {n} 篇…")
    articles = sample_articles(n)
    total = len(articles)
    print(f"共 {total} 篇不重複 GN 連結\n開始充實（含 throttle）…")

    latencies = []
    orig_enrich = gn.enrich_articles

    # 逐篇計時：包一層在單篇粒度呼叫
    stats = {"gn_total": 0, "resolved": 0, "summary_filled": 0,
             "image_filled": 0, "errors": 0}
    for i, a in enumerate(articles):
        t0 = time.time()
        s = orig_enrich([a])
        latencies.append(time.time() - t0)
        for k in stats:
            stats[k] += s[k]
        if (i + 1) % 10 == 0:
            print(f"  …{i + 1}/{total}")

    lat_sorted = sorted(latencies)
    mean = sum(latencies) / len(latencies)
    p95 = lat_sorted[max(0, int(len(lat_sorted) * 0.95) - 1)]

    resolved = stats["resolved"]
    decode_rate = resolved / total if total else 0
    summary_rate = stats["summary_filled"] / resolved if resolved else 0
    image_rate = stats["image_filled"] / resolved if resolved else 0

    checks = [
        ("1. 解碼成功率 ≥95%", f"{decode_rate:.0%} ({resolved}/{total})", decode_rate >= 0.95),
        ("2. 充實摘要率 ≥70%", f"{summary_rate:.0%} ({stats['summary_filled']}/{resolved})", summary_rate >= 0.70),
        ("3. 圖片取得率 ≥60%", f"{image_rate:.0%} ({stats['image_filled']}/{resolved})", image_rate >= 0.60),
        ("4. 延遲 mean≤2.0s / p95≤5s", f"mean={mean:.2f}s p95={p95:.2f}s", mean <= 2.0 and p95 <= 5.0),
        ("5. 優雅降級（跑完不炸）", f"errors={stats['errors']}（皆已捕捉）", True),
    ]

    print("\n════ 驗收評分 ════")
    all_pass = True
    for label, value, ok in checks:
        print(f"  {'✅' if ok else '❌'} {label:<28} {value}")
        all_pass &= ok
    print("════════════════")
    print("結果：" + ("全數通過 🎉" if all_pass else "未達標，需迭代"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
