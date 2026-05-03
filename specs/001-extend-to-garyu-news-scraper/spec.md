# Feature Specification: Extend to Garyu News Scraper (FFXIV Integration)

**Feature Branch**: `001-extend-to-garyu-news-scraper`
**Created**: 2026-05-03
**Status**: Draft
**Input**: Extend the existing traffic-issue-scraper codebase into garyu-news-scraper by
adding FFXIV 8.0 battle information scraping, implementing a knowledge base for term
normalization, and preserving all existing traffic news functionality.

## User Scenarios & Testing

### User Story 1 - FFXIV Weekly Digest Collection (Priority: P1)

A reader subscribed to the Garyu News system receives a weekly digest that includes
FFXIV 8.0 patch notes, battle content updates, and community discussion summaries
sourced from Reddit r/ffxiv and official JP/TW FFXIV sites — in addition to existing
traffic news.

**Why this priority**: Core deliverable; all other stories depend on collection working.

**Independent Test**: Running `python main.py` with `sources_ffxiv.yml` configured
produces articles with `content_type: ffxiv` in the pipeline output and Supabase.

**Acceptance Scenarios**:

1. **Given** `SOURCES_FFXIV_YML` is set with Reddit RSS and a JP patch note URL,
   **When** `collect_all()` is called,
   **Then** articles from both traffic and FFXIV sources appear, each tagged with
   the correct `content_type`.

2. **Given** FFXIV sources are unreachable,
   **When** `collect_all()` is called,
   **Then** the pipeline continues with traffic articles only and logs a warning per source.

---

### User Story 2 - FFXIV Knowledge Base Analysis (Priority: P2)

The AI analyzer produces FFXIV summaries that use correct Traditional Chinese game
terminology sourced from `knowledge-base.md`, without inventing translations.

**Why this priority**: Without the knowledge base, FFXIV summaries contain incorrect or
inconsistent translations, making them unusable for readers.

**Independent Test**: Running analysis on a sample FFXIV article produces a summary
where all FFXIV-specific terms match entries in `knowledge-base.md`.

**Acceptance Scenarios**:

1. **Given** `knowledge-base.md` contains the entry for "零式" → correct TW term,
   **When** the analyzer processes a Savage raid article,
   **Then** the summary uses the mapped term, not an invented translation.

2. **Given** an article contains an FFXIV term not in `knowledge-base.md`,
   **When** the analyzer processes it,
   **Then** the term is left untranslated and a log warning is emitted.

---

### User Story 3 - Dual-Content Supabase Storage & API (Priority: P3)

Both traffic and FFXIV articles are stored in the shared Supabase `articles` table,
distinguishable by a `content_type` column, and the Cloudflare Worker API supports
filtering by content type.

**Why this priority**: Required for the frontend to display FFXIV content separately
from traffic news.

**Independent Test**: After a pipeline run, Supabase contains rows with both
`content_type='traffic'` and `content_type='ffxiv'` for the same `week_id`.

**Acceptance Scenarios**:

1. **Given** a full pipeline run completes with both source types,
   **When** querying Supabase,
   **Then** rows exist with `content_type='traffic'` and `content_type='ffxiv'`.

2. **Given** the Worker receives `?content_type=ffxiv`,
   **When** it queries Supabase,
   **Then** only FFXIV articles are returned.

---

### Edge Cases

- What if Reddit RSS returns 0 new posts? Pipeline continues with traffic only.
- What if `knowledge-base.md` is missing or empty? Pipeline fails fast with a clear error
  before FFXIV analysis begins (Principle VI).
- What if the same article appears in both Reddit RSS and an HTML source? `filter.py`
  deduplication catches it via content hash.
- What if `SOURCES_FFXIV_YML` is not set? System falls back to traffic-only mode
  (backwards compatible; no hard failure).

## Requirements

### Functional Requirements

- **FR-001**: System MUST collect FFXIV articles from RSS and HTML sources in `sources_ffxiv.yml`.
- **FR-002**: System MUST tag each collected article with a `content_type` field (`'traffic'`
  or `'ffxiv'`), set by the collector from the source config entry.
- **FR-003**: System MUST load `knowledge-base.md` before FFXIV analysis and inject relevant
  entries into the Gemini prompt.
- **FR-004**: System MUST NOT invent FFXIV term translations; unknown terms MUST be left
  untranslated with a log warning.
- **FR-005**: System MUST persist a `content_type` column in the Supabase `articles` table.
- **FR-006**: System MUST remain backwards-compatible: if `SOURCES_FFXIV_YML` is unset,
  traffic-only mode MUST work unchanged.
- **FR-007**: System MUST NOT break the existing weekly GitHub Actions workflow.
- **FR-008**: The Cloudflare Worker API MUST support filtering by `content_type` via query
  parameter (default: all content types, for backwards compatibility).

### Key Entities

- **Article**: Pipeline dict with: `title`, `link`, `source`, `published`, `summary`,
  `content_type`, and (after analysis) `analysis`.
- **Analysis**: AI output JSONB with: `summary`, `analysis`, `importance`,
  `importance_reason`, `tags`.
- **KnowledgeBaseEntry**: Markdown table row with: JP term, TW term, EN term, category, notes.
- **Source**: Config entry with: `name`, `type`, `url`, `enabled`, `content_type`, plus
  type-specific fields.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Full dual-content pipeline (traffic + FFXIV) completes within 15 minutes on
  GitHub Actions.
- **SC-002**: Zero existing traffic pipeline regressions after the FFXIV extension merges.
- **SC-003**: Supabase contains FFXIV articles tagged `content_type='ffxiv'` after the first
  successful run.
- **SC-004**: `knowledge-base.md` contains ≥20 core FFXIV 8.0 term entries before first
  production run.

## Assumptions

- Reddit r/ffxiv RSS is publicly accessible without authentication.
- `jp.finalfantasyxiv.com/lodestone/news/` is publicly scrapable; robots.txt does not
  disallow the news category path.
- The existing `articles` Supabase table can be extended with a `content_type` column
  without breaking existing data (column defaults to `'traffic'`).
- Knowledge base is maintained manually via PRs; automated CI validation is out of scope for v1.
- Email digest (`mailer.py`) update is a follow-on task; v1 focuses on pipeline and storage.
