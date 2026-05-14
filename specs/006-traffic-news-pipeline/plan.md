# Implementation Plan: Modular News Processing Engine

**Branch**: `006-traffic-news-pipeline` | **Date**: 2026-05-12 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/006-traffic-news-pipeline/spec.md`

## Summary

Three coordinated changes that split the traffic pipeline into a daily buffer phase and a weekly hot-topic deep-analysis phase, while leaving the FFXIV pipeline untouched:

1. **Traffic pipeline refactor** — `TrafficCategory.analyze()` becomes a no-op (no Gemini call); `.publish()` upserts articles to a buffer (new `articles` columns) instead of publishing to pages. Text normalisation, category assignment, and quality scoring are added to `TrafficCategory.filter()`.
2. **Weekly traffic analysis** — New `scripts/traffic_weekly_analysis.py` reads buffered articles, clusters them by Jaccard similarity, scores topic buckets (composite: count × source-diversity × day-spread × cumulative-momentum), selects hot topics above a configurable threshold, calls Gemini once per hot topic, and stores results in a new `hot_topic_reports` table.
3. **Scheduling split** — New `traffic_daily.yml` GitHub Actions workflow runs daily (Tue–Sun 08:00 TST) to collect and buffer traffic articles. Existing `weekly.yml` is extended with two new steps on Monday: a final Monday collection call and the weekly analysis runner.

The FFXIV pipeline, existing `main.py`, and all FFXIV-specific modules remain unchanged.

## Technical Context

**Language/Version**: Python 3.11 (pipeline + scripts) / Vanilla JS (frontend) / GitHub Actions YAML
**Primary Dependencies**: supabase-py (existing), requests (existing for Gemini), jieba (new — Chinese word segmentation)
**Storage**: Supabase PostgreSQL — new `hot_topic_reports` table + new columns on `articles` table
**Testing**: pytest (existing); unit tests for normaliser and Jaccard; integration tests for buffer and weekly analysis
**Target Platform**: GitHub Actions (scheduling); Cloudflare Pages (traffic frontend); Cloudflare Worker (API)
**Project Type**: Data pipeline (Python batch) + static frontend (Vanilla JS) + GitHub Actions automation
**Performance Goals**: Daily buffer run ≤ 3 min; weekly analysis (including Gemini calls) ≤ 8 min total
**Constraints**: No new paid services; max 3 Gemini calls per weekly run (one per hot topic); daily traffic collection must complete before Monday 08:00 TST analysis run; free-tier Supabase limits respected
**Scale/Scope**: Expected 10–80 traffic articles/day; weekly buffer pool of 70–560 articles; max 3 hot-topic reports per week

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design below.*

### Principle I — Pipeline Integrity ✓
- Daily phase: Collect → Filter (normalise + categorise + score + deduplicate) → Store (buffer). Each stage completes before the next; silence is forbidden per constitution.
- Weekly phase: Read Buffer → Cluster → Score Topics → Analyze → Publish. Gated: if fewer than 3 buffered articles exist, pipeline halts with logged reason and no Gemini call is made.
- `TrafficCategory` still fulfils the `Category` protocol contract; no cross-stage skipping introduced.

### Principle II — Configuration over Code ✓
- Category taxonomy → `config/categories_traffic.yml` stored as GitHub Environment Variable `CATEGORIES_TRAFFIC_YML`. Committed example: `config/categories_traffic.example.yml`.
- Pipeline thresholds (Jaccard bounds, topic score threshold, buffer max age, hot-topic max count) → `config/pipeline_config.yml` stored as GitHub Environment Variable `PIPELINE_CONFIG_YML`. Committed example: `config/pipeline_config.example.yml`.
- No threshold or category keyword is hardcoded in `src/`.

### Principle III — Idempotency & Deduplication ✓
- Jaccard deduplication for traffic occurs in `src/filter.py` (same module as all other dedup).
- `hot_topic_reports` upserted with `(week_start_date, topic_label)` as unique key — re-running Monday analysis produces identical rows.
- New `articles` buffer columns use the same `content_fingerprint` stable key already in use.

### Principle IV — Free Tier Discipline ✓
- Daily buffer phase: zero Gemini calls.
- Weekly analysis: at most 3 Gemini calls per run (one per qualified hot topic). Well within free-tier rate limits.
- Two new GitHub Actions workflows (daily + extended weekly). Daily run estimated at 2–3 min. Combined Monday run estimated at 7–9 min. Total monthly usage well within 2,000 free minutes.

### Principle V — Single Responsibility ✓
- `src/filter.py`: gains `normalise_traffic_title()`, `compute_jaccard()`, `assign_category()`, `compute_quality_score()`. All are filtering/preprocessing concerns.
- `src/analyzer.py`: gains `cluster_traffic_articles()`, `score_topic_buckets()`, `select_hot_topics()`, `analyze_hot_topic()`. All are analysis concerns.
- `src/storage.py`: gains `upsert_traffic_buffer()`, `get_traffic_buffer()`, `upsert_hot_topic_report()`, `expire_buffer_articles()`. All are storage concerns.
- `src/publisher.py`: gains `publish_hot_topic_reports()`. Publishing concern.
- `scripts/traffic_buffer.py` and `scripts/traffic_weekly_analysis.py`: operational scripts (same pattern as `scripts/auto_kb.py`), not `src/` stage modules.
- jieba custom dictionary loaded once at module import in `src/filter.py`; not spread across modules.

### Principle VI — Knowledge Base Integrity ✓ (not applicable to traffic analysis)

**Post-design re-check**: All artifacts (research.md, data-model.md, contracts/) are consistent with the constitution. No amendments required.

**Gate result**: PASS — implementation may proceed immediately.

## Project Structure

### Documentation (this feature)

```text
specs/006-traffic-news-pipeline/
├── plan.md              # This file
├── research.md          # Phase 0: key decisions
├── data-model.md        # Phase 1: Supabase schema changes
├── quickstart.md        # Phase 1: local run guide
├── contracts/
│   ├── api-hot-topics.md        # Cloudflare Worker endpoint contract
│   └── config-files.md          # categories_traffic.yml + pipeline_config.yml contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
# New files
scripts/traffic_buffer.py             # Daily runner: TrafficCategory collect+filter+store
scripts/traffic_weekly_analysis.py    # Monday runner: cluster+score+analyze+publish
config/categories_traffic.example.yml # Committed example of category taxonomy
config/pipeline_config.example.yml    # Committed example of threshold config
supabase_migrations/
  002_traffic_pipeline.sql            # New columns on articles; new hot_topic_reports table
.github/workflows/traffic_daily.yml  # Daily (Tue–Sun) traffic buffer workflow

# Modified files
src/filter.py            # Add: normalise_traffic_title(), compute_jaccard(),
                         #      assign_category(), compute_quality_score()
src/analyzer.py          # Add: cluster_traffic_articles(), score_topic_buckets(),
                         #      select_hot_topics(), analyze_hot_topic()
src/storage.py           # Add: upsert_traffic_buffer(), get_traffic_buffer(),
                         #      upsert_hot_topic_report(), expire_buffer_articles()
src/publisher.py         # Add: publish_hot_topic_reports()
src/pipeline/traffic.py  # Modify: analyze() → no-op; publish() → calls upsert_traffic_buffer()
pages/traffic/index.html # Modify: add hot-topic reports section; retire individual-article list
pages/shared/app.js      # Modify: add renderHotTopics() (traffic-gated)
.github/workflows/weekly.yml  # Extend: add Monday buffer collection + weekly analysis steps
requirements.txt         # Add: jieba

# New test files
tests/unit/test_text_normaliser.py
tests/unit/test_jaccard.py
tests/unit/test_category_assign.py
tests/unit/test_topic_scoring.py
tests/integration/test_traffic_buffer.py
tests/integration/test_weekly_analysis.py
```

**Structure Decision**: Single project layout retained. New scripts follow the existing `scripts/` operational pattern. No new top-level directories introduced.
