---
description: "Task list for Gemini-Powered Self-Evolving Knowledge Base"
---

# Tasks: Gemini-Powered Self-Evolving Knowledge Base

**Input**: Design documents from `specs/005-gemini-kb-auto-resolve/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

---

## Phase 1: Setup

**Purpose**: Commit the completed constitution amendment before any implementation deploys.

- [x] T001 Verify and commit `.specify/memory/constitution.md` amendment (v1.1.0 → v1.2.0) — removes `knowledge-base.md` restrictions, adds Supabase `knowledge_base` table rules

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Supabase table creation and data migration — MUST complete before any user story can be implemented or tested.

**⚠️ CRITICAL**: No user story work can be deployed to production until T004 is verified.

- [ ] T002 Create `knowledge_base` table in Supabase — run the SQL migration from `specs/005-gemini-kb-auto-resolve/data-model.md` (schema: `jp_term UNIQUE`, `tw_term`, `en_term`, `category`, `notes`, `auto_generated BOOLEAN`, `created_at`, `updated_at`)
- [x] T003 [P] Write `scripts/migrate_kb.py` — parse `knowledge-base.md` using 5-column pipe table logic, upsert all rows to `knowledge_base` with `auto_generated = false`, on_conflict `jp_term` (idempotent); see `contracts/pipeline-kb-migration.md` for full spec
- [ ] T004 Run `python scripts/migrate_kb.py` and verify: row count in Supabase `knowledge_base` table matches the number of term rows in `knowledge-base.md` (~60 rows); log shows expected count; no errors

**Checkpoint**: `knowledge_base` table populated — user story implementation can now begin.

---

## Phase 3: User Story 2 — Pipeline Reads KB from Supabase (P2) 🎯 Deploy first

**Goal**: Weekly pipeline reads KB from Supabase instead of `knowledge-base.md`; file retired.

**Why deploy before US1**: The pipeline must use Supabase KB before the auto-KB job writes new terms, otherwise newly auto-added terms won't appear in article analysis.

**Independent Test**: Remove `knowledge-base.md`, trigger pipeline via `workflow_dispatch`, verify `"知識庫載入完成：N 個術語"` in logs with N ≥ 60 and no `FileNotFoundError`.

### Implementation for User Story 2

- [x] T005 [P] [US2] Rewrite `load_knowledge_base()` in `src/analyzer.py` — replace file-read logic with Supabase SELECT (`jp_term, tw_term, en_term, category`); create Supabase client inline using `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`; preserve `_KB_CACHE` module-level dict and existing return format `{jp_term: {"tw", "en", "category"}}`; raise `RuntimeError` on empty result or connection failure (see `contracts/pipeline-kb-migration.md`)
- [ ] T006 Delete `knowledge-base.md` from repository root — only after T004 row count verified and T005 deployed; confirm pipeline run succeeds without the file
- [ ] T007 [P] Delete `config/knowledge-base-template.md` from repository
- [ ] T008 [P] Delete `scripts/resolve_kb_misses.py` from repository (superseded by auto-KB job inline re-resolution in US1)
- [ ] T009 [P] Delete `.github/workflows/resolve-kb-misses.yml` from repository (trigger path `knowledge-base.md` no longer exists)

**Checkpoint**: Pipeline runs cleanly from Supabase KB; all retired files removed.

---

## Phase 4: User Story 1 — Automated KB Expansion via Gemini (P1)

**Goal**: Weekly auto-KB job collects `[[term]]` misses, resolves via Gemini, writes to Supabase KB, patches articles inline.

**Independent Test**: Insert a synthetic `[[テスト用語]]` placeholder into a Supabase FFXIV article, run `python scripts/auto_kb.py`, verify new KB row with `auto_generated = true` and article placeholder replaced.

### Implementation for User Story 1

- [x] T010 [P] [US1] Write `scripts/auto_kb.py` — complete implementation per `contracts/auto-kb-job.md`:
  - Step 1: load existing `jp_term` set from Supabase `knowledge_base`
  - Step 2: query FFXIV articles with `analysis::text LIKE '%[[%'`, extract unique unknown terms (not in existing set)
  - Step 3: if no unknown terms, log and exit 0
  - Step 4: single Gemini batch call with system prompt ("FFXIV TW 術語翻譯專家") and user prompt (newline-separated term list, JSON array response, temperature 0.1); parse response; validate `jp_term` and `tw_term` non-empty
  - Step 5: INSERT each valid entry to `knowledge_base` with `auto_generated = true`; skip duplicates; log `[KB AUTO-MISS]` for omitted terms
  - Step 6: inline re-resolution — for each article from Step 2, replace `[[term]]` with newly-added `tw_term`, UPDATE Supabase if any replacements made
  - Always exit 0; all failures are logged and non-blocking
- [x] T011 [US1] Write `.github/workflows/auto-kb.yml` — trigger: `workflow_run` on `Garyu News Scraper 週報` with `types: [completed]`; job guard: `if: github.event.workflow_run.conclusion == 'success'`; steps: checkout, Python 3.11 setup, pip install, `python scripts/auto_kb.py`; env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL_NAME` (all from existing secrets/vars)

**Checkpoint**: Auto-KB job collects misses, calls Gemini, writes KB rows, patches articles — end-to-end without human intervention.

---

## Phase 5: User Story 3 — Frontend Tag Cloud (P3)

**Goal**: Scattered word cloud of unresolved `[[term]]` terms displayed at top of FFXIV news page.

**Independent Test**: Ensure at least one FFXIV article in Supabase has a `[[term]]` placeholder; open FFXIV page; verify `#unknown-term-pool` section appears above the tag bar with the term as a floating tag.

### Implementation for User Story 3

- [x] T012 [P] [US3] Add `#unknown-term-pool` HTML and CSS to `pages/ffxiv/index.html` — insert `<div id="unknown-term-pool" class="term-pool" style="display:none">` with `<div class="term-pool-header">` and `<div class="term-pool-tags" id="term-pool-tags">` between `<div class="week-nav" id="week-nav">` and `<div class="tag-bar" id="tag-bar">`; add `.term-pool`, `.term-pool-header`, `.term-pool-sub`, `.term-pool-tags`, `.term-tag` CSS using `var(--accent)`, `var(--tag-bg)`, `var(--card-bg)` variables in the `<style>` block (see `contracts/frontend-tag-cloud.md` for exact HTML/CSS)
- [x] T013 [P] [US3] Add `renderTermPool(articles)` to `pages/shared/app.js` and call from `renderAll()` — function: guard on `C.contentType !== 'ffxiv'`; extract `[[term]]` matches from `JSON.stringify(a.analysis || {})` for all articles; deduplicate via `Set`; if empty set `pool.style.display = 'none'`; else render tags as `position:absolute` spans with random `font-size` (0.85–1.55rem), `left` (2–90%), `top` (5–80%) per tag (see `contracts/frontend-tag-cloud.md` for exact JS)

**Checkpoint**: Tag cloud appears with scattered tags when unresolved terms exist; hides when none exist; traffic page unaffected.

---

## Phase 6: User Story 4 — Scheduling Verification (P4)

**Goal**: Confirm `auto-kb.yml` fires automatically after the weekly pipeline, not before.

**Independent Test**: Trigger `Garyu News Scraper 週報` via `workflow_dispatch`; verify `Auto KB Expansion` job appears in GitHub Actions within ~60 seconds of pipeline completion.

### Implementation for User Story 4

- [ ] T014 [US4] Trigger `Garyu News Scraper 週報` via GitHub Actions `workflow_dispatch`; confirm `auto-kb.yml` run appears automatically after pipeline completes successfully (quickstart Scenario 7); confirm no run appears after a failed pipeline

**Checkpoint**: `workflow_run` trigger confirmed working end-to-end.

---

## Phase 7: Polish & Validation

**Purpose**: End-to-end integration validation across all user stories.

- [ ] T015 [P] Run quickstart Scenario 1: pipeline reads Supabase KB with no `knowledge-base.md` present; verify log `"知識庫載入完成：N 個術語"`
- [ ] T016 [P] Run quickstart Scenario 3: insert synthetic `[[term]]` into Supabase article, run `python scripts/auto_kb.py`, verify KB row written with `auto_generated = true` and article patched
- [ ] T017 [P] Run quickstart Scenario 6: verify FFXIV page tag cloud shows/hides based on `[[term]]` presence in displayed articles
- [ ] T018 Run quickstart Scenario 8: run `python scripts/migrate_kb.py` twice, verify Supabase row count identical both runs (idempotency)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US2 (Phase 3)**: Depends on T002 (table) + T004 (migration verified) — deploy before US1
- **US1 (Phase 4)**: Depends on T002 (table) — can develop in parallel with US2
- **US3 (Phase 5)**: No dependencies — can start any time after Phase 1
- **US4 (Phase 6)**: Depends on T011 (auto-kb.yml deployed)
- **Polish (Phase 7)**: Depends on all user story phases complete

### Critical Deployment Order

```
T002 (table) → T004 (migration) → T005+T006 (analyzer + delete .md) deployed first
                                 → T010+T011 (auto_kb.py + workflow) deployed second
T012+T013 (frontend) can deploy independently at any point
```

### Within US2

- T005 (analyzer rewrite) before T006 (delete .md) — cannot delete the file until the new code is verified working

### Within US1

- T010 (script) before T011 (workflow) — workflow references the script

### Parallel Opportunities

```bash
# Phase 2 — T003 and T005/T010 can all be written in parallel (different files):
Write: scripts/migrate_kb.py
Write: src/analyzer.py (load_knowledge_base rewrite)
Write: scripts/auto_kb.py
Add:   pages/ffxiv/index.html (term pool div)
Add:   pages/shared/app.js (renderTermPool)
```

---

## Implementation Strategy

### MVP First (US2 — Pipeline Migration)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (table + migration)
3. Complete Phase 3: US2 (analyzer + file deletions)
4. **STOP and VALIDATE**: Trigger pipeline, confirm it reads from Supabase with no `.md` file
5. Deploy — pipeline now uses self-evolving KB storage

### Incremental Delivery

1. Setup + Foundational → KB in Supabase, pipeline working
2. US2 → `knowledge-base.md` fully retired ✓
3. US1 → Auto-KB job closes the miss-resolution loop ✓
4. US3 → Users see unresolved terms in the tag cloud ✓
5. US4 → Scheduling verified, fully automated weekly cycle ✓

---

## Notes

- `[P]` = different files, no incomplete task dependencies — safe to run in parallel
- `[US#]` maps to user stories in `specs/005-gemini-kb-auto-resolve/spec.md`
- T006 (delete `knowledge-base.md`) is a one-way door — ensure T004 and T005 are verified before executing
- All script failures must exit 0 — never let auto-KB job crash the weekly pipeline
- Constitution amendment (T001) was completed during `/speckit-constitution` — verify committed
