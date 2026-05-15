# Research: Modular News Processing Engine

**Feature**: `006-traffic-news-pipeline` | **Date**: 2026-05-12

## Decision 1: Chinese Word Segmentation Library

**Decision**: Use `jieba` for Chinese word segmentation with a project-managed custom user dictionary.

**Rationale**: jieba is the de-facto standard for Traditional/Simplified Chinese tokenisation in Python. It supports a `userdict.txt` file (`jieba.load_userdict(path)`) for entity protection — road names and numerical facts can be added as single entries so they are never split mid-token. Zero cost; no external API dependency.

**Alternatives considered**:
- `ckip-transformers` (CKIP Lab, National Taiwan University): higher accuracy for Traditional Chinese, but heavyweight (transformer models, GPU-optional). Overkill for title-level token sets and contradicts free-tier discipline.
- `pkuseg`: good accuracy but lower community adoption and slower than jieba for short texts.

**Implementation note**: Custom dictionary lives at `config/jieba_userdict.txt`. Stored as GitHub Environment Variable `JIEBA_USERDICT_TXT`. Loaded once at `src/filter.py` module import. Seed entries: common Taipei/New Taipei road names, numerical patterns like `3死`, `57歲`, `北部`.

---

## Decision 2: Jaccard Similarity Computation Location

**Decision**: Compute Jaccard similarity entirely in Python (in `src/filter.py`), not via PostgreSQL GIN index queries.

**Rationale**: Expected weekly buffer volume is 70–560 articles. At this scale, a full O(n²) pairwise Python comparison over token sets takes < 1 second. Adding a PostgreSQL `text[]` column with GIN index would require schema complexity (array literals, `&&` operator queries via supabase-py REST) that is disproportionate to the scale. Python set operations (`len(A & B) / len(A | B)`) are readable and testable without a live DB.

**Alternatives considered**:
- PostgreSQL GIN index with `&&` operator: faster at scale (10k+ articles), but supabase-py's REST interface makes raw `&&` queries awkward. Deferred as an optimisation if volume grows beyond 1,000 weekly articles.

---

## Decision 3: Initial Quality Score Formula (Zero AI Cost)

**Decision**: Algorithmic quality score at ingestion: `score = (kw_match_ratio × 0.4) + (norm_word_count × 0.3) + (source_weight × 0.3)`

Where:
- `kw_match_ratio` = (number of category keywords matched in title) / (total keywords in category), capped at 1.0
- `norm_word_count` = `min(word_count, 500) / 500` (longer articles score higher, but plateau at 500 chars)
- `source_weight` = lookup from a `source_weights` map in `pipeline_config.yml` (default 0.5 for unknown sources; known major outlets get 0.7–1.0)

**Rationale**: Proxy for article significance without an AI call. Keyword density reflects relevance to the category. Word count proxies information density. Source weight proxies editorial credibility. All three are available at ingestion time with zero API cost.

**Alternatives considered**:
- AI classification at ingestion (Option A from clarification): rejected — daily AI calls would violate the "near-zero token cost" design goal and free-tier discipline.
- Pure word count: too easily gamed by verbose low-quality articles.

---

## Decision 4: Cumulative Topic Score Formula

**Decision**: `cumulative_score = Σ(article.quality_score) × log(distinct_sources + 1) × log(distinct_days + 1)`

Applied across all articles in a topic bucket that have `hot_topic_analyzed = false` and `buffer_expires_at > NOW()`.

Where:
- `Σ(article.quality_score)` = sum of per-article quality scores across all buffer weeks for this category
- `distinct_sources` = count of distinct `source` values in the bucket
- `distinct_days` = count of distinct publication dates in the bucket

The log transforms prevent a single-day spike of many articles from dominating over a slow-burning multi-week issue with genuine breadth. `log(x + 1)` ensures score stays ≥ 0 when counts are low.

**Threshold**: Configurable in `pipeline_config.yml` (`topic_scoring.min_threshold`). Default value: `1.5`. Tunable after first few runs.

**Alternatives considered**:
- Linear weighting `(count × w1) + (sources × w2) + (days × w3)`: simpler but linear growth means a single high-traffic day could outscore a genuinely persistent issue. Log scale better captures the "diminishing returns of breadth".

---

## Decision 5: Monday Scheduling Without Race Condition

**Decision**: `traffic_daily.yml` runs Tue–Sun (`0 0 * * 2-7`). Monday collection is a dedicated step in `weekly.yml` (runs first, before the FFXIV pipeline and before the weekly analysis).

**Rationale**: Running both workflows simultaneously on Monday would create a race condition between Monday's buffer write and the weekly analysis read. By making Monday's collection an explicit first step in `weekly.yml`, we guarantee ordering: collect → (FFXIV pipeline runs in parallel concern) → weekly analysis.

**Alternatives considered**:
- `workflow_run` trigger chaining: overly complex for this use case.
- Running `traffic_daily.yml` 7 days/week and relying on it to complete before `weekly.yml` starts: GitHub Actions cron is not guaranteed to fire at exact seconds, making this brittle.

---

## Decision 6: `TrafficCategory` Pipeline Mode Change

**Decision**: `TrafficCategory.analyze()` returns its input unchanged (no Gemini call). `TrafficCategory.publish()` calls `upsert_traffic_buffer()` instead of the frontend publisher.

The existing `main.py` calling `TrafficCategory` will now buffer articles rather than publish them. Individual traffic article analyses on the frontend are retired; the frontend shows hot topic reports only.

**Rationale**: Cleanest way to hook the new behaviour into the existing `Category` protocol without introducing a mode flag or a new class. `main.py` remains unchanged. The `Category` protocol contract is still satisfied.

**Implications**: The existing traffic frontend (`pages/traffic/index.html`) will need to be updated to render `hot_topic_reports` instead of individual articles. This is an intentional UX change (hot topic reports replace individual article analysis cards).

---

## Decision 7: Buffer Expiry Mechanism

**Decision**: `buffer_expires_at` column on `articles` table, set to `buffered_at + 8 weeks` at insert time. `expire_buffer_articles()` in `storage.py` deletes rows where `buffer_expires_at < NOW() AND hot_topic_analyzed = false AND content_type = 'traffic'`. Called at the start of each weekly analysis run.

**Rationale**: Prevents buffer from growing unboundedly. Hard cutoff is enforced database-side via a timestamp column, not computed in Python each run. Expired articles are deleted (not archived) since they have never been published and are no longer newsworthy.
