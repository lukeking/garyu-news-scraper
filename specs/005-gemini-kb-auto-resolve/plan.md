# Implementation Plan: Gemini-Powered Self-Evolving Knowledge Base

**Branch**: `005-gemini-kb-auto-resolve` | **Date**: 2026-05-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/005-gemini-kb-auto-resolve/spec.md`

## Summary

Five coordinated changes that replace the static `knowledge-base.md` file with a live Supabase `knowledge_base` table, automate weekly KB expansion via Gemini, and surface still-unresolvable terms as a scattered tag cloud on the FFXIV news page:

1. **Constitution Amendment** — Principle VI + Technology Constraints amended (MINOR 1.1.0 → 1.2.0) to reflect Supabase SSoT and auto-write model.
2. **KB Migration** — One-time script migrates existing `knowledge-base.md` content to Supabase `knowledge_base` table; file and template retired.
3. **Pipeline Migration** — `src/analyzer.py`'s `load_knowledge_base()` rewritten to query Supabase at startup instead of reading the file; same in-memory cache pattern preserved.
4. **Auto-KB Job** — New `scripts/auto_kb.py` + `.github/workflows/auto-kb.yml`. Triggered on successful `Garyu News Scraper 週報` completion via `workflow_run`. Collects `[[term]]` misses, calls Gemini for confident TW resolutions, writes directly to Supabase, then inline-re-resolves all matched article placeholders. Retires `scripts/resolve_kb_misses.py` and `.github/workflows/resolve-kb-misses.yml`.
5. **Frontend Tag Cloud** — Scattered word cloud section added between `#week-nav` and `.tag-bar` in `pages/ffxiv/index.html`; `pages/shared/app.js` extended with FFXIV-gated `renderTermPool()` that extracts `[[term]]` patterns from displayed article analysis data.

## Technical Context

**Language/Version**: Python 3.11 (pipeline + scripts) / Vanilla JS (frontend) / GitHub Actions YAML  
**Primary Dependencies**: supabase-py (existing), requests (existing for Gemini calls) — no new packages  
**Storage**: Supabase PostgreSQL — new `knowledge_base` table alongside existing `articles` table  
**Testing**: pytest (existing unit tests); manual trigger via `workflow_dispatch` for GH Actions jobs  
**Target Platform**: GitHub Actions (auto-KB job, migration script); Cloudflare Pages (frontend); Python 3.11 runtime  
**Project Type**: Data pipeline (Python) + Static frontend (Vanilla JS) + GitHub Actions automation  
**Performance Goals**: Auto-KB job completes in < 10 min; Gemini batch call processes ≤ 30 unknown terms per run  
**Constraints**: No new paid services; no new GitHub Secrets needed; free-tier Supabase read/write limits respected; `workflow_run` trigger only fires on weekly pipeline success  
**Scale/Scope**: KB expected to grow from ~60 current terms to a few hundred over 12 months; Supabase query returns all rows (no pagination needed at this scale)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked post-design below.*

### Principle I — Pipeline Integrity ✓
- Auto-KB job is a standalone GitHub Actions workflow — it never touches the weekly pipeline's execution path.
- `load_knowledge_base()` halts the pipeline on Supabase query failure (FR-010) rather than continuing with an empty KB; no silent failure.
- Re-resolution step in `auto_kb.py` is an independent write to `articles.analysis`; isolated from the collect→filter→analyze→store pipeline.

### Principle II — Configuration over Code ✓
- No new config files. `GEMINI_MODEL_NAME` and `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` are reused.
- `knowledge_base` table name is a constant, not hardcoded in multiple places.

### Principle III — Idempotency & Deduplication ✓
- KB upsert uses `jp_term` as unique key (UNIQUE constraint); running migration twice does not duplicate rows.
- `auto_kb.py` deduplicates against existing `knowledge_base` rows before querying Gemini; re-resolution is idempotent (no `[[` remains after a resolved term is written).

### Principle IV — Free Tier Discipline ✓
- One Supabase SELECT per pipeline startup for full KB fetch — well within free-tier read limits.
- Auto-KB job makes one Gemini batch call per weekly run, covering ≤ 30 unique unknown terms — well within free-tier rate limits.
- Auto-KB job runs at most once per week (triggered by weekly pipeline).

### Principle V — Single Responsibility ✓
- `src/analyzer.py`: KB fetch logic stays in `load_knowledge_base()` within the same module; no new cross-module dependency introduced. Supabase client created inline (same pattern as `scripts/resolve_kb_misses.py`'s `_get_client()`).
- `scripts/auto_kb.py`: operational script (same pattern as `scripts/resolve_kb_misses.py`) — not a `src/` stage module.
- Frontend: `renderTermPool()` added to `app.js`, FFXIV-gated via `C.contentType === 'ffxiv'` check.

### Principle VI — Knowledge Base Integrity ⚠ AMENDMENT REQUIRED
**Violation**: Principle VI names `knowledge-base.md` as the authoritative source and requires PR review for all KB updates. This feature retires the file and allows Gemini to write new entries directly to Supabase without a PR.

**Justification**: The KB automation is the explicit purpose of this feature. The confidence gate (Gemini instructed to omit uncertain terms) replaces the PR review mechanism. The `auto_generated` flag in the Supabase table preserves auditability. The Operations & Deployment section can be updated to note that manual review of auto-generated entries is performed via the Supabase dashboard, not via PRs.

**Resolution**: Amendment to Principle VI and Technology Constraints required as the first task of this implementation. MINOR version bump 1.1.0 → 1.2.0.

**Post-design re-check**: All design decisions in research.md, data-model.md, and contracts/ are consistent with the amended constitution. No new violations introduced.

**Gate result**: CONDITIONAL PASS — implementation MAY proceed in parallel with the constitution amendment, but the amendment MUST be merged before the auto-KB job is deployed to production.

## Project Structure

### Documentation (this feature)

```text
specs/005-gemini-kb-auto-resolve/
├── plan.md                          # This file
├── research.md                      # Phase 0: key decisions
├── data-model.md                    # Phase 1: Supabase schema
├── quickstart.md                    # Phase 1: integration test scenarios
├── contracts/
│   ├── kb-schema.md                 # knowledge_base table contract
│   ├── auto-kb-job.md               # auto_kb.py + workflow contract
│   ├── pipeline-kb-migration.md     # analyzer.py migration contract
│   └── frontend-tag-cloud.md        # term pool UI contract
└── tasks.md                         # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

```text
# New files
scripts/auto_kb.py                    # Gemini auto-KB expansion + inline re-resolution
scripts/migrate_kb.py                 # One-time migration: knowledge-base.md → Supabase
.github/workflows/auto-kb.yml        # workflow_run trigger on weekly pipeline success

# Modified files
src/analyzer.py                       # load_knowledge_base() → Supabase query
pages/ffxiv/index.html                # Add #unknown-term-pool div + CSS
pages/shared/app.js                   # Add renderTermPool() (FFXIV-gated)
.specify/memory/constitution.md       # Amendment: Principle VI + Technology Constraints

# Deleted files
knowledge-base.md                     # Retired; content migrated to Supabase
config/knowledge-base-template.md     # Retired; Supabase schema documented in data-model.md
scripts/resolve_kb_misses.py          # Retired; logic merged into auto_kb.py
.github/workflows/resolve-kb-misses.yml  # Retired; superseded by auto-kb.yml
```

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Principle VI: auto-write to KB without PR | Self-evolving KB is the stated feature goal; PR gate defeats full automation | Requiring a PR for every Gemini suggestion reintroduces the manual bottleneck the feature is designed to eliminate; confidence gate + `auto_generated` flag provides equivalent quality control |
| Principle VI: `knowledge-base.md` retired | Supabase SSoT eliminates context-window scalability concern and enables direct write | Keeping the file as a generated snapshot (Option C original) was rejected by user as "meaningless" — it creates a stale artifact with no consumers |
