import os


class FFXIVCategory:
    name = "ffxiv"
    content_type = "ffxiv"
    max_articles = 10
    output_dir = "pages/ffxiv"
    site_url = os.environ.get("FFXIV_SITE_URL", "https://garyu-ffxiv-news.pages.dev")

    def collect(self) -> list:
        from src.collector import collect_by_type
        return collect_by_type("ffxiv")

    def filter(self, raw: list) -> list:
        from src.filter import filter_and_deduplicate
        return filter_and_deduplicate(raw)[:self.max_articles]

    def analyze(self, articles: list) -> list:
        from src.analyzer import analyze_all
        return analyze_all(articles)

    def publish(self, articles: list) -> str:
        from src.publisher import publish
        return publish(articles, output_dir=self.output_dir, site_url=self.site_url)
