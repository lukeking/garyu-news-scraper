import os


class TrafficCategory:
    name = "traffic"
    content_type = "traffic"
    max_articles = 20
    output_dir = "pages/traffic"
    site_url = (os.environ.get("TRAFFIC_SITE_URL") or
                os.environ.get("SITE_URL") or
                "https://lukeking.github.io/traffic-issue-scraper")

    def collect(self) -> list:
        from src.collector import collect_by_type
        return collect_by_type("traffic")

    def filter(self, raw: list) -> list:
        from src.filter import filter_and_deduplicate
        return filter_and_deduplicate(raw)[:self.max_articles]

    def analyze(self, articles: list) -> list:
        from src.analyzer import analyze_all
        return analyze_all(articles)

    def publish(self, articles: list) -> str:
        from src.publisher import publish
        return publish(articles, output_dir=self.output_dir, site_url=self.site_url)
