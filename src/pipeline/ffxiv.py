import logging
import os

logger = logging.getLogger(__name__)


class FFXIVCategory:
    name = "ffxiv"
    content_type = "ffxiv"
    max_articles = 30
    output_dir = "pages/ffxiv"
    site_url = os.environ.get("FFXIV_SITE_URL", "https://garyu-ffxiv-news.pages.dev")

    def collect(self) -> list:
        from src.collector import load_ffxiv_sources, collect_sources
        return collect_sources(load_ffxiv_sources())

    def filter(self, raw: list) -> list:
        from src.filter import freshness_filter, filter_and_deduplicate, game_deduplicate
        from src.pipeline_config import load_pipeline_config
        from src.storage import get_existing_title_fingerprints, is_configured
        existing_fps: set = set()
        if is_configured():
            try:
                existing_fps = get_existing_title_fingerprints()
            except Exception as e:
                logger.warning("[%s] 跨週指紋查詢失敗，略過：%s", self.name, e)
        after_freshness = freshness_filter(raw, existing_fps)
        after_dedup = filter_and_deduplicate(after_freshness)
        config = load_pipeline_config()
        return game_deduplicate(after_dedup, config)

    def analyze(self, articles: list) -> list:
        from src.analyzer import analyze_all
        return analyze_all(articles)

    def publish(self, articles: list) -> str:
        from src.publisher import publish
        return publish(
            articles,
            output_dir=self.output_dir,
            site_url=self.site_url,
            feed_title="最終幻想XIV 週報",
            feed_description="每週自動彙整 FFXIV 遊戲相關資訊，含 AI 摘要與重點分析",
        )
