# Tasks: Site UX Polish

**Input**: Design documents from `specs/003-ux-polish/`
**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Data model**: [data-model.md](./data-model.md)
**Contracts**: [freshness-filter.md](./contracts/freshness-filter.md) | [frontend-features.md](./contracts/frontend-features.md) | [kb-re-resolution.md](./contracts/kb-re-resolution.md)
**Tests**: Not requested — no test tasks generated.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Create the one new directory required by the plan.

- [ ] T001 Create `scripts/` directory at repository root (needed by US6)

---

## Phase 2: Foundational (Blocking Prerequisite for US1)

**Purpose**: Extend `src/storage.py` with the fingerprint data-access functions that both pipeline categories (traffic + FFXIV) will call. Must complete before Phase 3.

**⚠️ CRITICAL**: Phase 3 (US1) cannot begin until T002 is complete.

- [ ] T002 Extend `src/storage.py`: add `get_existing_title_fingerprints() -> set[str]` (SELECT non-null `content_fingerprint` from `articles`; returns empty set on failure with WARNING log); expand `upsert_articles()` to compute and write `sha256(re.sub(r'[^\w一-鿿぀-ヿ]', '', title.lower().strip()).encode()).hexdigest()` as `content_fingerprint` for every article regardless of whether it has a URL

**Checkpoint**: `get_existing_title_fingerprints()` and expanded `upsert_articles()` are in place. Phase 3 can now begin.

---

## Phase 3: User Story 1 — Pipeline Freshness Filter (Priority: P1) 🎯 MVP

**Goal**: Two-layer stale-article gate in `src/filter.py` eliminates cross-week duplicates and articles older than 30 days before the analysis stage.

**Independent Test**: Scenarios 1–3 in `specs/003-ux-polish/quickstart.md`.

- [ ] T003 [US1] Add `FRESHNESS_THRESHOLD_DAYS = 30`, `_normalize_title_for_fingerprint(title)`, `title_fingerprint(article) -> str`, `_extract_url_date(url) -> date | None`, and `_is_too_old_by_age(article, threshold_days) -> bool` to `src/filter.py` per the algorithm in `contracts/freshness-filter.md`
- [ ] T004 [US1] Add `freshness_filter(articles, existing_fingerprints, threshold_days=30) -> list[dict]` to `src/filter.py` implementing the per-article decision tree in `contracts/freshness-filter.md`: fingerprint match → exclude with INFO log; Google News URL-date → exclude if old; direct RSS pubDate → exclude if old; unparseable → include (depends on T003)
- [ ] T005 [P] [US1] Update `filter()` in `src/pipeline/traffic.py`: call `get_existing_title_fingerprints()` then `freshness_filter(raw, fingerprints)` before the existing `filter_and_deduplicate()` call, per the four-step contract in `contracts/freshness-filter.md` (depends on T004)
- [ ] T006 [P] [US1] Update `filter()` in `src/pipeline/ffxiv.py`: same four-step sequence as T005 (depends on T004)

**Checkpoint**: Run pipeline locally with a known stale article — it must be excluded and logged. US1 independently verifiable.

---

## Phase 4: User Story 2 — Mark News as Outdated (Priority: P2)

**Goal**: Each article card on both sites has a "標記過時" dismiss button; dismissed URLs persist in localStorage and are hidden on all subsequent renders.

**Independent Test**: Scenarios 4–5 in `specs/003-ux-polish/quickstart.md`.

- [ ] T007 [P] [US2] Add dismiss button `<button class="dismiss-btn" data-url="{article.link}">標記過時</button>` to each article card in `pages/traffic/index.html`; add click handler (localStorage key `dismissed-traffic`, JSON array); add on-load/week-switch filter to hide dismissed cards; add empty-state with "清除過時標記" button; add localStorage fallback (session-only hide on quota error) — per `contracts/frontend-features.md` P2 section
- [ ] T008 [P] [US2] Same as T007 for `pages/ffxiv/index.html` using localStorage key `dismissed-ffxiv`

**Checkpoint**: Dismiss a card, reload — card absent. Click "清除過時標記" — card returns. US2 independently verifiable.

---

## Phase 5: User Story 3 — Dark / Light Theme Toggle (Priority: P3)

**Goal**: Light/dark theme toggle in both site headers; preference persisted in localStorage; OS `prefers-color-scheme` applied on first visit.

**Independent Test**: Scenarios 6–7 in `specs/003-ux-polish/quickstart.md`.

- [ ] T009 [P] [US3] In `pages/traffic/index.html`: add CSS custom properties under `:root` (light defaults) and `[data-theme="dark"]` overrides per `contracts/frontend-features.md` P3; replace all hardcoded colour values with `var(--token)` references; add `<button id="theme-toggle">` to header; add theme-init script in `<head>` (read localStorage `theme`, fall back to OS `prefers-color-scheme`, set `data-theme` on `<html>` before paint); add toggle click handler (flip theme, write to localStorage `theme`, update icon 🌙/☀️)
- [ ] T010 [P] [US3] Same as T009 for `pages/ffxiv/index.html`

**Checkpoint**: Toggle dark → close tab → reopen → dark mode active with no flash. US3 independently verifiable.

---

## Phase 6: User Story 4 — Collected-Time Date Label (Priority: P4)

**Goal**: All article date displays on both sites prefixed "收錄時間"; no element rendered when date absent.

**Independent Test**: Scenario 8 in `specs/003-ux-polish/quickstart.md`.

- [ ] T011 [P] [US4] Update all article date rendering in `pages/traffic/index.html` so every date is `<span class="date-label">收錄時間 {date}</span>`; suppress element entirely when date is empty/null per `contracts/frontend-features.md` P4
- [ ] T012 [P] [US4] Same as T011 for `pages/ffxiv/index.html`

**Checkpoint**: Inspect both sites — zero dates without "收錄時間" prefix. US4 independently verifiable.

---

## Phase 7: User Story 5 — FFXIV Site RSS Feed (Priority: P5)

**Goal**: `pages/ffxiv/feed.xml` generated with FFXIV-specific title/description; FFXIV site header exposes an RSS link.

**Independent Test**: Scenario 9 in `specs/003-ux-polish/quickstart.md`.

- [ ] T013 [US5] Add `feed_title: str` and `feed_description: str` parameters (with existing traffic values as defaults) to `build_feed()` and `publish()` in `src/publisher.py` per `contracts/frontend-features.md` P5 pipeline contract; traffic pipeline is unaffected (no call-site changes needed due to defaults)
- [ ] T014 [US5] Update `FFXIVCategory.publish()` in `src/pipeline/ffxiv.py` to pass `feed_title="最終幻想XIV 週報"` and `feed_description="每週自動彙整 FFXIV 遊戲相關資訊，含 AI 摘要與重點分析"` to `publish()` (depends on T013)
- [ ] T015 [P] [US5] Add `<a href="./feed.xml" class="rss-link" rel="alternate" type="application/rss+xml" title="RSS 訂閱">📡 RSS 訂閱</a>` to FFXIV site header in `pages/ffxiv/index.html` per `contracts/frontend-features.md` P5 DOM contract (independent of T013/T014)

**Checkpoint**: Run FFXIV pipeline locally → inspect `pages/ffxiv/feed.xml` for `<title>最終幻想XIV 週報</title>` and valid RSS 2.0. US5 independently verifiable.

---

## Phase 8: User Story 6 — KB Miss Re-Resolution Job (Priority: P6)

**Goal**: GitHub Actions workflow triggers on `knowledge-base.md` push to `main`; resolves `[[term]]` markers in Supabase FFXIV articles via KB string lookup; no AI calls, no scraping, no CF Pages redeploy.

**Independent Test**: Push a KB update to `main` → GH Actions run completes → Supabase articles with `[[that-term]]` have it replaced with the correct TW term.

- [x] T016 [P] [US6] Create `scripts/resolve_kb_misses.py` per `contracts/kb-re-resolution.md`: implement `load_kb(kb_path)` (parse KB markdown tables into JP→TW dict); query Supabase for FFXIV articles with `analysis::text LIKE '%[[%'`; per-article loop using `re.findall/sub` on `json.dumps(analysis)` to detect and replace `\[\[([^\]]+)\]\]` markers; UPDATE Supabase rows that had resolvable replacements; emit one aggregated KB MISS WARNING block for all unresolvable terms; exit 0 always
- [x] T017 [P] [US6] Create `.github/workflows/resolve-kb-misses.yml`: trigger `on: push: branches: [main]: paths: ['knowledge-base.md']`; single job: `actions/checkout@v4` → `pip install supabase` → `python scripts/resolve_kb_misses.py`; inject `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` from existing GitHub Secrets

**Checkpoint**: Merge a test KB change to `main` → Actions tab shows workflow triggered → completes green. US6 independently verifiable.

---

## Final Phase: Polish & Validation

**Purpose**: End-to-end validation against all quickstart scenarios and smoke-test the GH Actions workflow.

- [ ] T018 [P] Validate Scenarios 1–3 (freshness filter: fingerprint dedup, RSS age gate, URL-date extraction) from `specs/003-ux-polish/quickstart.md`
- [ ] T019 [P] Validate Scenarios 4–5 (dismiss button: hide + persist, empty state + clear) from `specs/003-ux-polish/quickstart.md`
- [ ] T020 [P] Validate Scenarios 6–7 (theme toggle: persistence across reload, OS preference) from `specs/003-ux-polish/quickstart.md`
- [ ] T021 [P] Validate Scenarios 8–9 (date label on both sites, FFXIV RSS feed structure and link) from `specs/003-ux-polish/quickstart.md`
- [ ] T022 Smoke-test KB re-resolution job: confirm GH Actions workflow YAML is valid and triggers correctly on a `knowledge-base.md` push to `main`

---

## Dependencies & Execution Order

### Phase Dependencies

```
T001 (Setup)
  ├─→ T002 (Foundational) → T003 → T004 → T005 [P]
  │                                         T006 [P]
  ├─→ T007 [P]  (US2 — traffic HTML)
  ├─→ T008 [P]  (US2 — ffxiv HTML)
  ├─→ T009 [P]  (US3 — traffic HTML)   ← same file as T007, sequence within file
  ├─→ T010 [P]  (US3 — ffxiv HTML)    ← same file as T008, sequence within file
  ├─→ T011 [P]  (US4 — traffic HTML)   ← same file as T007/T009, sequence within file
  ├─→ T012 [P]  (US4 — ffxiv HTML)    ← same file as T008/T010/T015, sequence within file
  ├─→ T013 → T014  (US5 — pipeline, sequential)
  ├─→ T015 [P]     (US5 — ffxiv HTML, independent of T013/T014)
  ├─→ T016 [P]  (US6 — script)
  └─→ T017 [P]  (US6 — workflow)
```

### Intra-file Sequencing (avoid edit conflicts)

| File | Tasks (sequence in this order) |
|------|-------------------------------|
| `pages/traffic/index.html` | T007 → T009 → T011 |
| `pages/ffxiv/index.html` | T008 → T010 → T012 → T015 |
| `src/filter.py` | T003 → T004 |
| `src/pipeline/ffxiv.py` | T006 then T014 |

---

## Implementation Strategy

### MVP (Pipeline Filter Only)

1. T001 → T002 → T003 → T004 → T005 + T006
2. **Validate** Scenarios 1–3 → deploy pipeline change

### Incremental Delivery

```
MVP:  T001→T002→T003→T004→T005+T006  (backend — stale-article filter live)
+US2: T007+T008                        (dismiss button on both sites)
+US3: T009+T010                        (theme toggle on both sites)
+US4: T011+T012                        (date label — one-liner per site)
+US5: T013→T014, T015                  (FFXIV RSS feed)
+US6: T016+T017                        (KB re-resolution automation)
```

---

## Summary

| Phase | Story | Tasks | Parallelizable |
|-------|-------|-------|----------------|
| Setup | — | T001 | — |
| Foundational | — | T002 | — |
| Phase 3 | US1 P1 🎯 | T003–T006 | T005+T006 |
| Phase 4 | US2 P2 | T007–T008 | T007+T008 |
| Phase 5 | US3 P3 | T009–T010 | T009+T010 |
| Phase 6 | US4 P4 | T011–T012 | T011+T012 |
| Phase 7 | US5 P5 | T013–T015 | T015 with T013 |
| Phase 8 | US6 P6 | T016–T017 | T016+T017 |
| Polish | — | T018–T022 | T018–T021 |
| **Total** | **6 stories** | **22 tasks** | **13 parallelizable** |
