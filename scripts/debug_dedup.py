"""
Debug script for dedup_same_event — run with real or synthetic articles
to inspect what Gemini decides and why.

Usage:
    python scripts/debug_dedup.py

Set GEMINI_API_KEY in .env or environment before running.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from src.analyzer import dedup_same_event

# ── Edit these to test different scenarios ────────────────────────────────────

candidates = [
    {
        "title": "淡江大橋通車首日！騎士不滿機車道過窄竟橫躺攔路 涉公共危險罪送辦",
        "summary": "淡水往八里方向，一名機車騎士在淡江大橋機車道上橫躺，宣稱測量車道寬度，警方依公共危險罪移送。",
    },
    {
        "title": "騎士躺淡江大橋機車道測寬度 公路局蒐證報警舉發",
        "summary": "公路局北區養護工程分局調閱橋上監控錄影，蒐證後向警方報案，指騎士橫躺阻礙車流。",
    },
    {
        "title": "離譜！躺淡江大橋機車道「測寬度」 公路局不忍了：報警舉發",
        "summary": "通車首日即有騎士躺在淡江大橋機車道中央，公路局強調已報警處理，將依法究辦。",
    },
    {
        "title": "台64線發生多車追撞 造成3人輕傷",
        "summary": "昨日下午台64線快速道路發生三車追撞事故，警方到場處理，三名傷者送醫。",
    },
]

buffer_articles = []  # empty = first run of the week

# ─────────────────────────────────────────────────────────────────────────────

print("\n=== 送出候選 ===")
for i, a in enumerate(candidates, 1):
    print(f"[N{i}] {a['title']}")

print("\n=== 執行 LLM 去重複 ===\n")
result = dedup_same_event(candidates, buffer_articles)

print("\n=== 保留結果 ===")
for a in result:
    print(f"  ✓ {a['title']}")

excluded = [a for a in candidates if a not in result]
if excluded:
    print("\n=== 排除結果 ===")
    for a in excluded:
        print(f"  ✗ {a['title']}")
