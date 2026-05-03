# Implementation Plan: Extend to Garyu News Scraper (FFXIV Integration)

**Branch**: `epic/extend-to-garyu-news-scraper` | **Date**: 2026-05-03 | **Spec**: `specs/001-extend-to-garyu-news-scraper/spec.md`
**Input**: Feature specification from `specs/001-extend-to-garyu-news-scraper/spec.md`

## Summary

Extend the existing traffic-news pipeline to collect, filter, analyze, and store FFXIV 8.0
game information alongside traffic news. Three new FFXIV source types are supported:
`rss` (Reddit r/ffxiv), `html_patch` (Lodestone JP), and `html_forum` (Square Enix JP
Forum — thread titles + links only; full body requires OAuth). A knowledge base
(`knowledge-base.md`) gates FFXIV AI analysis to prevent invented term translations. Both
content types share the Supabase `articles` table via a new `content_type` column. The
existing traffic pipeline is preserved unchanged.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: feedparser, requests, beautifulsoup4 + lxml, PyYAML,
  python-dotenv, supabase-py (Gemini accessed via direct REST requests — no SDK)
**Storage**: Supabase PostgreSQL — existing `articles` table + `content_type` column
  via `db/supabase_migrations/002_add_content_type.sql`
**Testing**: None (project has no test suite; verification via GitHub Actions run)
**Target Platform**: GitHub Actions ubuntu-latest; local dev on Windows
**Project Type**: Scheduled data pipeline / automation
**Performance Goals**: Full dual-content pipeline completes within 15 minutes on GitHub
  Actions; FFXIV articles capped at 30/run (shared Gemini RPD budget with traffic)
**Constraints**: Free tier — Gemini (10 RPM, 20 RPD), GitHub Actions (2,000 min/month),
  Supabase (500MB), Cloudflare (free Workers/Pages); backward compat with traffic-only mode
**Scale/Scope**: ~30 traffic + ~30 FFXIV articles/run; weekly cadence; single developer

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Requirement | Status |
|-----------|-------------|--------|
| I. Pipeline Integrity | FFXIV content flows through the same Collect→Filter→Analyze→Store→Notify stage contract; content-type dispatch is internal to each stage | ✅ |
| II. Config over Code | `sources_ffxiv.yml` stored as `SOURCES_FFXIV_YML` GitHub Env Var; never committed | ✅ |
| III. Idempotency | `filter.py` dedup applies to FFXIV via same MD5 hash; `storage.py` upserts by stable `link` key; `content_type` defaults preserve existing rows | ✅ |
| IV. Free Tier | Reddit RSS (no auth); Lodestone HTML (public); JP Forum listing (public); combined article cap maintained | ✅ |
| V. Single Responsibility | New collection logic in `collector.py`; FFXIV analysis dispatch in `analyzer.py`; no cross-module leakage; sub-module promotion deferred per constitution | ✅ |
| VI. Knowledge Base Integrity | `knowledge-base.md` loaded and validated before FFXIV analysis; missing KB raises `RuntimeError`; unknown terms logged as `[KB MISS]`, not invented | ✅ |

**Post-design re-check**: JP Forum source collects titles-only due to OAuth requirement for
full content — this is consistent with Principle IV (free tier, no credentials required)
and Principle II (no new secrets needed). No violations introduced.

**GATE: PASSED — no violations.**

## Project Structure

### Documentation (this feature)

```
specs/001-extend-to-garyu-news-scraper/
├── plan.md          # This file
├── spec.md          # Feature specification
├── research.md      # Phase 0 findings
├── data-model.md    # Phase 1 entity and schema definitions
├── quickstart.md    # Phase 1 dev + ops runbook
├── contracts/
│   ├── sources-schema.md   # Config entry schema for all source types
│   └── article-schema.md   # Pipeline article dict contract
└── tasks.md         # Phase 2 output (/speckit-tasks — not yet generated)
```

### Source Code (repository root)

```
src/
├── collector.py     # + load_ffxiv_sources(), _fetch_html_patch(), _fetch_html_forum()
│                    #   dispatch FFXIV sources; tag articles with content_type
├── filter.py        # + FFXIV_MUST_INCLUDE list; dispatch filter by content_type
├── analyzer.py      # + load_knowledge_base(), FFXIV_SYSTEM_PROMPT,
│                    #   FFXIV_ANALYSIS_TEMPLATE; dispatch by content_type
├── storage.py       # + content_type field in upsert row dict
├── publisher.py     # + dual content-type sections in output
├── mailer.py        # Unchanged for v1
└── main.py          # + FFXIV source loading; pass content_type through pipeline

config/
├── sources.yml              # Traffic (from SOURCES_YML env var; not committed)
├── sources.example.yml      # Traffic example (committed)
├── sources_ffxiv.yml        # FFXIV (from SOURCES_FFXIV_YML env var; not committed)
└── sources_ffxiv.example.yml  # FFXIV example with all 3 source types (committed)

knowledge-base.md            # FFXIV term mappings; ≥20 entries before v1 production run
knowledge-base-template.md   # Existing template (unchanged)

db/
└── supabase_migrations/
    └── 002_add_content_type.sql

workers/api/
└── index.js         # + ?content_type= query param filter

.github/workflows/
├── weekly.yml       # + SOURCES_FFXIV_YML injection step
├── deploy-pages.yml # Review + fix if broken
└── deploy-worker.yml # Review + fix if broken
```

**Structure Decision**: Single-project flat `src/` layout (Option 1). No sub-module
promotion (`src/scrapers/`) in this iteration — FFXIV logic stays co-located with
traffic logic per constitution Principle V until volume justifies reorganization.

## Complexity Tracking

> No constitution violations requiring justification.
