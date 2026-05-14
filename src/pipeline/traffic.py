import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TW_TZ = timezone(timedelta(hours=8))


class TrafficCategory:
    name = "traffic"
    content_type = "traffic"
    max_articles = 20
    output_dir = "pages/traffic"
    site_url = (os.environ.get("TRAFFIC_SITE_URL") or
                os.environ.get("SITE_URL") or
                "https://lukeking.github.io/traffic-issue-scraper")

    def _current_week_id(self) -> str:
        dt = datetime.now(_TW_TZ)
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"

    def collect(self) -> list:
        from src.collector import load_sources, collect_sources
        return collect_sources(load_sources())

    def filter(self, raw: list) -> list:
        from src.filter import freshness_filter, filter_and_deduplicate, normalise_title, assign_category, compute_quality_score, compute_jaccard
        from src.pipeline_config import load_pipeline_config, load_category_taxonomy
        from src.storage import get_existing_title_fingerprints, is_configured

        existing_fps: set = set()
        if is_configured():
            try:
                existing_fps = get_existing_title_fingerprints()
            except Exception as e:
                logger.warning("[%s] 跨週指紋查詢失敗，略過：%s", self.name, e)

        after_freshness = freshness_filter(raw, existing_fps)
        # No cap yet — dedup first so the quota is spent on unique stories
        candidates = filter_and_deduplicate(after_freshness, throttle=False)

        try:
            config = load_pipeline_config()
            taxonomy = load_category_taxonomy()
        except Exception as e:
            logger.warning("[%s] 分類設定載入失敗，略過分類步驟：%s", self.name, e)
            return candidates[:self.max_articles]

        # Drop articles from blocked sources (brand keyword match).
        # Handles aggregator feeds (e.g. Google News) that bypass per-source disabling.
        blocked_sources = [kw.lower() for kw in config.get("blocked_sources", []) if kw]
        if blocked_sources:
            before = len(candidates)
            candidates = [
                a for a in candidates
                if not any(kw in (a.get("source") or "").lower() for kw in blocked_sources)
            ]
            dropped = before - len(candidates)
            if dropped:
                logger.info("[%s] 來源封鎖：略過 %d 筆", self.name, dropped)

        # Drop promotional/marketing articles by title keyword match.
        blocked_content = [kw.lower() for kw in config.get("blocked_content_keywords", []) if kw]
        if blocked_content:
            before = len(candidates)
            candidates = [
                a for a in candidates
                if not any(kw in (a.get("title") or "").lower() for kw in blocked_content)
            ]
            dropped = before - len(candidates)
            if dropped:
                logger.info("[%s] 內容關鍵字封鎖：略過 %d 筆", self.name, dropped)

        for article in candidates:
            tokens = normalise_title(article.get("title") or "")
            article["token_set"] = tokens
            cat = assign_category(tokens, taxonomy)
            article["major_category"] = cat
            article["initial_quality_score"] = compute_quality_score(
                article, taxonomy.get(cat, []), config
            )

        merge_threshold = config.get("jaccard", {}).get("merge_threshold", 0.45)

        # Per-batch Jaccard dedup: drop same-batch syndicated near-duplicates,
        # keeping the richer article (more tokens).
        deduped: list = []
        for article in candidates:
            ts = article.get("token_set", frozenset())
            dup_idx = next(
                (i for i, kept in enumerate(deduped)
                 if compute_jaccard(ts, kept.get("token_set", frozenset())) > merge_threshold),
                None,
            )
            if dup_idx is None:
                deduped.append(article)
            elif len(ts) > len(deduped[dup_idx].get("token_set", frozenset())):
                deduped[dup_idx] = article

        # LLM same-event dedup: catches same-incident articles that Jaccard misses
        # (different reporters, different angles, same event). Also checks against
        # this week's buffer so the daily quota is spent on genuinely new stories.
        if is_configured():
            try:
                from src.storage import get_traffic_buffer
                from src.analyzer import embed_dedup
                from src.pipeline_config import load_pipeline_config as _lpc
                _cfg = _lpc()
                _threshold = _cfg.get("embed_dedup", {}).get("threshold", 0.88)
                week_id = self._current_week_id()
                this_week = [
                    a for a in get_traffic_buffer(max_age_weeks=1)
                    if a.get("week_id") == week_id
                ]
                deduped = embed_dedup(deduped, this_week, threshold=_threshold)
            except Exception as e:
                logger.warning("[%s] 嵌入去重複失敗，略過：%s", self.name, e)

        deduped.sort(key=lambda a: float(a.get("initial_quality_score") or 0), reverse=True)
        return deduped[:self.max_articles]

    def analyze(self, articles: list) -> list:
        # Traffic analysis is deferred to the weekly phase (scripts/traffic_weekly_analysis.py)
        return articles

    def publish(self, articles: list) -> str:
        from src.storage import upsert_traffic_buffer, is_configured
        from src.pipeline_config import load_pipeline_config

        if not is_configured():
            logger.warning("[%s] Supabase 未設定，跳過 buffer 寫入", self.name)
            return ""

        week_id = self._current_week_id()

        try:
            config = load_pipeline_config()
            max_age_weeks = config.get("buffer", {}).get("max_age_weeks", 8)
        except Exception:
            max_age_weeks = 8

        count = upsert_traffic_buffer(articles, week_id, max_age_weeks=max_age_weeks)
        logger.info("[%s] buffer 寫入完成：%d 筆（week_id=%s）", self.name, count, week_id)
        return f"buffered {count} traffic articles for week {week_id}"
