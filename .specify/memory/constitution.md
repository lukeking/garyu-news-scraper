<!--
## Sync Impact Report

**Version change**: 1.3.0 → 2.0.0
**Bump rationale**: MAJOR — Principle IV is redefined (Free Tier Discipline → Explicit Budgets)
  and Technology Constraints stops fixing versions, models, plans and schedules. The rule this
  amendment adopts: the constitution states intent and invariants; values that change in
  routine operation live where they are enforced (config, workflow files, code next to the
  call), indexed in `docs/external-services.md`. Evidence that the old text had decayed
  silently: it named the `google-generativeai` SDK (not in `requirements.txt`; calls are REST),
  default model `gemini-2.0-flash` (code default `gemini-2.5-pro`, prod `gemini-3.7-flash`), a
  2.5-second delay (code uses per-model 4–12 s), a free-tier rule (pay-as-you-go since
  2026-06-22), and Gmail SMTP delivery (`src/mailer.py` removed as dead code in `ddf6c84`).
  1.3.0 itself wrote minute counts and timeout values into IV — the same mistake.

### Modified Principles
- II. Configuration over Code → adds: an example file that mirrors a production variable is
  committed; the variable remains the source of truth; the mirror list is the one in
  `scripts/check_config_drift.py` (spec 014 adds the two sources files to it).
- Operations: source changes update the mirror in a PR when one exists, replacing "Neither
  sources update requires a PR"; the canonical pipeline test no longer cites the removed email step.
- IV. Free Tier Discipline → **IV. Explicit Budgets**: every external service runs inside a
  written budget, overruns are visible, rate limits and per-run caps are explicit where the call
  is made; values live in `docs/external-services.md` and the files it points to.

### Added Sections
- None (the new file `docs/external-services.md` is an operational doc, not a section).

### Removed Sections
- Technology Constraints: SDK name, default model, FFXIV source list, schedule time, email delivery.

### Templates Checked
- ✅ `.specify/templates/plan-template.md` — Constitution Check gate is content-agnostic.
    No changes required.
- ✅ `.specify/templates/spec-template.md` — No principle text restated. No changes required.
- ✅ `.specify/templates/tasks-template.md` — Phase/parallel model is content-agnostic.
    No changes required.
- ✅ `.specify/templates/commands/` — Directory does not exist; skipped.
- ✅ `.github/workflows/*.yml` — every job already sets `timeout-minutes` (1.3.0).

### Deferred Items
- Principle I still names a **Notify** stage and Principle V still lists `src/mailer.py`; email
  was removed in `ddf6c84`. Principle I also calls the weekly workflow the authoritative
  environment, while a daily workflow now writes the buffer. Left for a separate decision.
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

- `config/sources_traffic.yml` is the sole source-of-truth for traffic news sources; it MUST be
  stored as the GitHub Environment Variable `SOURCES_TRAFFIC_YML` and MUST NOT be committed.
- `config/sources_ffxiv.yml` is the sole source-of-truth for FFXIV sources; it MUST be
  stored as the GitHub Environment Variable `SOURCES_FFXIV_YML` and MUST NOT be committed.
- A `config/*.example.yml` that mirrors a production variable is committed so the setting can be
  read and diffed in git; the variable remains the source of truth. Which files are mirrors is
  the list in `scripts/check_config_drift.py`, and that scheduled check fails when a mirror falls
  out of sync.
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

### IV. Explicit Budgets

Every external service the system consumes runs inside a budget that is written down, and
going over it MUST be visible rather than silent. This principle fixes the obligation, not the
values: plans, budgets, models, delays, caps and timeouts change in routine operation and live
where they are enforced, indexed in `docs/external-services.md`. Changing one is an ordinary
reviewed PR to that file and the setting it points to, not an amendment.

- Each paid or metered service MUST have its current plan, its budget and the date that plan
  was approved recorded in `docs/external-services.md`. Moving to a paid plan requires explicit
  approval recorded there and in the PR.
- Rate limits MUST be respected by explicit throttling whose value lives next to the call
  (code or configuration), not by convention.
- Generative AI calls per run MUST be bounded by explicit caps (articles, topics, retries) set in
  code or configuration, so cost cannot grow without a visible change.
- Every CI workflow job MUST set an explicit `timeout-minutes` as a runaway guard, sized from the
  job's observed maximum runtime with headroom; the value lives in the workflow file. CI usage
  MUST stay within the budget recorded in `docs/external-services.md`.
- Feeds and pages MUST be fetched from public endpoints without credentials for public data;
  robots.txt MUST be checked before adding an HTML source; requests MUST be spaced by delays.
- A new external service MUST have its budget recorded in `docs/external-services.md` before
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

The FFXIV knowledge base is the authoritative source for game-term normalization and MUST
be consulted by `src/analyzer.py` before generating any FFXIV summary.

- The knowledge base is stored in the Supabase `knowledge_base` table and queried at
  analysis runtime; it is the sole source of truth for FFXIV term translations.
- The AI analyzer MUST NOT invent game-term translations or romanizations. Unknown terms
  MUST be written as `[[term]]` placeholders so they can be resolved by the auto-KB job.
- The auto-KB job (`scripts/auto_kb.py`) runs weekly after the pipeline and MUST only write
  terms it can resolve with high confidence (sourced from official TW patch notes, TW wikis,
  or established community usage); it MUST NOT guess or include low-confidence entries.
- Manual KB additions are made directly via the Supabase dashboard or a migration script;
  no PR is required. The `auto_generated` column distinguishes automated from manual entries.
- Every term in the `knowledge_base` table MUST have a verified, accurate mapping —
  auto-generated entries are held to the same accuracy standard as manually added ones.
- If the `knowledge_base` table is empty or unreachable at pipeline startup, the pipeline
  MUST halt with a clear error rather than continuing with an empty translation set.

## Technology Constraints

These are the project's structural choices: changing one changes the shape of the system and
requires an amendment. Versions, model names, plans, sources and schedules are not listed here;
they are configuration and live where they are set (Principles II and IV).

- **Runtime**: Python 3; dependencies managed via `requirements.txt`.
- **AI Analysis**: an external LLM API called from `src/analyzer.py`; the model is chosen by
  configuration (`GEMINI_MODEL_NAME`). The current provider, model and plan are recorded in
  `docs/external-services.md`.
- **Storage**: Supabase (PostgreSQL); writes use the `service_role` key.
- **Knowledge Base**: Supabase `knowledge_base` table; queried at analysis runtime by
  `src/analyzer.py`; auto-expanded by `scripts/auto_kb.py`.
- **Sources**: public feeds, pages and APIs, as configured (Principle II).
- **Public API**: Cloudflare Worker (`workers/api/`); serves the `articles` data to frontends.
- **Frontend**: Cloudflare Pages (`pages/`); separate deployments for traffic and FFXIV.
- **Scheduling and CI**: GitHub Actions; schedules live in `.github/workflows/`.

## Operations & Deployment

Standard operating procedures that all contributors MUST follow.

- The canonical test for a full pipeline run is a manual dispatch of
  `.github/workflows/weekly.yml`. Confirm success by the run concluding successfully and by
  the weekly verification routine's report (`routines/weekly-verify/`).
- Local development MUST use `.env` (copied from `.env.example`) and local copies of both
  `config/sources_traffic.yml` and `config/sources_ffxiv.yml` (copied from their `.example`
  counterparts). All four files MUST remain in `.gitignore`.
- To add or modify traffic or FFXIV sources: edit `SOURCES_TRAFFIC_YML` or `SOURCES_FFXIV_YML`
  in GitHub Environment Variables. If that variable has a mirror (Principle II), update the
  mirror to match in a PR; the scheduled drift check fails when it was skipped.
- To rotate secrets: update the relevant GitHub Secret. No PR needed.
- The `SUPABASE_SERVICE_ROLE_KEY` secret MUST be shared between the weekly workflow and the
  Cloudflare Worker; both require the ability to bypass RLS on the `articles` table.
- To add or modify KB terms manually: insert or update rows in the Supabase `knowledge_base`
  table directly (dashboard or migration script). Set `auto_generated = false` for manually
  verified entries. No PR required.
- Auto-generated KB entries are written by `scripts/auto_kb.py` after each weekly pipeline
  run. They take effect on the next pipeline run. Review auto-generated entries periodically
  via the Supabase dashboard to verify accuracy.

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

**Version**: 2.0.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-10-13
