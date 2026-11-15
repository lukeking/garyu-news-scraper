import logging
import os
from collections import Counter
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_TW_TZ = timezone(timedelta(hours=8))



def dedup_window(buffer_rows: list, now: datetime) -> list:
    """embed_dedup 比對的 buffer 列：本週與上週、還沒被消耗的（週報池＝全部未消耗的列，最長 8 週）。
    更早的不放進來：每月一次的同類事件（例如道安會報）餘弦也 ≥ 0.88，會被誤殺（GNS-20261005-nwn）。"""
    local = now.astimezone(_TW_TZ)
    weeks = {f"{y}-W{w:02d}" for y, w, _ in (local.isocalendar(), (local - timedelta(days=7)).isocalendar())}
    return [a for a in buffer_rows if a.get("week_id") in weeks]


def confluence_categories(config: dict) -> set:
    """匯流類別＝每個 category_digest 的主類別＋其 include_categories；從設定推導，程式裡不寫類別名。"""
    out: set = set()
    for cat, entry in (config.get("category_digest") or {}).items():
        out |= {cat} | set(entry.get("include_categories") or [])
    return out


def source_funnel(attempted: list, stages: list, confluence: set) -> dict:
    """逐來源漏斗（contracts C1）：stages＝收集…寫入上限七關之後的 list，回傳 {來源: (a…g, h)}。
    順序先照 attempted、再補 stages[0] 裡名單外的來源（依首次出現）；0 篇的來源照樣有一列。"""
    per_stage = [Counter(a.get("source") for a in stage) for stage in stages]
    in_confluence = Counter(a.get("source") for a in stages[-1] if a.get("major_category") in confluence)
    names = dict.fromkeys(list(attempted) + [a.get("source") for a in stages[0]])
    return {n: tuple(c[n] for c in per_stage) + (in_confluence[n],) for n in names}


def funnel_line(source, counts: tuple) -> str:
    """C1 的一行。行首與箭頭是週驗收 routine grep 的錨（C1-4），改了要同步 routine。"""
    a, b, c, d, e, f, g, h = counts
    return f"[來源漏斗] {source}：收集 {a} → 新鮮度 {b} → 過濾 {c} → 封鎖 {d} → 同批去重 {e} → 向量去重 {f} → 寫入上限 {g}（匯流四類 {h}）"


# collected.json 的逐來源欄位，依序對到 funnel_line 的 a…h；kept 是 filter() 交出去的篇數（寫入上限之後）
FUNNEL_FIELDS = ("collected", "after_freshness", "after_keyword_filter", "after_source_block",
                 "after_batch_dedup", "after_vector_dedup", "kept", "kept_in_confluence")

class TrafficCategory:
    name = "traffic"
    content_type = "traffic"
    llm_stage = None  # analyze() 只做 HTTP 充實、不呼叫生成式 LLM，不發布的兩級都照跑
    max_articles = 20  # degraded fallback only (config-load failure); buffer cap is buffer.max_daily_articles
    output_dir = "pages/traffic"
    site_url = (os.environ.get("TRAFFIC_SITE_URL") or
                os.environ.get("SITE_URL") or
                "https://lukeking.github.io/traffic-issue-scraper")

    def _current_week_id(self) -> str:
        dt = datetime.now(_TW_TZ)
        y, w, _ = dt.isocalendar()
        return f"{y}-W{w:02d}"

    def collect(self, sources: list | None = None) -> list:
        from src.collector import load_sources, collect_sources
        if sources is None:
            sources = load_sources()
        self._attempted_names = [s.get("name") for s in sources]
        return collect_sources(sources)

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
        stages = [raw, after_freshness, candidates]

        try:
            config = load_pipeline_config()
            taxonomy = load_category_taxonomy()
            source_defaults = load_source_default_categories()
        except Exception as e:
            logger.warning("[%s] 分類設定載入失敗，略過分類步驟：%s", self.name, e)
            self.last_funnel = {}
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
        stages.append(candidates)

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
        stages.append(deduped)

        # LLM same-event dedup: catches same-incident articles that Jaccard misses
        # (different reporters, different angles, same event). Also checks against this and
        # last week's unconsumed buffer so the daily quota is spent on genuinely new stories.
        if is_configured():
            try:
                deduped = self._embedding_dedup(deduped, config)
            except Exception as e:
                logger.warning("[%s] 嵌入去重複失敗，略過：%s", self.name, e)
        stages.append(deduped)

        deduped.sort(key=lambda a: float(a.get("initial_quality_score") or 0), reverse=True)
        # Buffer cap is a feed-flood safety ceiling, not a cost control: generative
        # spend is bounded at the weekly stage (min_threshold + max_hot_topics + novelty
        # gate), so low-frequency deep sources are no longer starved by a tight daily cap.
        max_daily = config.get("buffer", {}).get("max_daily_articles", 100)
        kept = deduped[:max_daily]
        stages.append(kept)

        attempted = getattr(self, "_attempted_names", [])
        self.last_funnel = source_funnel(attempted, stages, confluence_categories(config))
        for source, counts in self.last_funnel.items():
            logger.info("%s", funnel_line(source, counts))
        return kept

    def _embedding_dedup(self, deduped: list, config: dict, now=None) -> list:
        from src.storage import get_traffic_buffer
        from src.analyzer import attach_embeddings, embed_dedup
        threshold = config.get("embed_dedup", {}).get("threshold", 0.88)
        window = dedup_window(get_traffic_buffer(), now or datetime.now(_TW_TZ))
        # 生成向量（不純、會打 Gemini）與去重（純）刻意分成兩步，見 BACKLOG #4。
        attach_embeddings(deduped)
        deduped = embed_dedup(deduped, window, threshold=threshold)
        cross_threshold = config.get("embed_dedup", {}).get("cross_run_threshold", 0.92)
        try:
            deduped = self._drop_cross_run_repeats(deduped, cross_threshold)
        except Exception as e:
            logger.warning("[embed_dedup 跨期] 比對失敗，本次不擋：%s", e)
        return deduped

    def _drop_cross_run_repeats(self, candidates: list, threshold: float) -> list:
        from src.storage import get_recent_consumed_traffic
        from src.analyzer import find_cross_run_repeats
        hits = find_cross_run_repeats(candidates, get_recent_consumed_traffic(), threshold=threshold)
        for cand, old, cos, gap_h in hits:
            logger.info("[embed_dedup 跨期] 擋下 cos=%.4f 發布差 %.1fh：「%s」↔ 已消耗 id=%s「%s」",
                        cos, gap_h, cand.get("title"), old.get("id"), old.get("title"))
        logger.info("[embed_dedup 跨期] 擋下 %d/%d 篇候選（發布差 < 24h、餘弦 ≥ %.2f）",
                    len(hits), len(candidates), threshold)
        dropped = {id(cand) for cand, _, _, _ in hits}
        return [a for a in candidates if id(a) not in dropped]

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
        return self._drop_old_after_enrich(articles)

    def _drop_old_after_enrich(self, articles: list) -> list:
        """GNS-20261108-a7k：充實把 published 換成媒體頁日期後再跑一次年齡門檻（GN 給公視舊文固定日期）；
        媒體頁沒日期時看的是 GN 的 published，所以 log 只寫「日期」。"""
        from urllib.parse import urlparse
        from src.filter import FRESHNESS_THRESHOLD_DAYS, _is_too_old_by_age
        kept = []
        for a in articles:
            if _is_too_old_by_age(a)[0]:
                logger.info("[充實後過時] 擋下：%s 日期 %s「%s」", urlparse(a.get("link") or "").netloc,
                            (a.get("published") or "")[:10], (a.get("title") or "")[:40])
            else:
                kept.append(a)
        logger.info("[充實後過時] 擋下 %d/%d 篇（充實後的日期早於 %d 天前）",
                    len(articles) - len(kept), len(articles), FRESHNESS_THRESHOLD_DAYS)
        return kept

    def analyze(self, articles: list) -> list:
        # LLM analysis is deferred to the weekly phase (scripts/traffic_weekly_analysis.py).
        # For traffic, analyze() carries no LLM work itself — it is the pipeline entry
        # point (main.py) that runs the HTTP-only prefetch on post-dedup articles.
        return self.prefetch(articles)

    def _buffer_max_age_weeks(self) -> int:
        from src.pipeline_config import load_pipeline_config
        try:
            config = load_pipeline_config()
            return config.get("buffer", {}).get("max_age_weeks", 8)
        except Exception:
            return 8

    def _dump_collected(self, articles: list) -> None:
        """不發布：TRAFFIC_POOL_DIR 有設才寫 collected.json（級別、逐來源漏斗、buffer 會收到的列）；沒設或寫不進去都印一行。"""
        import json
        from src import run_mode
        from src.storage import traffic_buffer_rows
        out_dir = os.environ.get("TRAFFIC_POOL_DIR", "").strip()
        if not out_dir:
            logger.info("交通候選清單：未設 TRAFFIC_POOL_DIR，不寫檔")
            return
        week_id = self._current_week_id()
        rows = traffic_buffer_rows(articles, week_id, datetime.now(timezone.utc), self._buffer_max_age_weeks())
        funnel = getattr(self, "last_funnel", {})
        data = {
            "run_mode": run_mode.current(),
            "week_id": week_id,
            "sources": [{"source": s, **dict(zip(FUNNEL_FIELDS, counts))} for s, counts in funnel.items()],
            "article_count": len(rows),
            "articles": rows,
        }
        path = os.path.join(out_dir, "collected.json")
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1, default=str)
        except OSError as e:
            logger.warning("交通候選清單：寫入 %s 失敗（%s）", path, e)
            return
        logger.info("交通候選清單：寫入 %s（%d 篇）", path, len(rows))

    def publish(self, articles: list) -> str:
        from src import run_mode
        from src.storage import upsert_traffic_buffer, is_configured

        if run_mode.is_dry_run():
            self._dump_collected(articles)

        if not is_configured():
            logger.warning("[%s] Supabase 未設定，跳過 buffer 寫入", self.name)
            return ""

        week_id = self._current_week_id()
        max_age_weeks = self._buffer_max_age_weeks()

        count = upsert_traffic_buffer(articles, week_id, max_age_weeks=max_age_weeks)
        if run_mode.is_dry_run():
            return ""  # 略過那一行已經由 upsert_traffic_buffer 印了，不再印「寫入完成」
        logger.info("[%s] buffer 寫入完成：%d 筆（week_id=%s）", self.name, count, week_id)
        return f"buffered {count} traffic articles for week {week_id}"
