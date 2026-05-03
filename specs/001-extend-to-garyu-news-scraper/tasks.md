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

- [x] T001 Create `config/sources_ffxiv.example.yml` with example entries for all three FFXIV source types: `rss` (Reddit), `html_patch` (Lodestone), and `html_forum` (forum.square-enix.com/ffxiv/forums/512-Japanese-Forums) — each with `content_type: "ffxiv"` and `enabled: false` by default
- [x] T002 [P] Create `db/supabase_migrations/002_add_content_type.sql` with `ALTER TABLE articles ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'traffic'` and a supporting index

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Apply the Supabase schema migration before any pipeline run that stores FFXIV articles.

**⚠️ CRITICAL**: No US3 storage validation can succeed until this phase is complete.

- [ ] T003 Apply `db/supabase_migrations/002_add_content_type.sql` in the Supabase SQL editor (Settings → SQL Editor → paste and run); confirm the `content_type` column exists in the `articles` table with default `'traffic'` and that existing rows are unaffected

**Checkpoint**: Supabase `articles` table has `content_type` column — user story implementation can now begin.

---

## Phase 3: User Story 1 — FFXIV Weekly Digest Collection (Priority: P1) 🎯 MVP

**Goal**: `collect_all()` returns articles tagged `content_type='ffxiv'` from Reddit RSS,
Lodestone HTML, and the Square Enix JP Forum thread listing. Traffic pipeline unchanged.

**Independent Test**: Run `python main.py` with `config/sources_ffxiv.yml` present and at
least one source enabled. Confirm log output shows FFXIV articles collected alongside traffic
articles, each with `content_type` field set correctly.

### Implementation for User Story 1

- [x] T004 [P] [US1] Implement `load_ffxiv_sources()` in `src/collector.py` — reads `config/sources_ffxiv.yml`; returns `[]` with a `logger.warning` if file absent (backward-compatible fallback); sets `content_type` on each article from the source's `content_type` config field (default `"ffxiv"`)
- [x] T005 [P] [US1] Implement `_fetch_html_patch(source: dict) -> list` in `src/collector.py` — fetches a Lodestone-style HTML news listing page; uses `source["selector"]` CSS selector via BeautifulSoup to extract items; reads `title_selector` (default `"a"`) and `link_attr` (default `"href"`); respects `max_items`; tags articles with `content_type: source["content_type"]`
- [x] T006 [P] [US1] Implement `_fetch_html_forum(source: dict) -> list` in `src/collector.py` — fetches the Square Enix vBulletin forum index page; extracts `<a>` tags whose `href` matches the `threads/[ID]-[SLUG]` pattern; builds article dict with `title` = link text, `link` = absolute URL, `summary = "[JP Forum] " + title`, `published = ""`; respects `max_items`; tags with `content_type: source["content_type"]`
- [x] T007 [US1] Register `"html_patch"` and `"html_forum"` in the `FETCHERS` dict and wire `load_ffxiv_sources()` into `collect_all()` in `src/collector.py` — FFXIV sources fetched after traffic sources; 1-second inter-source delay preserved (depends on T004, T005, T006)
- [x] T008 [US1] Add FFXIV content-type passthrough to `filter_and_deduplicate()` in `src/filter.py` — articles with `content_type == "ffxiv"` skip the `MUST_INCLUDE` motorcycle keyword check (they are already curated by source); `_is_stale_article` and deduplication hash logic apply to both types unchanged
- [x] T009 [US1] Update `src/main.py` — call `load_ffxiv_sources()` and merge returned articles into the pipeline; if `SOURCES_FFXIV_YML` env var is set, write it to `config/sources_ffxiv.yml` before loading (mirrors the pattern for `SOURCES_YML` in `weekly.yml`); graceful no-op if neither file nor env var present

**Checkpoint**: `python main.py` with FFXIV sources enabled produces articles tagged
`content_type='ffxiv'` in log output alongside traffic articles. US1 is fully functional
and testable independently.

---

## Phase 4: User Story 2 — FFXIV Knowledge Base Analysis (Priority: P2)

**Goal**: The AI analyzer uses `knowledge-base.md` terms when summarizing FFXIV articles.
No invented translations; unknown terms logged as `[KB MISS]`.

**Independent Test**: Run `python main.py` with one FFXIV article in the pipeline (or
call `analyze_article()` directly on a sample FFXIV dict). Confirm that the produced
`analysis["summary"]` uses terms from `knowledge-base.md`, and no `[KB MISS]` warnings
appear for common FFXIV 8.0 terms.

### Implementation for User Story 2

- [x] T010 [US2] Seed `knowledge-base.md` with ≥20 core FFXIV 8.0 term entries using the table format `| JP Term | TW Term | EN Term | Category | Notes |` — must include at minimum: 零式 (Savage), 絶討伐戦 (Ultimate), ノーマル (Normal), パッチ (Patch), ジョブ (Job), スキル (Skill), レイド (Raid), コンテンツ (Content), ボス (Boss), and key 8.0 jobs/roles (Viper, Pictomancer, etc.)
- [x] T011 [P] [US2] Implement `load_knowledge_base(path: str = "knowledge-base.md") -> dict` in `src/analyzer.py` — parse the markdown table; skip header and separator rows; return `{jp_term: {"tw": str, "en": str, "category": str}}` mapping; raise `RuntimeError` with a clear message if file is missing or contains 0 data rows; log entry count on success
- [x] T012 [P] [US2] Add `FFXIV_SYSTEM_PROMPT` and `FFXIV_ANALYSIS_TEMPLATE` constants to `src/analyzer.py` — system prompt frames the AI as an FFXIV information analyst writing in Traditional Chinese; analysis template includes a `{knowledge_base}` placeholder injected with condensed KB entries in the format `JP → TW (EN)`; output fields match existing traffic format (摘要/分析/重要性/重要性原因/標籤) for storage compatibility
- [x] T013 [US2] Add `content_type` dispatch to `analyze_article()` in `src/analyzer.py` — when `article["content_type"] == "ffxiv"`: call `load_knowledge_base()`, format KB as condensed reference block, insert into `FFXIV_ANALYSIS_TEMPLATE`; use `FFXIV_SYSTEM_PROMPT` instead of `SYSTEM_PROMPT`; FFXIV-specific tag pool used for 標籤 field (depends on T011, T012)
- [x] T014 [US2] Add `[KB MISS]` log warning in `src/analyzer.py` — after analysis completes for an FFXIV article, scan the raw Gemini response for JP-script terms not present in `knowledge-base.md` keys; log each at `logger.warning("[KB MISS] 未知詞彙：%s", term)` to flag knowledge base gaps

**Checkpoint**: User Stories 1 AND 2 both work independently — FFXIV articles are
collected and analyzed with correct Traditional Chinese terminology.

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

- [x] T015 [P] [US3] Add `"content_type": a.get("content_type", "traffic")` to the upsert row dict in `src/storage.py` `upsert_articles()` — no other storage logic changes required
- [x] T016 [P] [US3] Update `src/publisher.py` to render separate sections for traffic and FFXIV content — split incoming article list by `content_type`; output traffic section first, then FFXIV section; both sections use the same per-article rendering logic
- [x] T017 [P] [US3] Add `?content_type=` query parameter support to `workers/api/index.js` — if the parameter is present, append `&content_type=eq.<value>` to the Supabase REST query; if absent, omit the filter (returns all types, backwards compatible)
- [x] T018 [US3] Add `SOURCES_FFXIV_YML` injection step to `.github/workflows/weekly.yml` — insert immediately after the existing `SOURCES_YML` injection step: `echo "$SOURCES_FFXIV_YML" > config/sources_ffxiv.yml` with `env: SOURCES_FFXIV_YML: ${{ vars.SOURCES_FFXIV_YML }}`; step should be a no-op (empty file) if the variable is unset
- [x] T019 [P] [US3] Review `.github/workflows/deploy-pages.yml` — verify it references the correct Cloudflare Pages project name and deploy trigger; fix any broken `actions/checkout` version or missing secrets references
- [x] T020 [P] [US3] Review `.github/workflows/deploy-worker.yml` — verify it references the correct Cloudflare Worker name; fix any broken action versions or missing `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID` references

**Checkpoint**: All three user stories are fully functional — traffic and FFXIV articles
collected, analyzed, stored, and queryable independently via the Worker API.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation, robots.txt compliance, and knowledge base completeness.

- [x] T021 [P] Verify `www.ffxiv.com.tw/robots.txt` — if `/web/special/patchnote_log/` is not disallowed, add the TW patch log as an `html_patch` source in `config/sources_ffxiv.example.yml` with `enabled: true`; otherwise add with `enabled: false` and a comment explaining the restriction
- [ ] T022 End-to-end validation — trigger the GitHub Actions workflow manually (Actions → 台灣機車交通週報 → Run workflow); confirm: (a) run completes in ≤15 minutes, (b) Supabase contains both `content_type` values for the current `week_id`, (c) no `[KB MISS]` warnings for core 8.0 terms, (d) Worker responds correctly to `?content_type=ffxiv`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately; T001 and T002 are parallel
- **Foundational (Phase 2)**: Depends on T002 (migration SQL exists) — T003 unblocks US3 storage validation
- **US1 (Phase 3)**: Depends on T001 (example config to reference) — T004/T005/T006 are parallel; T007 depends on all three; T008/T009 can start after T007
- **US2 (Phase 4)**: Depends on US1 completion (need FFXIV articles in pipeline to test) — T011/T012 are parallel; T013 depends on both; T014 follows T013
- **US3 (Phase 5)**: Depends on T003 (migration applied) + US1 (articles have content_type) — T015/T016/T017/T019/T020 are parallel; T018 sequenced after T017 (Worker ready)
- **Polish (Phase 6)**: Depends on all user stories + T018 (workflow updated)

### User Story Dependencies

- **US1 (P1)**: Can start after Phase 1 — no dependency on US2 or US3
- **US2 (P2)**: Depends on US1 completion (FFXIV articles must flow through the pipeline)
- **US3 (P3)**: Depends on T003 (migration) + US1 (content_type on articles) — T015 and T016 can start after US1

### Within Each User Story

- US1: T004, T005, T006 in parallel → T007 → T008 and T009 in parallel
- US2: T010 in parallel with T011 and T012 → T013 → T014
- US3: T015, T016, T017, T019, T020 in parallel → T018

---

## Parallel Execution Examples

### User Story 1

```
# Launch T004, T005, T006 together (different functions, same file OK):
Task: "Implement load_ffxiv_sources() in src/collector.py"
Task: "Implement _fetch_html_patch() in src/collector.py"
Task: "Implement _fetch_html_forum() in src/collector.py"

# Then T007 (depends on above), then T008 and T009 together:
Task: "Register fetchers and wire FFXIV into collect_all() in src/collector.py"
--- after T007 ---
Task: "Add FFXIV passthrough to filter_and_deduplicate() in src/filter.py"
Task: "Update src/main.py to load and wire FFXIV sources"
```

### User Story 2

```
# Launch T010, T011, T012 together:
Task: "Seed knowledge-base.md with ≥20 FFXIV 8.0 terms"
Task: "Implement load_knowledge_base() in src/analyzer.py"
Task: "Add FFXIV_SYSTEM_PROMPT and FFXIV_ANALYSIS_TEMPLATE to src/analyzer.py"

# Then T013 (depends on T011 + T012), then T014:
Task: "Add content_type dispatch to analyze_article() in src/analyzer.py"
Task: "Add [KB MISS] log warning in src/analyzer.py"
```

### User Story 3

```
# Launch T015, T016, T017, T019, T020 together:
Task: "Add content_type to upsert row dict in src/storage.py"
Task: "Update src/publisher.py for dual content-type sections"
Task: "Add ?content_type= filter to workers/api/index.js"
Task: "Review and repair .github/workflows/deploy-pages.yml"
Task: "Review and repair .github/workflows/deploy-worker.yml"

# Then T018:
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
2. User Story 1 → FFXIV articles collected and flowing through pipeline (MVP)
3. User Story 2 → FFXIV articles analyzed with KB terminology
4. User Story 3 → Full storage + API + GitHub Actions automation

### Notes

- `[P]` tasks within the same phase act on different functions/files — safe to parallelize
- T003 is a manual Supabase operation, not a code change; do it once before any US3 validation
- T010 (seed knowledge-base.md) is content work, not code — can be done any time before T013
- All `src/collector.py` parallel tasks (T004–T006) touch different functions; no conflict
