import logging
import os

logger = logging.getLogger(__name__)


class TrafficCategory:
    name = "traffic"
    content_type = "traffic"
    max_articles = 20
    output_dir = "pages/traffic"
    site_url = (os.environ.get("TRAFFIC_SITE_URL") or
                os.environ.get("SITE_URL") or
                "https://lukeking.github.io/traffic-issue-scraper")

    def collect(self) -> list:
        from src.collector import load_sources, collect_sources
        return collect_sources(load_sources())

    def filter(self, raw: list) -> list:
        from src.filter import freshness_filter, filter_and_deduplicate
        from src.storage import get_existing_title_fingerprints, is_configured
        existing_fps: set = set()
        if is_configured():
            try:
                existing_fps = get_existing_title_fingerprints()
            except Exception as e:
                logger.warning("[%s] 跨週指紋查詢失敗，略過：%s", self.name, e)
        after_freshness = freshness_filter(raw, existing_fps)
        return filter_and_deduplicate(after_freshness)[:self.max_articles]

    def analyze(self, articles: list) -> list:
        from src.analyzer import analyze_all
        return analyze_all(articles)

    def publish(self, articles: list) -> str:
        from src.publisher import publish
        return publish(articles, output_dir=self.output_dir, site_url=self.site_url)
