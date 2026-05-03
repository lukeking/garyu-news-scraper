<!--
## Sync Impact Report

**Version change**: 1.0.0 → 1.1.0
**Bump rationale**: MINOR — new Principle VI (Knowledge Base Integrity) added; Principles II and V
  materially expanded for dual-content (traffic + FFXIV) scope; Technology Constraints and
  Operations updated accordingly.

### Modified Principles
- II. Configuration over Code → expanded: `sources_ffxiv.yml` added as second mandatory
  externalized config; `SOURCES_FFXIV_YML` GitHub Environment Variable rule added.
- V. Single Responsibility per Module → updated: `publisher.py` added to the canonical module
  list; future `src/scrapers/traffic/` and `src/scrapers/ffxiv/` sub-structure documented.

### Added Sections
- Principle VI: Knowledge Base Integrity (new; FFXIV term-normalization requirement)
- Technology Constraints: Reddit RSS source, JP forum HTML scraping, knowledge-base.md

### Removed Sections
- None

### Templates Checked
- ✅ `.specify/templates/plan-template.md` — "Constitution Check" gate is content-agnostic;
    aligns with updated Principles I–VI. No structural changes required.
- ✅ `.specify/templates/spec-template.md` — Generic requirements structure; compatible.
    No changes required.
- ✅ `.specify/templates/tasks-template.md` — Phase/parallel model covers both scrapers and
    knowledge-base tasks. No changes required.
- ✅ `.specify/templates/commands/` — No command templates found; skipped.

### Deferred Items
- None
-->

# Garyu News Scraper Constitution
## (台灣機車交通 & FFXIV 資訊聚合系統)

## Core Principles

### I. Pipeline Integrity

The system is a strictly ordered data pipeline:
**Collect → Filter → Analyze → Store → Notify**.

- Each stage MUST complete successfully before the next begins.
- Stage failures MUST surface with actionable error messages; silent failures are forbidden.
- No stage may skip upstream output or produce output without valid upstream input.
- Both content types (traffic news and FFXIV information) MUST pass through the same
  pipeline stage contract; content-type-specific logic is encapsulated within each stage.
- The weekly GitHub Actions workflow is the authoritative execution environment; local runs
  are for development and debugging only.

### II. Configuration over Code

News sources, AI model names, and credentials MUST be externalized from source code.

- `config/sources.yml` is the sole source-of-truth for traffic news sources; it MUST be
  stored as the GitHub Environment Variable `SOURCES_YML` and MUST NOT be committed.
- `config/sources_ffxiv.yml` is the sole source-of-truth for FFXIV sources; it MUST be
  stored as the GitHub Environment Variable `SOURCES_FFXIV_YML` and MUST NOT be committed.
- Secrets (API keys, passwords) MUST live in GitHub Secrets (production) or `.env` (local
  development only). Neither `.env` nor either sources config may be committed.
- Adding, removing, or disabling a source, or swapping AI models, MUST require no code
  change — only a configuration update.

### III. Idempotency & Deduplication

Repeated pipeline runs on the same underlying news corpus MUST produce identical stored state.

- Deduplication MUST occur in `src/filter.py` before articles reach the analysis stage.
- Storage upserts in `src/storage.py` MUST use stable content hashes as primary keys, not
  timestamps, run IDs, or auto-increment values. This prevents duplicate rows across retries.
- The Supabase `articles` table MUST be written using the `SUPABASE_SERVICE_ROLE_KEY`; the
  anonymous key MUST NOT be used for writes to avoid RLS-related data loss.

### IV. Free Tier Discipline

All external service usage MUST remain within free tier limits. Paid usage requires explicit
approval and documentation in the relevant PR.

- **Gemini**: MUST NOT exceed free tier rate limits; the 2.5-second inter-request delay MUST
  be preserved; the per-run article cap (default 30) MUST be respected.
- **GitHub Actions**: Each workflow run MUST complete within 10 minutes; total monthly usage
  MUST remain within the 2,000 free minutes.
- **Reddit RSS**: MUST use the public RSS endpoint (`/new/.rss`) without OAuth; rate limits
  MUST be respected via appropriate request delays.
- **JP Forums / Official Sites**: MUST use public web scraping only; robots.txt MUST be
  checked before adding a new HTML source.
- New external service integrations MUST be evaluated against free tier constraints before
  adoption.

### V. Single Responsibility per Module

Each Python module in `src/` owns exactly one pipeline stage or concerns.

- `src/collector.py` collects raw articles from all configured sources (traffic + FFXIV).
- `src/filter.py` filters and deduplicates across all content types.
- `src/analyzer.py` analyzes, dispatching to content-type-specific prompts internally.
- `src/storage.py` persists to Supabase.
- `src/publisher.py` builds and publishes the static site output.
- `src/mailer.py` composes and sends the weekly digest email.
- As the FFXIV scraper grows, traffic-specific and FFXIV-specific collection logic MAY be
  promoted to `src/scrapers/traffic/` and `src/scrapers/ffxiv/` sub-modules; this
  reorganization MUST be done as a single, complete migration — not piecemeal.
- Cross-module logic MUST be justified. Helper utilities belong in a clearly named shared
  module, not in a stage module.
- New abstractions require explicit rationale in the relevant spec or PR. Three similar lines
  are better than a premature abstraction (YAGNI).

### VI. Knowledge Base Integrity

The FFXIV knowledge base (`knowledge-base.md`) is the authoritative source for game-term
normalization and MUST be consulted by `src/analyzer.py` before generating any FFXIV summary.

- `knowledge-base.md` MUST NOT be committed with placeholder entries; every term listed
  MUST have a verified, accurate mapping.
- The AI analyzer MUST NOT invent game-term translations or romanizations; unknown terms
  MUST trigger a knowledge-base update PR rather than a best-guess inline translation.
- New terms discovered during pipeline runs MAY be proposed for addition via PR; the PR
  description MUST document the source of the mapping (e.g., official patch note, JP wiki).
- `knowledge-base-template.md` is the canonical template for term entries; it MUST be kept
  in sync with the structure of `knowledge-base.md`.

## Technology Constraints

The following technology choices are fixed for this project. Deviations require a constitution
amendment.

- **Runtime**: Python 3.x; dependency list managed via `requirements.txt`.
- **AI Analysis**: Gemini API (google-generativeai SDK); default model `gemini-2.0-flash`,
  overridable via `GEMINI_MODEL_NAME` secret without code changes.
- **Storage**: Supabase (PostgreSQL); accessed via `supabase-py` SDK using `service_role` key.
- **FFXIV Sources**: Reddit RSS (`/r/ffxiv/new/.rss`), JP official forums HTML scraping
  (`forum.square-enix.com/ffxiv/` and official patch note pages), and Taiwan/JP FFXIV
  official sites for structured patch note pages.
- **Knowledge Base**: Markdown file (`knowledge-base.md`); read at analysis runtime; updated
  via PRs.
- **Public API**: Cloudflare Worker (`workers/api/`); serves the `articles` data to frontends.
- **Frontend**: Cloudflare Pages (`pages/`); separate deployments for traffic and FFXIV
  content (distinct domains or sub-paths).
- **Scheduling**: GitHub Actions weekly workflow (Monday 08:00 Taiwan time).
- **Email delivery**: Gmail SMTP using an App Password (16-character format).

## Operations & Deployment

Standard operating procedures that all contributors MUST follow.

- The canonical test for a full pipeline run is: GitHub Actions UI → **Actions →
  週報自動系統 → Run workflow**. Confirm success by checking that `信件寄送成功` appears
  in the run log.
- Local development MUST use `.env` (copied from `.env.example`) and local copies of both
  `config/sources.yml` and `config/sources_ffxiv.yml` (copied from their `.example` counterparts).
  All four files MUST remain in `.gitignore`.
- To add or modify traffic sources: edit `SOURCES_YML` in GitHub Environment Variables.
- To add or modify FFXIV sources: edit `SOURCES_FFXIV_YML` in GitHub Environment Variables.
- Neither sources update requires a PR.
- To rotate secrets: update the relevant GitHub Secret. No PR needed.
- The `SUPABASE_SERVICE_ROLE_KEY` secret MUST be shared between the weekly workflow and the
  Cloudflare Worker; both require the ability to bypass RLS on the `articles` table.
- Knowledge base updates MUST go through a PR so term mappings are peer-reviewed before
  they influence production summaries.

## Governance

This constitution supersedes all other development practices, conventions, or tribal knowledge
for this project. When a PR introduces code that conflicts with a principle above, the principle
wins unless the constitution is formally amended.

**Amendment procedure**:
1. Open a PR that updates this file with the proposed change and a rationale comment.
2. Bump the version according to semantic rules (MAJOR: principle removed/redefined; MINOR:
   principle or section added; PATCH: wording/clarity fix).
3. Update `LAST_AMENDED_DATE` to the merge date.
4. The PR description MUST include the Sync Impact Report section for the change.

**Compliance review**:
- All PRs that touch a pipeline module (`src/collector.py`, `src/filter.py`,
  `src/analyzer.py`, `src/storage.py`, `src/publisher.py`, `src/mailer.py`) MUST verify
  compliance with Principles I–III in the PR description.
- PRs that touch FFXIV analysis logic MUST also verify compliance with Principle VI.
- Complexity violations (e.g., a new cross-module dependency) MUST be documented in the
  plan's Complexity Tracking table before implementation begins.

**Version**: 1.1.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-05-03
