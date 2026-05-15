from typing import Protocol, runtime_checkable


@runtime_checkable
class Category(Protocol):
    name: str
    content_type: str
    max_articles: int
    output_dir: str
    site_url: str

    def collect(self) -> list: ...
    def filter(self, raw: list) -> list: ...
    def analyze(self, articles: list) -> list: ...
    def publish(self, articles: list) -> str: ...
