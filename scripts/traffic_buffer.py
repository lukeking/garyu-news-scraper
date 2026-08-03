"""
scripts/traffic_buffer.py
Daily runner : collect traffic articles, filter, prefetch (og:), write to buffer.
No AI calls; exits non-zero on exception.

Runs collect -> filter -> prefetch -> publish, skipping the weekly LLM analysis on
purpose. The project originally ran the LLM daily on freshly scraped articles, which
proved wasteful while article quality and sources were still unvalidated; hence the
split into a daily buffer and a weekly bucket analysis. Do NOT wire the weekly LLM
analysis in here.

prefetch() is Google News link resolution + og: enrichment — HTTP-only, no LLM — so
it belongs on the daily path and keeps this runner AI-free. It used to live only in
the weekly path, so Google News rows kept an unresolved link and no image until
Monday (specs/BACKLOG.md). Kill-switch: set buffer.daily_enrich=false to stop hitting
publisher domains 7x/week if the 403 block-list starts expanding into native media.
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
    from src.pipeline_config import load_pipeline_config

    cat = TrafficCategory()
    logger.info("=== 交通新聞每日 buffer 開始 ===")

    raw = cat.collect()
    logger.info("收集到 %d 篇原始文章", len(raw))

    filtered = cat.filter(raw)
    logger.info("過濾後 %d 篇", len(filtered))

    # og enrichment (HTTP-only, no LLM) used to run on Mondays only, so most Google
    # News rows kept an unresolved link and no image. Run it daily now. Kill-switch:
    # buffer.daily_enrich=false to stop hitting publisher domains 7x/week if the 403
    # block-list starts expanding into native media. See specs/BACKLOG.md.
    try:
        daily_enrich = load_pipeline_config().get("buffer", {}).get("daily_enrich", True)
    except Exception as e:
        logger.warning("pipeline_config 載入失敗，daily_enrich 預設開啟：%s", e)
        daily_enrich = True

    if daily_enrich:
        cat.prefetch(filtered)
    else:
        from src.gn_resolver import is_gn_article_link
        gn_pending = sum(1 for a in filtered if is_gn_article_link(a.get("link") or ""))
        logger.info(
            "每日 og 充實已關閉（buffer.daily_enrich=false）：%d/%d 篇 Google News "
            "文章維持未還原連結、無 og 摘要與圖片",
            gn_pending, len(filtered),
        )

    result = cat.publish(filtered)
    logger.info("結果：%s", result)
    logger.info("=== 交通新聞每日 buffer 完成 ===")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("traffic_buffer.py 執行失敗")
        sys.exit(1)
