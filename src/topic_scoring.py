"""週交通熱點的純運算：分群、計分、新穎度閘、digest 池選材。

不呼叫外部服務（Gemini／Supabase／網路）；LLM 分析留在 `src/analyzer.py`。"""
import logging

logger = logging.getLogger(__name__)


# ── Traffic Pipeline: Clustering + Scoring (US3) ─────────────────────────────

def _article_word_count(article: dict) -> int:
    body = article.get("summary", "") or ""
    return len((article.get("title", "") + body).replace(" ", ""))


def _date_part(published: str) -> str:
    return published[:10] if published else ""


def cluster_traffic_articles(articles: list, config: dict) -> dict:
    """
    Group traffic articles into topic buckets by Jaccard similarity within each
    major_category.

    - Jaccard > merge_threshold: near-duplicate pair — keep higher word-count article (FR-013)
    - Jaccard in [cluster_lower, merge_threshold]: same topic bucket (FR-014)
    - Otherwise: new independent bucket

    Returns {bucket_id: [article_dicts]}.
    """
    from src.filter import normalise_title, compute_jaccard

    merge_threshold = config.get("jaccard", {}).get("merge_threshold", 0.45)
    cluster_lower = config.get("jaccard", {}).get("cluster_lower", 0.20)

    # Group by major_category
    by_category: dict = {}
    for article in articles:
        cat = article.get("major_category", "uncategorised")
        by_category.setdefault(cat, []).append(article)

    all_buckets: dict = {}
    bucket_counter = 0

    for cat_articles in by_category.values():
        token_sets = {id(a): normalise_title(a.get("title", "")) for a in cat_articles}

        # 1. Deduplicate: sort by word count desc; retain article only if no
        #    already-retained article has Jaccard > merge_threshold with it.
        sorted_articles = sorted(cat_articles, key=_article_word_count, reverse=True)
        deduplicated: list = []
        for article in sorted_articles:
            ts_a = token_sets[id(article)]
            is_dup = any(
                compute_jaccard(ts_a, token_sets[id(r)]) > merge_threshold
                for r in deduplicated
            )
            if not is_dup:
                deduplicated.append(article)

        # 2. Cluster: assign to an existing bucket if any member scores in
        #    [cluster_lower, merge_threshold]; start a new bucket otherwise.
        cat_buckets: dict = {}
        for article in deduplicated:
            ts_a = token_sets[id(article)]
            assigned = False
            for bid, bucket_articles in cat_buckets.items():
                for b_article in bucket_articles:
                    score = compute_jaccard(ts_a, token_sets[id(b_article)])
                    if cluster_lower <= score <= merge_threshold:
                        bucket_articles.append(article)
                        assigned = True
                        break
                if assigned:
                    break
            if not assigned:
                bid = f"bucket_{bucket_counter}"
                bucket_counter += 1
                cat_buckets[bid] = [article]

        all_buckets.update(cat_buckets)

    return all_buckets


def score_topic_buckets(buckets: dict, config: dict) -> dict:
    """
    Compute the cumulative momentum score for each bucket:
    score = Σ(quality_scores) × log(distinct_sources + 1) × log(distinct_days + 1)

    Returns {bucket_id: score}.
    """
    import math

    scores: dict = {}
    for bid, bucket_articles in buckets.items():
        quality_sum = sum(
            float(a.get("initial_quality_score") or 0) for a in bucket_articles
        )
        distinct_sources = len({a.get("source", "") for a in bucket_articles})
        distinct_days = len({
            _date_part(a.get("published", ""))
            for a in bucket_articles
            if a.get("published")
        })
        score = (
            quality_sum
            * math.log(distinct_sources + 1)
            * math.log(max(distinct_days, 1) + 1)
        )
        scores[bid] = score

    return scores


def select_hot_topics(bucket_scores: dict, config: dict) -> list:
    """
    Return at most max_hot_topics bucket_ids with score >= min_threshold,
    sorted by score descending.
    """
    topic_cfg = config.get("topic_scoring", {})
    min_threshold = float(topic_cfg.get("min_threshold", 1.5))
    max_hot_topics = int(topic_cfg.get("max_hot_topics", 3))

    qualified = [
        (bid, score) for bid, score in bucket_scores.items()
        if score >= min_threshold
    ]
    qualified.sort(key=lambda x: x[1], reverse=True)
    return [bid for bid, _ in qualified[:max_hot_topics]]


# ── Novelty gate (feature 009) ────────────────────────────────────────────────

_TOPIC_LABEL_SEP = " · "


def topic_token_signature(bucket_articles: list, top_k: int = 8) -> list:
    """Representative tokens for a bucket: the most frequent normalise_title tokens
    across its articles (up to top_k). Used for cross-week topic identity matching."""
    from collections import Counter
    from src.filter import normalise_title

    counter: Counter = Counter()
    for a in bucket_articles:
        counter.update(normalise_title(a.get("title", "")))
    return [tok for tok, _ in counter.most_common(top_k)]


def _bucket_latest_date(bucket_articles: list) -> str:
    """Latest published date (YYYY-MM-DD) among bucket articles; '' if none."""
    dates = [_date_part(a.get("published", "")) for a in bucket_articles if a.get("published")]
    return max(dates) if dates else ""


def _topic_label_category(topic_label: str) -> str:
    """Extract the major_category prefix from a topic_label ("<category> · <term>").
    Pre-009 reports stored the bare category, so a label without the separator is
    returned as-is."""
    return topic_label.split(_TOPIC_LABEL_SEP, 1)[0] if _TOPIC_LABEL_SEP in topic_label else topic_label


def _match_prior_basis(major_category: str, signature: list, prior_reports: list,
                       similarity_threshold: float) -> dict | None:
    """Most recent prior report of the same major_category whose
    topic_token_signature has Jaccard ≥ threshold with `signature`.
    prior_reports are assumed ordered week_start_date DESC. Returns basis or None."""
    from src.filter import compute_jaccard

    sig_set = frozenset(signature)
    for r in prior_reports:
        if _topic_label_category(r.get("topic_label", "")) != major_category:
            continue
        prior_sig = frozenset(r.get("topic_token_signature") or [])
        if compute_jaccard(sig_set, prior_sig) >= similarity_threshold:
            return r
    return None


def passes_novelty(bucket_score: float, bucket_latest_date: str,
                   prior_basis: dict | None, config: dict) -> bool:
    """No prior basis → novel (first-time, FR-003). Otherwise require BOTH:
       (a) bucket_score ≥ prior.cumulative_score × (1 + novelty_growth_pct), and
       (b) bucket_latest_date strictly later than prior.latest_source_date
           (a new publication day since the last report)."""
    if prior_basis is None:
        return True
    p = float(config.get("topic_scoring", {}).get("novelty_growth_pct", 0.5))
    last_score = float(prior_basis.get("cumulative_score") or 0)
    if bucket_score < last_score * (1 + p):
        return False
    last_date = prior_basis.get("latest_source_date") or ""
    return bool(bucket_latest_date) and bucket_latest_date > last_date


def select_hot_topics_with_novelty(buckets: dict, bucket_scores: dict,
                                   prior_reports: list, config: dict) -> list:
    """Gate-then-cap (feature 009): gate every bucket scoring ≥ min_threshold through
    the novelty check (matched against same-category prior reports by signature
    similarity), then take the top max_hot_topics survivors by score.
    Returns bucket_ids. prior_reports=[] → behaves like first-time (all novel)."""
    topic_cfg = config.get("topic_scoring", {})
    default_min = float(topic_cfg.get("min_threshold", 1.5))
    category_min = topic_cfg.get("category_min_threshold") or {}
    max_hot_topics = int(topic_cfg.get("max_hot_topics", 3))
    sim_threshold = float(config.get("topic_identity", {}).get("similarity_threshold", 0.3))

    survivors: list = []
    for bid, score in bucket_scores.items():
        articles = buckets.get(bid, [])
        major_category = articles[0].get("major_category", bid) if articles else bid
        # Low-cadence categories (e.g. 道安政策) can carry a lower per-category
        # threshold so their small buckets aren't blocked by the global bar tuned
        # for high-volume categories; falls back to the global min_threshold.
        threshold = float(category_min.get(major_category, default_min))
        if score < threshold:
            continue
        signature = topic_token_signature(articles)
        latest_date = _bucket_latest_date(articles)
        prior = _match_prior_basis(major_category, signature, prior_reports, sim_threshold)
        is_novel = passes_novelty(score, latest_date, prior, config)
        logger.info(
            "  novelty[%s] cat=%s score=%.3f thr=%.2f prior=%s newer_than=%s → %s",
            bid, major_category, score, threshold,
            "yes" if prior else "none",
            (prior.get("latest_source_date") if prior else "-"),
            "PASS" if is_novel else "suppress",
        )
        if is_novel:
            survivors.append((bid, score))

    survivors.sort(key=lambda x: x[1], reverse=True)
    return [bid for bid, _ in survivors[:max_hot_topics]]


# ── Category digest pool (feature 010) ─────────────────────────────────────────


def select_digest_pool(articles: list, category: str, digest_cfg: dict,
                       excluded_links: set) -> tuple:
    """
    組出某低頻類別的 digest 池（純函數、零 I/O）。

    Returns (selected, pool_all, effective_count):
    - pool_all: 該類別全部未排除文章（含低於品質下限者）——消耗（清池）用。
    - selected: quality ≥ quality_floor 者依 quality 降冪取前 max_articles 篇——選材。
    - effective_count: quality ≥ quality_floor 的篇數——觸發判斷用（呼叫端比對 trigger_count）。

    池的成員判定吃**一組**類別（feature 013）：`{category} ∪ include_categories`。
    用集合而非 list 串接，故清單含主類別自己時自動去重、順序不影響輸出。
    缺 `include_categories` ⇒ 空清單 ⇒ 集合退化為 `{category}` ⇒ 行為與本功能
    不存在時逐篇相同。**不改動輸入物件**：匯流只影響成員判定，不寫回
    `major_category`，buffer list 的細分類因此保留。
    """
    quality_floor = float(digest_cfg.get("quality_floor", 0.18))
    max_articles = int(digest_cfg.get("max_articles", 15))
    categories = {category} | set(digest_cfg.get("include_categories") or [])

    pool_all = [
        a for a in articles
        if a.get("major_category") in categories
        and (a.get("link") or "") not in excluded_links
    ]
    effective = [
        a for a in pool_all
        if float(a.get("initial_quality_score") or 0) >= quality_floor
    ]
    effective.sort(key=lambda a: float(a.get("initial_quality_score") or 0), reverse=True)
    return effective[:max_articles], pool_all, len(effective)


def log_digest_pool_composition(logger, category: str, digest_cfg: dict,
                                pool_all: list) -> None:
    """印出 digest 池的逐類別組成（013 C3），讓「匯流有沒有效」不必查 DB 就能從 log 判讀。

    **零篇的類別也要印**——沉默與「跑了但沒事可做」無法區分，而缺口能躺數週
    正是因為沉默不留腳印。這條規則的誘惑點就在下面那個 join：任何「跳過 0」的
    寫法（`if n`、`most_common()`、過濾 falsy）都會讓零篇類別整行消失，
    所以 `test_composition_prints_zero_count_category` 守的是這裡。

    `logger` 由呼叫端傳入，讓這行仍掛在週跑腳本的 logger 名字下（log 輸出逐字不變）。
    無 `include_categories` ⇒ 不印，與匯流不存在時行為相同。
    """
    from collections import Counter

    merged_cats = list(digest_cfg.get("include_categories") or [])
    if not merged_cats:
        return
    per_cat = Counter(a.get("major_category") for a in pool_all)
    parts = " ＋ ".join(f"{c} {per_cat.get(c, 0)}" for c in [category] + merged_cats)
    logger.info("digest[%s] 池組成：%s = %d", category, parts, len(pool_all))
