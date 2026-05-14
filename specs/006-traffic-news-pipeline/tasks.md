# Tasks: Modular News Processing Engine

**Input**: Design documents from `specs/006-traffic-news-pipeline/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks in same phase)
- **[Story]**: User story this task belongs to (US1–US4)
- Exact file paths included in all task descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database migration, config example files, new dependency, and workflow skeletons. No story implementation yet.

- [X] T001 Write `supabase_migrations/002_traffic_pipeline.sql` — ALTER TABLE articles to add `major_category TEXT`, `initial_quality_score FLOAT4`, `buffered_at TIMESTAMPTZ`, `buffer_expires_at TIMESTAMPTZ`, `hot_topic_analyzed BOOLEAN DEFAULT FALSE`; CREATE TABLE `hot_topic_reports` (id UUID, week_start_date DATE, topic_label TEXT, report_text TEXT, source_article_count INT, source_article_links JSONB, cumulative_score FLOAT4, distinct_sources INT, distinct_days INT, created_at TIMESTAMPTZ, UNIQUE(week_start_date, topic_label)); CREATE INDEX idx_articles_traffic_buffer and idx_hot_topic_reports_week per data-model.md
- [X] T002 Apply `supabase_migrations/002_traffic_pipeline.sql` to the Supabase project via the SQL Editor dashboard
- [X] T003 [P] Add `jieba` to `requirements.txt`
- [X] T004 [P] Create `config/categories_traffic.example.yml` with the 6 seed categories from data-model.md (大型車安全, 酒駕, 道路施工, 行人事故, 路口安全, 機車事故) and their keyword lists
- [X] T005 [P] Create `config/pipeline_config.example.yml` with all default values from data-model.md (jaccard thresholds, topic_scoring, buffer.max_age_weeks, quality_score_weights, source_weights for 5 named outlets)
- [X] T006 [P] Create `config/jieba_userdict.example.txt` with seed entries: 台一線, 台九丙, 中山高, 北二高 (frequency 5, pos n); 3死, 3傷, 57歲, 2死1傷 (frequency 10, pos m)
- [X] T007 Add the four new config-write steps to `.github/workflows/weekly.yml` — write `CATEGORIES_TRAFFIC_YML`, `PIPELINE_CONFIG_YML`, `JIEBA_USERDICT_TXT` to their respective `config/` paths (follow the identical pattern used for `SOURCES_TRAFFIC_YML`)

**Checkpoint**: Migration applied; example config files committed; weekly.yml updated

---

## Phase 2: Foundation / User Story 4 — Shared Text Normalisation (P2)

**Purpose**: All three remaining user stories (US1, US2, US3) depend on `normalise_title()`, `compute_jaccard()`, `assign_category()`, and `compute_quality_score()`. This phase must be complete before Phase 3 or Phase 4 can begin.

**Goal**: Every article title can be reduced to a normalised token set; two token sets can be compared via Jaccard similarity; a traffic article can be assigned a major category.

**Independent Test**: Run `pytest tests/unit/test_text_normaliser.py tests/unit/test_jaccard.py tests/unit/test_category_assign.py` and all pass without any DB connection.

- [X] T008 Create `src/pipeline_config.py` with `load_pipeline_config(path) → dict` and `load_category_taxonomy(path) → dict` — validate weight sum ≈ 1.0, validate thresholds in [0,1], raise `RuntimeError` with actionable message on parse failure or invalid values; load jieba userdict if `JIEBA_USERDICT_TXT` env var is set (log warning if missing, do not halt)
- [X] T009 [P] [US4] Implement `normalise_title(title: str) → set[str]` in `src/filter.py` — strip patterns `【…】`, `（…）`, `[…]`; remove trailing journalist attribution and "相關報導" / "連結" suffixes; convert full-width digits (０–９) to half-width; convert Chinese numeral words (一二三四五六七八九十百千) to Arabic; tokenise with jieba; return frozenset of tokens with length ≥ 2
- [X] T010 [P] [US4] Implement `compute_jaccard(set_a: set, set_b: set) → float` in `src/filter.py` — returns `len(a & b) / len(a | b)`; returns 0.0 if either set is empty
- [X] T011 [US4] Implement `assign_category(title_tokens: set, taxonomy: dict) → str` in `src/filter.py` — iterates taxonomy in definition order; returns first category label whose keyword list has any intersection with title_tokens; returns `'uncategorised'` if no match
- [X] T012 [US4] Implement `compute_quality_score(article: dict, category_keywords: list, config: dict) → float` in `src/filter.py` — formula: `(kw_match_ratio × w1) + (min(word_count, 500)/500 × w2) + (source_weight × w3)` where weights and source_weights are read from config; clamp result to [0.0, 1.0]
- [X] T013 [P] [US4] Write `tests/unit/test_text_normaliser.py` — test cases: (a) title with 【記者X報導】 → stripped; (b) ２０２５ → 2025; (c) 三人 → 3人 token present; (d) "3死57歲" preserved as single tokens; (e) empty string → empty set
- [X] T014 [P] [US4] Write `tests/unit/test_jaccard.py` — test cases: (a) identical sets → 1.0; (b) disjoint sets → 0.0; (c) 50% overlap → 0.333; (d) empty set A → 0.0; (e) boundary: score exactly at 0.45 threshold
- [X] T015 [P] [US4] Write `tests/unit/test_category_assign.py` — test cases: (a) title with '大型車' → '大型車安全'; (b) title with no keywords → 'uncategorised'; (c) title matching two categories → first wins (priority order)

**Checkpoint**: `pytest tests/unit/` passes; `normalise_title`, `compute_jaccard`, `assign_category`, `compute_quality_score` are importable and tested

---

## Phase 3: User Story 2 — Daily Game News Feed (P1)

**Goal**: After each FFXIV crawl, the pipeline produces at most 20 unique game articles with no near-duplicate or substring-duplicate titles.

**Independent Test**: Seed `filter_and_deduplicate()` with 40 FFXIV articles containing known duplicates; assert output ≤ 20 entries; assert no pair has Jaccard > 0.50 or title-inclusion relationship.

> **Note**: Phases 3 and 4 can be implemented in parallel as they touch different files.

- [X] T016 [US2] Update `FFXIVCategory.max_articles` from `10` to `20` in `src/pipeline/ffxiv.py` (FR-010 specifies 20-article cap)
- [X] T017 [US2] Add `game_deduplicate(articles: list, config: dict) → list` function to `src/filter.py` — for each candidate article: (1) compute `normalise_title()` token set; (2) discard if token set is subset of any retained article's token set (inclusion check, FR-008); (3) discard if `compute_jaccard()` against any retained article exceeds `config.jaccard.game_threshold` (FR-009); retain otherwise; return retained articles newest-first, capped at 20
- [X] T018 [US2] Update `FFXIVCategory.filter()` in `src/pipeline/ffxiv.py` to call `game_deduplicate(after_freshness, config)` as the final deduplication step, replacing the bare `[:self.max_articles]` slice
- [X] T019 [P] [US2] Write `tests/unit/test_game_deduplicate.py` — test cases: (a) inclusion check: "FFXIV 更新" is subset of "FFXIV 7.2 更新" → shorter discarded; (b) Jaccard > 0.50 → duplicate discarded; (c) 25 unique articles → capped at 20; (d) all unique articles ≤ 20 → all retained
- [X] T020 [US2] Write `tests/integration/test_game_feed.py` — load `config/pipeline_config.example.yml`; seed 40 articles with 15 known duplicate pairs; run `game_deduplicate()`; assert result ≤ 20; assert no duplicate pairs remain

**Checkpoint**: FFXIV pipeline passes integration test; game feed dedup is live in `FFXIVCategory.filter()`

---

## Phase 4: User Story 3 — Traffic Topic Clustering (P2)

**Goal**: A pool of normalised traffic articles can be grouped into topic buckets by Jaccard similarity, scored by composite metric, and ranked so the top 1–3 qualifying buckets can be identified.

**Independent Test**: Call `cluster_traffic_articles()` + `score_topic_buckets()` + `select_hot_topics()` on a fixed fixture set; verify bucket membership, score ordering, and threshold filtering without any DB or Gemini calls.

> **Note**: This phase can run in parallel with Phase 3. Phase 5 (US1) depends on this phase completing first.

- [X] T021 [US3] Implement `cluster_traffic_articles(articles: list, config: dict) → dict[str, list]` in `src/analyzer.py` — (1) group articles by `major_category`; (2) within each category group, iterate articles and assign to an existing bucket if any bucket member has Jaccard score in [0.20, 0.45] with the candidate (FR-014); start a new bucket otherwise; (3) for pairs with Jaccard > 0.45, keep only the higher-word-count article (FR-013); return `{bucket_id: [article_dicts]}`
- [X] T022 [US3] Implement `score_topic_buckets(buckets: dict, config: dict) → dict[str, float]` in `src/analyzer.py` — for each bucket: `score = sum(a['initial_quality_score'] for a in bucket) × log(distinct_sources + 1) × log(distinct_days + 1)` where distinct_sources = count of unique `source` values, distinct_days = count of unique `published` dates (date part only); return `{bucket_id: score}`
- [X] T023 [US3] Implement `select_hot_topics(bucket_scores: dict, config: dict) → list[str]` in `src/analyzer.py` — filter bucket_ids where score >= `config.topic_scoring.min_threshold`; sort by score descending; return at most `config.topic_scoring.max_hot_topics` bucket_ids
- [X] T024 [P] [US3] Write `tests/unit/test_topic_scoring.py` — test cases: (a) two articles with Jaccard 0.25 → same bucket; (b) two articles with Jaccard 0.50 → dedup, lower word count discarded; (c) bucket with 10 articles from 1 source scores lower than bucket with 5 articles from 3 sources (validates log diversity factor); (d) buckets below `min_threshold` are excluded by `select_hot_topics()`

**Checkpoint**: `pytest tests/unit/test_topic_scoring.py` passes; clustering and scoring functions are importable from `src/analyzer.py`

---

## Phase 5: User Story 1 — Monday Traffic Insight (P1)

**Goal**: Every Monday at 08:00 TST, the top 1–3 qualified traffic topics receive a Gemini deep-analysis report stored in `hot_topic_reports` and displayed on the traffic frontend. Daily (Tue–Sun) traffic articles are silently buffered without publishing.

**Independent Test**: Seed Supabase with one week of traffic articles across 2+ categories; run `scripts/traffic_weekly_analysis.py` manually; verify `hot_topic_reports` rows exist, source articles have `hot_topic_analyzed = TRUE`, and the traffic page renders the reports.

### Traffic Buffer — Daily Phase

- [X] T025 [US1] Modify `TrafficCategory.analyze()` in `src/pipeline/traffic.py` to be a no-op — return `articles` unchanged; remove the `from src.analyzer import analyze_all` call; add comment explaining traffic analysis is deferred to weekly phase
- [X] T026 [US1] Modify `TrafficCategory.filter()` in `src/pipeline/traffic.py` — after existing freshness + dedup filtering, call `normalise_title()`, `assign_category()`, `compute_quality_score()` on each retained article; attach results as `article['major_category']`, `article['initial_quality_score']`, `article['token_set']`
- [X] T027 [US1] Modify `TrafficCategory.publish()` in `src/pipeline/traffic.py` to call `upsert_traffic_buffer(articles, week_id)` from `src/storage.py` instead of `publisher.publish()` — compute `week_id` using the same ISO week pattern already in `storage.py`
- [X] T028 [US1] Add `upsert_traffic_buffer(articles: list, week_id: str) → int` to `src/storage.py` — upserts rows to `articles` table with `content_type='traffic'`, sets `major_category`, `initial_quality_score`, `buffered_at=NOW()`, `buffer_expires_at=NOW() + 8 weeks`, `hot_topic_analyzed=FALSE`; uses existing `content_fingerprint` as stable key; returns count written
- [X] T029 [US1] Create `scripts/traffic_buffer.py` — thin runner that instantiates `TrafficCategory`, calls `collect()` → `filter()` → `publish()` (now buffer write); logs article count and any errors; exits non-zero on exception (Principle I: no silent failures)

### Traffic Buffer — Storage Queries

- [X] T030 [US1] Add `get_traffic_buffer(max_age_weeks: int) → list` to `src/storage.py` — queries articles where `content_type='traffic'`, `hot_topic_analyzed=FALSE`, `buffer_expires_at > NOW()`; orders by `published` descending; returns list of dicts with all article columns
- [X] T031 [US1] Add `expire_buffer_articles() → int` to `src/storage.py` — deletes articles where `content_type='traffic'`, `hot_topic_analyzed=FALSE`, `buffer_expires_at < NOW()`; returns count deleted; logs result

### Weekly Analysis — Core Logic

- [X] T032 [US1] Add `analyze_hot_topic(bucket_articles: list, topic_label: str, week_start_date: str) → str` to `src/analyzer.py` — selects top 5–10 articles from bucket by `initial_quality_score`; builds Gemini prompt containing topic label + article titles + first 200 chars of each article body; calls Gemini API with traffic analyst system prompt (繁體中文, community sentiment + international standards angle); returns report text string; respects existing 2.5-second inter-request delay
- [X] T033 [US1] Add `upsert_hot_topic_report(report: dict) → None` to `src/storage.py` — upserts one row to `hot_topic_reports` using `(week_start_date, topic_label)` as conflict key; after successful upsert, marks all source articles as `hot_topic_analyzed=TRUE` by updating `articles` table where `content_fingerprint` is in `report['source_article_links']`
- [X] T034 [US1] Create `scripts/traffic_weekly_analysis.py` with `main()` function — sequence: (1) load config; (2) `expire_buffer_articles()`; (3) `articles = get_traffic_buffer(config.buffer.max_age_weeks)`; (4) halt with logged reason if `len(articles) < 3` (FR-020); (5) `buckets = cluster_traffic_articles(articles, config)`; (6) `scores = score_topic_buckets(buckets, config)`; (7) `hot_topic_ids = select_hot_topics(scores, config)`; (8) for each: call `analyze_hot_topic()` then `upsert_hot_topic_report()`; (9) call `publish_hot_topic_reports()`; add error handling for Gemini failure (log, skip remaining topics, do not crash)

### Weekly Analysis — Publishing

- [X] T035 [US1] Add `publish_hot_topic_reports(reports: list) → None` to `src/publisher.py` — writes reports as JSON to `pages/traffic/hot_topics.json` (consumed by frontend); triggers Cloudflare Pages traffic deployment via the same mechanism used by the existing `publish()` function
- [X] T036 [US1] Update `pages/traffic/index.html` — add `<section id="hot-topics">` between the page header and the existing week-nav; add loading/empty-state messaging ("本週熱點話題尚未產生" when reports array is empty)
- [X] T037 [US1] Add `renderHotTopics(reports)` to `pages/shared/app.js` — traffic-gated (`if (C.contentType === 'traffic')`); renders one card per report (topic_label as heading, report_text as body, source_article_count + distinct_sources as metadata); call from existing page-init flow after hot_topics.json fetch

### Cloudflare Worker API

- [X] T038 [US1] Add `GET /api/hot-topics` handler to `workers/api/` — query `hot_topic_reports` ordered by `week_start_date DESC, cumulative_score DESC`; accept optional `?week=` query param; return JSON per `contracts/api-hot-topics.md`; return `{"reports": []}` (not 404) for weeks with no data

### GitHub Actions Scheduling

- [X] T039 [US1] Create `.github/workflows/traffic_daily.yml` — cron `0 0 * * 2-7` (Tue–Sun UTC 00:00 = TST 08:00); steps: checkout → write config files from env vars (CATEGORIES_TRAFFIC_YML, PIPELINE_CONFIG_YML, JIEBA_USERDICT_TXT) → setup Python 3.11 → pip install → run `scripts/traffic_buffer.py`; use same secrets as `weekly.yml`
- [X] T040 [US1] Extend `.github/workflows/weekly.yml` with two new steps appended after the existing `main.py` run and before the Cloudflare deploy steps — Step A: "收集週一交通新聞 buffer" runs `scripts/traffic_buffer.py`; Step B: "週交通熱點分析" runs `scripts/traffic_weekly_analysis.py`; both steps use the same env secrets block as the main.py step

### Integration Tests

- [X] T041 [P] [US1] Write `tests/integration/test_traffic_buffer.py` — seed 5 traffic articles; run `TrafficCategory.collect() → filter() → publish()`; query Supabase; assert `major_category` is not NULL, `initial_quality_score` is in [0,1], `buffered_at` is set, `hot_topic_analyzed = FALSE`
- [X] T042 [P] [US1] Write `tests/integration/test_weekly_analysis.py` — pre-seed ≥ 3 buffered traffic articles across 2 categories; run `scripts/traffic_weekly_analysis.py`; assert ≥ 1 row in `hot_topic_reports`; assert those source articles now have `hot_topic_analyzed = TRUE`

**Checkpoint**: Run `scripts/traffic_buffer.py` locally → verify Supabase buffer rows. Run `scripts/traffic_weekly_analysis.py` → verify `hot_topic_reports` rows and traffic page renders reports.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Workflow hardening, gitignore, and validation run.

- [X] T043 Add `config/categories_traffic.yml`, `config/pipeline_config.yml`, `config/jieba_userdict.txt` (the non-example real files) to `.gitignore`
- [X] T044 [P] Verify `config/*.example.yml` and `config/jieba_userdict.example.txt` are tracked by git (run `git status` and confirm they appear as untracked or modified, not ignored)
- [X] T045 [P] Add `PIPELINE_CONFIG_YML` and `JIEBA_USERDICT_TXT` as GitHub Environment Variables (or Secrets) in the repository settings with the contents of their respective `.example` files as initial values
- [X] T046 Run full unit test suite: `pytest tests/unit/ -v` — all tests pass
- [ ] T047 [P] Run `scripts/traffic_buffer.py` in local dev mode and verify output matches quickstart.md expected log lines
- [ ] T048 Run `scripts/traffic_weekly_analysis.py` in local dev mode with seeded buffer data and verify a `hot_topic_reports` row is created

**Checkpoint**: All tests pass; both scripts run cleanly locally; config files are properly gitignored with examples committed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundation/US4)**: Depends on Phase 1 completion — blocks all user story phases
- **Phase 3 (US2 Game Feed)**: Depends on Phase 2 — can run in parallel with Phase 4
- **Phase 4 (US3 Clustering)**: Depends on Phase 2 — can run in parallel with Phase 3; **blocks Phase 5**
- **Phase 5 (US1 Traffic Insight)**: Depends on Phase 4 completion (clustering functions must exist)
- **Phase 6 (Polish)**: Depends on Phases 3, 4, and 5

### User Story Dependencies

- **US4 (Normalisation)** → in Foundation; blocks US1, US2, US3
- **US2 (Game Feed)** → depends on Foundation only; independent of US1 and US3
- **US3 (Clustering)** → depends on Foundation; is a prerequisite for US1
- **US1 (Traffic Insight)** → depends on US3 (clustering) and Foundation (normalisation)

### Within Phase 5 (US1) — Recommended Order

1. T025–T029 (modify TrafficCategory + upsert_traffic_buffer + daily runner)
2. T030–T031 (buffer read + expire queries in storage.py)
3. T032–T034 (analyze_hot_topic + upsert_report + weekly runner)
4. T035–T037 (publish_hot_topic_reports + frontend)
5. T038 (API endpoint)
6. T039–T040 (GitHub Actions workflows) — can be done in parallel with T035–T038
7. T041–T042 (integration tests)

---

## Parallel Opportunities

### Phase 1

All of T003, T004, T005, T006 can run in parallel (different files).

### Phase 2 (Foundation/US4)

After T008 (pipeline_config.py), T009, T010, T011 can run in parallel.
T013, T014, T015 (unit tests) can all run in parallel after their targets exist.

### Phase 3 + Phase 4

These entire phases can run in parallel (touch different files: Phase 3 edits `ffxiv.py` and game dedup; Phase 4 edits `analyzer.py` clustering/scoring).

### Phase 5

T041 and T042 (integration tests) can be written in parallel while runners are being built.
T039 and T040 (workflow files) can be created in parallel with T035–T038 (publish + frontend + API).

---

## Implementation Strategy

### MVP Scope (US1 only — end-to-end traffic pipeline)

1. Phase 1 (Setup) → Phase 2 (Foundation) → Phase 4 (US3 Clustering) → Phase 5 (US1 Traffic Insight)
2. Skip Phase 3 (US2 Game Feed) for the first deliverable
3. **Validate**: Run `scripts/traffic_weekly_analysis.py` manually; check `hot_topic_reports` in Supabase; verify traffic page renders
4. Add Phase 3 (US2 Game Feed) as a follow-on

### Full Delivery Order

1. Phase 1 → Phase 2 (serial, both are fast)
2. Phase 3 + Phase 4 in parallel
3. Phase 5 (US1, largest phase)
4. Phase 6 (polish)

**Total tasks**: 48
**Parallelizable tasks**: 22 marked [P]
**Phases**: 6
