# Implementation Plan: Site UX Polish

**Branch**: `epic/extend-to-garyu-news-scraper` | **Date**: 2026-05-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/003-ux-polish/spec.md`

## Summary

Five incremental improvements to the garyu news scraper system:

1. **P1 — Pipeline Freshness Filter**: A two-layer stale-article gate added before the existing `filter_and_deduplicate()` call. Layer 1 checks each article's title fingerprint against all Supabase history (cross-week dedup). Layer 2 applies a 30-day age threshold via RSS `<pubDate>` for direct feeds and regex URL-date extraction for Google News (no HTTP requests).
2. **P2 — Mark as Outdated**: A client-side "標記過時" dismiss button on each article card; dismissed article URLs are stored in browser localStorage and hidden on subsequent page loads and filter changes.
3. **P3 — Theme Toggle**: Light/dark theme toggle in the site header; preference stored in localStorage; OS `prefers-color-scheme` applied on first visit.
4. **P4 — Collected-Time Label**: All article date displays prefixed with "收錄時間" on both sites.
5. **P5 — FFXIV RSS Feed**: Parameterize `publisher.py`'s `build_feed()` with feed title and description; `FFXIVCategory.publish()` passes FFXIV-specific values so `pages/ffxiv/feed.xml` is correctly titled; `pages/ffxiv/index.html` header exposes the RSS link.

## Technical Context

**Language/Version**: Python 3.11 (pipeline) / Vanilla HTML + CSS + JS (frontend) / Cloudflare Worker JS (API — read-only for this feature)
**Primary Dependencies**: supabase-py, hashlib (stdlib), re (stdlib), datetime (stdlib) — no new packages required
**Storage**: Supabase PostgreSQL `articles` table; `content_fingerprint` column expanded to cover all articles (not just URL-less ones); browser localStorage for client-side state
**Testing**: pytest (existing unit tests); manual browser verification for all frontend stories
**Target Platform**: GitHub Actions weekly workflow (pipeline); Cloudflare Pages (static frontend)
**Project Type**: Data pipeline + Single Page Application
**Performance Goals**: Single batch Supabase SELECT per pipeline run for fingerprint lookup; age filter uses only stdlib datetime + regex (zero additional HTTP calls)
**Constraints**: No new paid services; no user authentication; no HTTP requests inside the freshness filter; full pipeline must complete within 10 min (GitHub Actions free tier)
**Scale/Scope**: ~30–50 articles per run; fingerprint set ≈ weeks × articles/week (~500–1000 rows total in Supabase)

## Constitution Check

*GATE: Must pass before implementation. Re-checked post-design below.*

### Principle I — Pipeline Integrity ✓
- `freshness_filter()` is a new sub-step within the existing Filter stage; it runs after collect and before `filter_and_deduplicate()`.
- Supabase query failure is handled gracefully: pipeline continues with age-only filter, warning logged (FR-004). No silent failure.

### Principle II — Configuration over Code ✓
- The 30-day threshold is a named constant `FRESHNESS_THRESHOLD_DAYS = 30` in `filter.py`.
- No config file or environment variable needed for this value; it is stable by spec definition.

### Principle III — Idempotency & Deduplication ✓
- Cross-week dedup lives in `filter.py` (`freshness_filter()`), satisfying the "deduplication MUST occur in `src/filter.py`" rule.
- `content_fingerprint` will be written for ALL articles in `upsert_articles()` (title-only sha256); re-running the pipeline overwrites rows idempotently (upsert key remains `link`).

### Principle IV — Free Tier Discipline ✓
- One Supabase SELECT per pipeline run for the fingerprint set — well within free tier read limits.
- URL-date regex extraction makes no HTTP calls.

### Principle V — Single Responsibility ✓
- `filter.py`: all freshness filter logic (title fingerprint computation, age checks, URL-date extraction).
- `storage.py`: Supabase fingerprint query + expanded `content_fingerprint` population.
- `pipeline/traffic.py` + `pipeline/ffxiv.py`: orchestrate the fetch-fingerprints → freshness-filter → dedup sequence in their `filter()` methods.
- `publisher.py`: RSS feed generation with parameterized title/description (existing responsibility, minor extension).
- Frontend: all client-side features self-contained in each site's `index.html`.

### Principle VI — Knowledge Base Integrity ✓
- No changes to FFXIV analysis or prompt logic; knowledge base is unaffected.

**Gate result**: PASS — no constitution violations detected.

**Post-design re-check**: All design decisions in research.md and data-model.md are consistent with the above analysis. No new violations introduced.

## Project Structure

### Documentation (this feature)

```text
specs/003-ux-polish/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 decisions
├── data-model.md        # Phase 1 entities
├── quickstart.md        # Phase 1 integration test scenarios
├── contracts/
│   ├── freshness-filter.md    # Pipeline freshness filter contract
│   └── frontend-features.md  # Dismiss + theme + label + RSS link contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
src/
├── filter.py            ← add FRESHNESS_THRESHOLD_DAYS, _normalize_title_for_fingerprint(),
│                           title_fingerprint(), _extract_url_date(), _is_too_old_by_age(),
│                           freshness_filter()
├── storage.py           ← add title_fingerprint_for_article(), get_existing_title_fingerprints();
│                           expand content_fingerprint population to ALL articles in upsert_articles()
├── pipeline/
│   ├── base.py          ← no change (Protocol only)
│   ├── traffic.py       ← update filter() to call get_existing_title_fingerprints() + freshness_filter()
│   └── ffxiv.py         ← update filter() same as traffic; update publish() with FFXIV feed params
└── publisher.py         ← add feed_title + feed_description params to build_feed() and publish()

pages/
├── traffic/
│   └── index.html       ← P2: dismiss button + localStorage logic
│                           P3: theme toggle + CSS variables + OS pref detection
│                           P4: "收錄時間" date label
└── ffxiv/
    └── index.html       ← P2: dismiss button + localStorage logic (key: dismissed-ffxiv)
                            P3: theme toggle + CSS variables + OS pref detection
                            P4: "收錄時間" date label
                            P5: RSS subscription link in header
```

**Structure Decision**: Single-project, in-place extension of existing modules. No new Python modules, no new directories. All pipeline logic extends existing files at their current stage boundary.

## Complexity Tracking

> No constitution violations — this table is not required.
