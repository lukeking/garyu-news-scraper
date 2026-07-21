"""
scripts/traffic_buffer.py
Daily runner : collect traffic articles, filter, write to Supabase buffer.
No AI calls; exits non-zero on exception.

Runs collect -> filter -> publish and skips the analyze stage on purpose. The
project originally ran the LLM daily on freshly scraped articles, which proved
wasteful while article quality and sources were still unvalidated; hence the
split into a daily buffer and a weekly bucket analysis. Do not wire analyze()
in here on the assumption it was forgotten.

Known consequence: TrafficCategory.analyze() no longer holds any LLM work, only
the Google News link resolution and og: enrichment, so that enrichment runs on
Mondays only. Tracked in specs/BACKLOG.md — the fix is to separate the prefetch
rather than to call analyze() from here.
"""
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("traffic_buffer")


def main():
    from src.pipeline.traffic import TrafficCategory

    cat = TrafficCategory()
    logger.info("=== 交通新聞每日 buffer 開始 ===")

    raw = cat.collect()
    logger.info("收集到 %d 篇原始文章", len(raw))

    filtered = cat.filter(raw)
    logger.info("過濾後 %d 篇", len(filtered))

    result = cat.publish(filtered)
    logger.info("結果：%s", result)
    logger.info("=== 交通新聞每日 buffer 完成 ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("traffic_buffer.py 執行失敗")
        sys.exit(1)
