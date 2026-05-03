---
description: "Tasks for FFXIV Integration into Garyu News Scraper"
---

# Tasks: Extend to Garyu News Scraper (FFXIV Integration)

**Input**: Design documents from `specs/001-extend-to-garyu-news-scraper/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: No test suite exists in this project. Verification is via manual run and GitHub Actions.

**Organization**: Tasks are grouped by user story to enable independent implementation and
testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Create new config files and schema migration that all stories depend on.

- [x] T001 Create `config/sources_ffxiv.example.yml` with example entries for all three FFXIV source types: `rss` (Reddit), `html_patch` (Lodestone), `html_forum` (forum.square-enix.com/ffxiv/forums/512-Japanese-Forums), and `html_patch` (www.ffxiv.com.tw TW patch log) — each with `content_type: "ffxiv"` and `enabled: false`
- [x] T002 [P] Create `db/supabase_migrations/002_add_content_type.sql` with `ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'traffic'` and a supporting index

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Apply the Supabase schema migration before any pipeline run that stores FFXIV articles.

**⚠️ CRITICAL**: No US3 storage validation can succeed until this phase is complete.

- [x] T003 Apply `db/supabase_migrations/002_add_content_type.sql` in the Supabase SQL editor (Settings → SQL Editor → paste and run); confirm the `content_type` column exists in the `articles` table with default `'traffic'` and that existing rows are unaffected

**Checkpoint**: Supabase `articles` table has `content_type` column — user story implementation can now begin.

---

## Phase 3: User Story 1 — FFXIV Weekly Digest Collection (Priority: P1) 🎯 MVP

**Goal**: `collect_all()` returns articles tagged `content_type='ffxiv'` from Reddit RSS,
Lodestone HTML, and the Square Enix JP Forum thread listing. Traffic pipeline unchanged.

**Independent Test**: Run `python main.py` with `config/sources_ffxiv.yml` present and at
least one source enabled. Confirm log output shows FFXIV articles collected alongside traffic
articles, each with `content_type` field set correctly.

### Implementation for User Story 1

- [x] T004 [P] [US1] Implement `load_ffxiv_sources()` in `src/collector.py` — reads `config/sources_ffxiv.yml`; falls back to `[]` with a warning if file absent; supports env-var `SOURCES_FFXIV_YML` → file write pattern (mirrors traffic SOURCES_YML flow)
- [x] T005 [P] [US1] Implement `_fetch_html_patch(source: dict) -> list` in `src/collector.py` — fetches a Lodestone-style HTML news listing page; uses `source["selector"]` CSS selector via BeautifulSoup; reads `title_selector` (default `"a"`) and `max_items`; tags articles with `content_type` from source config
- [x] T006 [P] [US1] Implement `_fetch_html_forum(source: dict) -> list` in `src/collector.py` — fetches Square Enix vBulletin forum index; extracts `<a>` tags whose `href` matches `threads/[ID]-[SLUG]`; sets `summary = "[JP Forum] " + title`; respects `max_items`; tags with `content_type` from source config (NOTE: per-subforum RSS rejected — delivers first post only)
- [x] T007 [US1] Register `"html_patch"` and `"html_forum"` in the `FETCHERS` dict and wire `load_ffxiv_sources()` into `collect_all()` in `src/collector.py` — FFXIV sources fetched after traffic sources; 1-second inter-source delay preserved (depends on T004, T005, T006)
- [x] T008 [US1] Add FFXIV content-type passthrough to `filter_and_deduplicate()` in `src/filter.py` — articles with `content_type == "ffxiv"` skip the `MUST_INCLUDE` motorcycle keyword check; stale detection and deduplication hash logic apply to both types unchanged
- [x] T009 [US1] Update `src/main.py` — merge FFXIV sources into pipeline; update log banner to "Garyu News Scraper"

**Checkpoint**: `python main.py` with FFXIV sources enabled produces articles tagged
`content_type='ffxiv'` in log output alongside traffic articles. US1 fully functional
and independently testable.

---

## Phase 4: User Story 2 — FFXIV Knowledge Base Analysis (Priority: P2)

**Goal**: The AI analyzer uses `knowledge-base.md` terms when summarising FFXIV articles.
Unknown terms appear as `[[term]]` in the output, are logged as `[KB MISS]`, and a
post-run prompt lists them for the user to review.

**Independent Test**: Run `python main.py` with one FFXIV article in the pipeline (or
call `analyze_article()` directly on a sample FFXIV dict). Confirm the produced
`analysis["summary"]` uses terms from `knowledge-base.md`; unknown terms appear wrapped
in `[[term]]`; post-run summary lists any flagged terms.

### Implementation for User Story 2

- [x] T010 [US2] Seed `knowledge-base.md` with ≥20 core FFXIV 8.0 term entries: all 22 jobs (JP term + EN abbreviation rows for bidirectional lookup), content types, roles, features, and two expansion names — sourced from https://www.ffxiv.com.tw/web/intro/guide/battle/
- [x] T011 [P] [US2] Implement `load_knowledge_base(path: str = "knowledge-base.md") -> dict` in `src/analyzer.py` — parse markdown table; skip header/separator rows; return `{jp_term: {"tw": str, "en": str, "category": str}}`; raise `RuntimeError` if file missing or 0 data rows; module-level cache via `_KB_CACHE`
- [x] T012 [P] [US2] Add `FFXIV_SYSTEM_PROMPT`, `FFXIV_DEFAULT_TAGS`, and `FFXIV_ANALYSIS_TEMPLATE` constants to `src/analyzer.py` — template includes `{knowledge_base}` placeholder and the `[[term]]` rule instruction: "若遇到知識庫中未列出的日文術語，請直接保留原文，並以 [[術語]] 格式包覆"
- [x] T013 [US2] Add `content_type` dispatch to `analyze_article()` in `src/analyzer.py` — when `article["content_type"] == "ffxiv"`: call `load_knowledge_base()`, format KB as table block, insert into `FFXIV_ANALYSIS_TEMPLATE`; use `FFXIV_SYSTEM_PROMPT`; FFXIV tag pool used for 標籤 field (depends on T011, T012)
- [x] T014 [US2] Update `_check_kb_misses()` in `src/analyzer.py` — detect both `[[term]]`-marked unknowns (model followed the rule) and bare katakana sequences (≥3 chars, fallback scan); accumulate all misses into `_KB_MISS_ACCUMULATOR` module-level set; log each as `[KB MISS]`
- [x] T015 [P] [US2] Add `_KB_MISS_ACCUMULATOR: set`, `_KB_HIGHLIGHT` regex, and `get_kb_miss_summary() -> list` to `src/analyzer.py` — public function returns sorted list of all flagged terms from the current run
- [x] T016 [US2] Add post-run KB review prompt to `src/main.py` — after `publish()`, call `get_kb_miss_summary()`; if non-empty, log a warning block listing each term and prompt user to update `knowledge-base.md` (FR-009)
- [x] T017 [P] [US2] Correct all TW job names in `knowledge-base.md` to match official TW site — key fixes: ヴァイパー→毒蛇劍士, リーパー→奪魂者, ナイト→騎士, 占星術士TW→占星術師, 白/黑/赤魔→道士 suffix; add all 22 job rows + 22 abbreviation rows for bidirectional lookup; fix パッチ→版本更新, ハウジング→住宅, アライアンスレイド→24人本, ヒーラー→補師, フリーカンパニー→FC, ゴールドソーサー→金碟, 黄金のレガシー→黃金的遺產, コンテンツファインダー→CF; add グランドカンパニー→GC

**Checkpoint**: US1 and US2 both work independently — FFXIV articles collected and
analysed with correct Traditional Chinese terminology; unknown terms flagged with `[[]]`.

---

## Phase 5: User Story 3 — Dual-Content Storage & API (Priority: P3)

**Goal**: Both content types stored in Supabase with `content_type` column; Cloudflare
Worker API supports `?content_type=` filtering; GitHub Actions workflow injects
`SOURCES_FFXIV_YML`.

**Independent Test**: After a full pipeline run, query Supabase for the current `week_id`
and confirm rows with `content_type='traffic'` AND `content_type='ffxiv'` both exist.
Query the deployed Worker with `?content_type=ffxiv` and confirm only FFXIV articles
are returned.

### Implementation for User Story 3

- [x] T018 [P] [US3] Add `"content_type": a.get("content_type", "traffic")` to the upsert row dict in `src/storage.py` `upsert_articles()`
- [x] T019 [P] [US3] Update `src/publisher.py` — split week HTML into traffic and FFXIV sections; extract card rendering into `_build_card()`; add FFXIV purple type-badge; update header to show per-type counts
- [x] T020 [P] [US3] Add `?content_type=` query parameter filter to `workers/api/src/index.js` — add `CONTENT_TYPE_VALUES` constant; filter `normalized` array when param present; expose `content_type` field in `normalizeRow()`; include `content_type` in Supabase SELECT
- [x] T021 [US3] Add `SOURCES_FFXIV_YML` injection step to `.github/workflows/weekly.yml` — insert after existing `SOURCES_YML` step; step is conditional on `vars.SOURCES_FFXIV_YML != ''` (no-op when variable unset; backwards compatible)
- [x] T022 [P] [US3] Review `.github/workflows/deploy-pages.yml` — verified correct: `actions/checkout@v5`, `cloudflare/pages-action@v1`, deploys `pages/` to `traffic-issue-scraper` project; no changes required
- [x] T023 [P] [US3] Review `.github/workflows/deploy-worker.yml` — verified correct: `cloudflare/wrangler-action@v3`, correct secrets wiring; no changes required

**Checkpoint**: All three user stories fully functional — traffic and FFXIV articles
collected, analysed, stored, and queryable independently via the Worker API.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Compliance verification, knowledge base integrity, and end-to-end validation.

- [x] T024 [P] Verify `www.ffxiv.com.tw/robots.txt` (returned HTTP 404 — no restrictions); add TW patch log as disabled `html_patch` source in `config/sources_ffxiv.example.yml`; update `specs/001-extend-to-garyu-news-scraper/research.md` with finding
- [x] T025 [P] Fix pipeline truncation — split `main.py` into per-category filter+budget: traffic capped at 20, FFXIV at 10; merged before `analyze_all()`; removes the `filtered[:30]` that silently discarded all FFXIV articles
- [ ] T026 End-to-end validation — trigger GitHub Actions workflow manually (Actions → Garyu News Scraper 週報 → Run workflow); confirm: (a) run completes in ≤15 minutes, (b) Supabase contains both `content_type` values for the current `week_id`, (c) no `[KB MISS]` warnings for core 8.0 terms in `knowledge-base.md`, (d) Worker responds correctly to `?content_type=ffxiv`, (e) both content types appear in the published HTML

---

## Phase 7: Future — Modular Pipeline Architecture (Planned, Not Yet Scheduled)

**Purpose**: Refactor the pipeline so each news category is a fully independent,
self-contained unit. Main orchestrates; individual modules own their collect/filter/
analyze/publish logic. Enables new categories (anime, cycling, etc.) without touching
existing code.

**Prerequisite**: T026 validated in production. Design this spec before starting implementation.

### Abstract Plan

- [ ] T027 Create `specs/002-modular-pipeline/` feature spec — define the per-category
  pipeline abstraction: each category module exposes `collect() -> list`,
  `filter(raw) -> list`, `analyze(articles) -> list`, `publish(articles, output_dir)`
  and a `config: CategoryConfig` (name, max_articles, output_dir, content_type)
- [ ] T028 [P] Design `src/pipeline/base.py` — abstract `Category` protocol/dataclass:
  `name`, `max_articles`, `output_dir`, `content_type`; `run() -> list[Article]` orchestrates
  the four stages; `main.py` iterates registered categories
- [ ] T029 [P] Design `src/pipeline/traffic.py` and `src/pipeline/ffxiv.py` — each implements
  the `Category` protocol, wrapping existing collector/filter/analyzer logic; no logic
  duplication — shared utilities stay in `src/`
- [ ] T030 [P] Design publisher parameterisation — `publish(articles, output_dir='pages/')`
  so traffic writes to `pages/`, FFXIV to `pages-ffxiv/`; each maps to its own CF Pages
  project and deploy workflow
- [ ] T031 Update GitHub Actions — add `deploy-pages-ffxiv.yml` deploying `pages-ffxiv/`
  to a second CF Pages project; traffic workflow unchanged
- [ ] T032 Run `/speckit-plan` for `specs/002-modular-pipeline/` to produce full research,
  data-model, contracts, and implementation plan before any code change

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 and T002 are parallel
- **Foundational (Phase 2)**: Depends on T002 — T003 unblocks US3 storage validation
- **US1 (Phase 3)**: Depends on T001 — T004/T005/T006 parallel; T007→T008/T009
- **US2 (Phase 4)**: Depends on US1 completion — T010/T011/T012/T015 parallel; T013→T014→T016; T017 parallel
- **US3 (Phase 5)**: Depends on T003 + US1 — T018/T019/T020/T022/T023 parallel; T021 after T020
- **Polish (Phase 6)**: Depends on all user stories + T021

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 1 — no dependency on US2 or US3
- **US2 (P2)**: Depends on US1 completion (FFXIV articles must flow through the pipeline first)
- **US3 (P3)**: Depends on T003 (migration) + US1 (articles have content_type)

### Within Each User Story

- US1: T004, T005, T006 in parallel → T007 → T008 and T009 in parallel
- US2: T010, T011, T012, T015 in parallel → T013 → T014 → T016; T017 parallel throughout
- US3: T018, T019, T020, T022, T023 in parallel → T021

---

## Parallel Execution Examples

### User Story 1

```
# T004, T005, T006 together (different functions, same file — no conflict):
Task: "Implement load_ffxiv_sources() in src/collector.py"
Task: "Implement _fetch_html_patch() in src/collector.py"
Task: "Implement _fetch_html_forum() in src/collector.py"

# Then T007, then T008 + T009 together:
Task: "Register fetchers and wire FFXIV into collect_all()"
--- after T007 ---
Task: "Add FFXIV passthrough to filter_and_deduplicate() in src/filter.py"
Task: "Update src/main.py to load and wire FFXIV sources"
```

### User Story 2

```
# T010, T011, T012, T015 together:
Task: "Seed knowledge-base.md with ≥20 FFXIV 8.0 terms + job abbreviations"
Task: "Implement load_knowledge_base() in src/analyzer.py"
Task: "Add FFXIV_SYSTEM_PROMPT and FFXIV_ANALYSIS_TEMPLATE to src/analyzer.py"
Task: "Add _KB_MISS_ACCUMULATOR and get_kb_miss_summary() to src/analyzer.py"

# Then T013 (depends on T011 + T012), then T014, then T016:
Task: "Add content_type dispatch to analyze_article() in src/analyzer.py"
Task: "Update _check_kb_misses() for [[term]] detection + accumulation"
Task: "Add post-run KB review prompt to src/main.py"
```

### User Story 3

```
# T018, T019, T020, T022, T023 together:
Task: "Add content_type to upsert row dict in src/storage.py"
Task: "Update src/publisher.py for dual content-type sections"
Task: "Add ?content_type= filter to workers/api/src/index.js"
Task: "Review and confirm .github/workflows/deploy-pages.yml"
Task: "Review and confirm .github/workflows/deploy-worker.yml"

# Then T021:
Task: "Add SOURCES_FFXIV_YML injection to .github/workflows/weekly.yml"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003) — apply migration
3. Complete Phase 3: User Story 1 (T004–T009)
4. **STOP and VALIDATE**: Run `python main.py` locally; confirm FFXIV articles collected
5. Traffic pipeline regression check: confirm no traffic articles lost

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. User Story 1 → FFXIV articles flowing through pipeline (MVP)
3. User Story 2 → FFXIV articles analysed with KB terminology + [[term]] flagging
4. User Story 3 → Full storage + API + GitHub Actions automation

### Notes

- `[P]` tasks within the same phase act on different functions/files — safe to parallelise
- T003 is a manual Supabase operation, not a code change — do it once before US3 validation
- T017 (KB corrections) is content work — can be done any time before a production run
- All `src/collector.py` parallel tasks (T004–T006) touch different functions; no conflict
- JP Forum per-subforum RSS intentionally excluded: only delivers first post per thread
