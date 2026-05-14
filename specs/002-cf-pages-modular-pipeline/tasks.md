---
description: "Tasks for Separate CF Pages + Modular Pipeline"
---

# Tasks: Separate CF Pages + Modular Pipeline

**Input**: Design documents from `specs/002-cf-pages-modular-pipeline/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: No automated test suite exists in this project. Verification is via local `python main.py` and manual GitHub Actions run.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

---

## Phase 1: Setup

**Purpose**: Create the `src/pipeline/` package directory that US2 tasks depend on.

- [x] T001 Create `src/pipeline/__init__.py` as an empty file to register the package

---

## Phase 2: User Story 1 — Separate CF Pages per Content Type (Priority: P1) 🎯 MVP

**Goal**: Traffic articles publish to `pages/traffic/` (migrated from existing `pages/`); FFXIV articles publish to `pages/ffxiv/` (new). Each site deploys independently via its own GitHub Actions workflow.

**Independent Test**: Run `python main.py` locally with both source configs. Confirm `pages/traffic/` contains only traffic articles and `pages/ffxiv/` contains only FFXIV articles. No regressions in the traffic output content.

### Implementation for User Story 1

- [x] T002 [P] [US1] Parameterize `publish()` in `src/publisher.py` — remove module-level `DOCS_DIR`, `DATA_DIR`, `WEEK_DIR` constants; change signature to `publish(articles: list, output_dir: str = "pages/traffic", site_url: str = None) -> str`; compute all path variables from `ROOT_DIR / output_dir` at call time; resolve `site_url` from parameter (when not None) or `SITE_URL` env var; all callers with no kwargs continue working unchanged

- [x] T003 [P] [US1] Migrate `.github/workflows/deploy-pages.yml` — change `directory: pages` to `directory: pages/traffic` and update the `paths` trigger from `pages/**` to `pages/traffic/**`; then create `.github/workflows/deploy-pages-ffxiv.yml` mirroring it with `name: Deploy Cloudflare Pages (FFXIV)`, `projectName: garyu-ffxiv-news`, `directory: pages/ffxiv`, and `paths` trigger `pages/ffxiv/**`

- [x] T004 [P] [US1] Add `FFXIV_SITE_URL: ${{ vars.FFXIV_SITE_URL }}` to the `env:` block of the `執行週報程式` step in `.github/workflows/weekly.yml`; default value `https://garyu-ffxiv-news.pages.dev` is used by `FFXIVCategory.site_url` when the variable is unset

- [x] T005 [US1] Update `main.py` — split the `analyzed` list into `traffic_analyzed` and `ffxiv_analyzed` by `content_type`; call `publish(traffic_analyzed, output_dir="pages/traffic")` for traffic; call `publish(ffxiv_analyzed, output_dir="pages/ffxiv", site_url=os.environ.get("FFXIV_SITE_URL"))` for FFXIV only when `ffxiv_analyzed` is non-empty; remove the single combined `publish(analyzed)` call; Supabase write remains centralized with all analyzed articles (depends on T002)

**Checkpoint**: `python main.py` produces both `pages/` (traffic only) and `pages-ffxiv/` (FFXIV only). Traffic pipeline output is byte-for-byte equivalent to pre-feature behavior. US1 independently deployable.

---

## Phase 3: User Story 2 — Content Module Architecture (Priority: P2)

**Goal**: Each content category is a self-contained module (`src/pipeline/traffic.py`, `src/pipeline/ffxiv.py`) implementing the `Category` protocol. `main.py` iterates a registered list — adding a new category requires one new file plus a one-line registration.

**Independent Test**: Create a stub module in `src/pipeline/stub.py` implementing `Category`; add it to `CATEGORIES` in `main.py`; run `python main.py`; confirm the stub runs without errors and existing traffic + FFXIV output is unchanged. Remove stub — confirm nothing breaks.

### Implementation for User Story 2

- [x] T006 [P] [US2] Add `collect_by_type(content_type: str) -> list` to `src/collector.py` — calls `collect_all()` internally and returns only articles where `article.get("content_type", "traffic") == content_type`; add immediately after `collect_all()`; existing callers of `collect_all()` are unchanged

- [x] T007 [P] [US2] Create `src/pipeline/base.py` — define `@runtime_checkable class Category(Protocol)` with class-level fields `name: str`, `content_type: str`, `max_articles: int`, `output_dir: str`, `site_url: str` and abstract methods `collect(self) -> list`, `filter(self, raw: list) -> list`, `analyze(self, articles: list) -> list`, `publish(self, articles: list) -> str`; export only `Category` from this module

- [x] T008 [US2] Create `src/pipeline/traffic.py` — implement `TrafficCategory` with: `name="traffic"`, `content_type="traffic"`, `max_articles=20`, `output_dir="pages/traffic"`, `site_url=os.environ.get("SITE_URL", "https://lukeking.github.io/traffic-issue-scraper")`; `collect()` calls `collect_by_type("traffic")`; `filter(raw)` calls `filter_and_deduplicate(raw)` then caps at `max_articles`; `analyze(articles)` calls `analyze_all(articles)`; `publish(articles)` calls `publish(articles, output_dir=self.output_dir, site_url=self.site_url)` (depends on T006, T007)

- [x] T009 [US2] Create `src/pipeline/ffxiv.py` — implement `FFXIVCategory` with: `name="ffxiv"`, `content_type="ffxiv"`, `max_articles=10`, `output_dir="pages/ffxiv"`, `site_url=os.environ.get("FFXIV_SITE_URL", "https://garyu-ffxiv-news.pages.dev")`; `collect()`, `filter()`, `analyze()`, `publish()` follow the same pattern as `TrafficCategory` (depends on T006, T007)

- [x] T010 [US2] Refactor `main.py` — import `TrafficCategory` and `FFXIVCategory`; define `CATEGORIES = [TrafficCategory(), FFXIVCategory()]`; replace per-category if/else logic with: `for cat in CATEGORIES: try: raw=cat.collect(); filtered=cat.filter(raw); analyzed=cat.analyze(filtered); cat.publish(analyzed); all_analyzed.extend(analyzed); except Exception as e: logger.error("[%s] category failed: %s", cat.name, e)`; move `_save_to_supabase(all_analyzed, week_id)` after the loop; KB MISS summary call unchanged (depends on T008, T009)

**Checkpoint**: `python main.py` produces identical output to US1 checkpoint. A stub `Category` can be registered and run without touching any other file.

---

## Phase 4: Polish & Cross-Cutting Concerns

**Purpose**: Ensure `pages-ffxiv/` is tracked in git (matching `pages/` treatment), update example config with `FFXIV_SITE_URL` reference, and validate end-to-end.

- [x] T011 [P] Move all existing files from `pages/` into `pages/traffic/` (preserving the `data/`, `week/`, `feed.xml` structure); create `pages/ffxiv/` with a minimal placeholder `index.html`; confirm neither subdirectory is in `.gitignore` (matching existing `pages/` tracking); add a comment to `config/sources_ffxiv.example.yml` noting the `FFXIV_SITE_URL` environment variable

- [ ] T012 End-to-end validation — trigger `Garyu News Scraper 週報` workflow manually (Actions → Run workflow); confirm: (a) workflow completes without errors, (b) `pages/traffic/` and `pages/ffxiv/` both contain current week's data, (c) Supabase has rows for both `content_type` values, (d) `deploy-pages-ffxiv.yml` workflow runs and produces a live FFXIV CF Pages URL, (e) no regression in traffic pipeline output

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — T001 is immediate
- **US1 (Phase 2)**: Depends on nothing beyond T001; T002/T003/T004 are parallel, T005 depends on T002
- **US2 (Phase 3)**: Can start after T002 (publisher parameterized for `output_dir`); T006/T007 parallel, T008/T009 parallel after T006+T007, T010 after T008+T009
- **Polish (Phase 4)**: Depends on US1 and US2 complete

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 1 — no dependencies on US2
- **US2 (P2)**: Starts after T002 (publisher parameterized) — thin wrappers call `publish(output_dir=...)` which must exist

### Within Each User Story

- US1: T002, T003, T004 parallel → T005 (depends on T002)
- US2: T006, T007 parallel → T008 and T009 parallel → T010

---

## Parallel Execution Examples

### User Story 1

```
# T002, T003, T004 together (different files, no conflicts):
Task: "Parameterize publish() in src/publisher.py"
Task: "Create .github/workflows/deploy-pages-ffxiv.yml"
Task: "Add FFXIV_SITE_URL to weekly.yml"

# Then T005 (depends on T002 being done):
Task: "Update main.py to call publish twice by content_type"
```

### User Story 2

```
# T006, T007 together:
Task: "Add collect_by_type() to src/collector.py"
Task: "Create src/pipeline/base.py with Category protocol"

# Then T008 and T009 together (different files):
Task: "Create src/pipeline/traffic.py — TrafficCategory"
Task: "Create src/pipeline/ffxiv.py — FFXIVCategory"

# Then T010:
Task: "Refactor main.py to use CATEGORIES list"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: User Story 1 (T002–T005)
3. **STOP and VALIDATE**: Both sites publish correctly; traffic output unchanged
4. Deploy FFXIV site via `deploy-pages-ffxiv.yml`

### Incremental Delivery

1. Setup → Phase 1 ready
2. US1 → Independent site per content type (MVP — user-visible value)
3. US2 → Modular architecture (enables new categories without code changes)
4. Polish → End-to-end validated in production

### Notes

- [P] tasks within the same phase operate on different files — safe to run in parallel
- T005 is the only task in US1 that touches `main.py`; T010 replaces it entirely in US2 — do NOT run T010 until T005 is validated
- US2 produces no behavioral change — output should be identical to US1 checkpoint before T010 is considered done
- A stub `Category` is the simplest independent test for US2 (see spec US2 Independent Test scenario)
