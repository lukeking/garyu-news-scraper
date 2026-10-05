import logging
import os
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TW_TZ = timezone(timedelta(hours=8))



def dedup_window(buffer_rows: list, now: datetime) -> list:
    """embed_dedup 比對的 buffer 列：本週與上週、還沒被消耗的（週報池＝全部未消耗的列，最長 8 週）。
    更早的不放進來：每月一次的同類事件（例如道安會報）餘弦也 ≥ 0.88，會被誤殺（GNS-20261005-nwn）。"""
    local = now.astimezone(_TW_TZ)
    weeks = {f"{y}-W{w:02d}" for y, w, _ in (local.isocalendar(), (local - timedelta(days=7)).isocalendar())}
    return [a for a in buffer_rows if a.get("week_id") in weeks]

class TrafficCategory:
    name = "traffic"
    content_type = "traffic"
    max_articles = 20  # degraded fallback only (config-load failure); buffer cap is buffer.max_daily_articles
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
        from src.filter import freshness_filter, filter_and_deduplicate, normalise_title, assign_category, resolve_source_default, compute_quality_score, compute_jaccard
        from src.pipeline_config import load_pipeline_config, load_category_taxonomy, load_source_default_categories
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
            source_defaults = load_source_default_categories()
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
            if cat == "uncategorised" and source_defaults:
                cat = resolve_source_default(article.get("source", ""), source_defaults)
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
        # (different reporters, different angles, same event). Also checks against this and
        # last week's unconsumed buffer so the daily quota is spent on genuinely new stories.
        if is_configured():
            try:
                deduped = self._embedding_dedup(deduped, config)
            except Exception as e:
                logger.warning("[%s] 嵌入去重複失敗，略過：%s", self.name, e)

        deduped.sort(key=lambda a: float(a.get("initial_quality_score") or 0), reverse=True)
        # Buffer cap is a feed-flood safety ceiling, not a cost control: generative
        # spend is bounded at the weekly stage (min_threshold + max_hot_topics + novelty
        # gate), so low-frequency deep sources are no longer starved by a tight daily cap.
        max_daily = config.get("buffer", {}).get("max_daily_articles", 100)
        return deduped[:max_daily]

    def _embedding_dedup(self, deduped: list, config: dict, now=None) -> list:
        from src.storage import get_traffic_buffer
        from src.analyzer import attach_embeddings, embed_dedup
        threshold = config.get("embed_dedup", {}).get("threshold", 0.88)
        window = dedup_window(get_traffic_buffer(), now or datetime.now(_TW_TZ))
        # 生成向量（不純、會打 Gemini）與去重（純）刻意分成兩步，見 BACKLOG #4。
        attach_embeddings(deduped)
        deduped = embed_dedup(deduped, window, threshold=threshold)
        try:
            self._shadow_cross_run(deduped, threshold)
        except Exception as e:
            logger.warning("[embed_dedup 影子] 跨期比對失敗，略過（只記錄，不影響去重）：%s", e)
        return deduped

    def _shadow_cross_run(self, candidates: list, threshold: float) -> None:
        from src.storage import get_recent_consumed_traffic
        from src.analyzer import find_cross_run_repeats
        hits = find_cross_run_repeats(candidates, get_recent_consumed_traffic(), threshold=threshold)
        for cand, old, cos, gap_h in hits:
            logger.info("[embed_dedup 影子] 會擋 cos=%.4f 發布差 %.1fh：「%s」↔ 已消耗 id=%s「%s」",
                        cos, gap_h, cand.get("title"), old.get("id"), old.get("title"))
        logger.info("[embed_dedup 影子] 跨期重複：%d/%d 篇候選會被擋（發布差 < 24h、餘弦 ≥ %.2f；只記錄、不擋）",
                    len(hits), len(candidates), threshold)

    def prefetch(self, articles: list) -> list:
        # Google News link resolution + og:description/og:image enrichment. No LLM —
        # HTTP-only, ~1.7s/article — so this belongs on both the weekly path (via
        # analyze) and the daily runner (scripts/traffic_buffer.py). Extracted out of
        # analyze() so daily enrichment no longer runs on Mondays only, which is why
        # most Google News rows used to keep an unresolved link and no image.
        # See specs/BACKLOG.md.
        try:
            from src.gn_resolver import enrich_articles
            enrich_articles(articles)
        except Exception as e:
            logger.warning("[%s] GN 充實整批失敗，文章維持原樣：%s", self.name, e)
        return articles

    def analyze(self, articles: list) -> list:
        # LLM analysis is deferred to the weekly phase (scripts/traffic_weekly_analysis.py).
        # For traffic, analyze() carries no LLM work itself — it is the pipeline entry
        # point (main.py) that runs the HTTP-only prefetch on post-dedup articles.
        return self.prefetch(articles)

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
