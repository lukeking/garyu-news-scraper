"""Scout the live buffer for substantive/policy clusters (read-only)."""
import os, sys, re
from collections import Counter
REPO = "/home/luke/Projects/garyu-news-scraper"
sys.path.insert(0, REPO)
from dotenv import load_dotenv
load_dotenv(os.path.join(REPO, ".env"), override=True)
import logging; logging.basicConfig(level=logging.ERROR)
from src.pipeline_config import load_pipeline_config
from src.storage import get_traffic_buffer
from src.analyzer import cluster_traffic_articles, score_topic_buckets, topic_token_signature

POLICY = {"科技執法", "路權政策", "交通工程", "道安政策"}
SUBSTANTIVE = POLICY | {"行人事故", "路口安全", "大型車安全", "酒駕", "道路施工"}
# policy/opinion language that the accident taxonomy misses
POLICY_KW = re.compile(r"左轉|待轉|路權|還路|禁行|兩段|測速|區間|執法|檢舉|道安|願景|"
                       r"行人|斑馬線|人行道|Vision|願景|政策|試辦|開放|條例|處罰|盲區|死角")

cfg = load_pipeline_config()
arts = get_traffic_buffer(cfg.get("buffer", {}).get("max_age_weeks", 8))
buckets = cluster_traffic_articles(arts, cfg)
scores = score_topic_buckets(buckets, cfg)

def cat(b): return (b[0].get("major_category") or "uncategorised") if b else "?"

print(f"buffer={len(arts)}  buckets={len(buckets)}\n")

print("=== 文章數 by major_category ===")
c = Counter((a.get("major_category") or "uncategorised") for a in arts)
for k, v in c.most_common():
    print(f"  {k}: {v}")

print("\n=== 最大的 12 個 bucket（不分類別）===")
for bid, b in sorted(buckets.items(), key=lambda x: -len(x[1]))[:12]:
    sig = topic_token_signature(b)
    print(f"  {bid} [{cat(b)}] n={len(b)} score={scores[bid]:.2f} sig={sig[:4]}")
    print(f"      e.g. {b[0].get('title','')[:42]}")

print("\n=== policy/substantive 類別的 bucket（n>=2, 依 n 排序）===")
cand = [(bid, b) for bid, b in buckets.items()
        if cat(b) in SUBSTANTIVE and len(b) >= 2]
for bid, b in sorted(cand, key=lambda x: -len(x[1]))[:15]:
    sig = topic_token_signature(b)
    print(f"  {bid} [{cat(b)}] n={len(b)} score={scores[bid]:.2f} sig={sig[:4]}")
    for a in b[:3]:
        print(f"      - {a.get('title','')[:46]}")

print("\n=== 含政策語言的 bucket（不論類別標籤, n>=3, 依 n 排序）===")
polib = []
for bid, b in buckets.items():
    hits = sum(1 for a in b if POLICY_KW.search(a.get("title", "")))
    if len(b) >= 3 and hits >= 2:
        polib.append((bid, b, hits))
for bid, b, hits in sorted(polib, key=lambda x: -len(x[1]))[:12]:
    sig = topic_token_signature(b)
    print(f"  {bid} [{cat(b)}] n={len(b)} 政策詞命中={hits} score={scores[bid]:.2f} sig={sig[:4]}")
    for a in b[:4]:
        print(f"      - {a.get('title','')[:48]}")
