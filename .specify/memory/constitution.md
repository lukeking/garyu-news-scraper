<!--
## Sync Impact Report

**Version change**: 2.2.0 → 2.3.0
**Bump rationale**: MINOR — a section is added, Layered Acceptance: a change is split by
  acceptance scope into slices, one PR each, and each scope has a verification that is enough for
  it, so only the slice that needs a scheduled run waits for one. No principle is removed or
  redefined. Source: spec 020 (`specs/020-layered-acceptance/`, FR-011 to FR-020; BACKLOG
  `GNS-20261114-bh8`). Before this, acceptance conditions were routinely written as "after the
  next scheduled weekly run", which made the schedule the clock for every change although nothing
  in this constitution made it the authority.
  The spec's tasks name this amendment 2.1.1 → 2.2.0; 2.2.0 was used on 2026-11-18 (#218), so
  this one is 2.3.0.

### Modified Principles
- None

### Modified Sections
- Operations & Deployment → new bullet: the non-publishing entry, what it verifies and what it
  does not.
- Governance → Compliance review: a PR description states the slice's acceptance scope, the
  verification used and its result.

### Added Sections
- Layered Acceptance (between Operations & Deployment and Governance).

### Removed Sections
- None

### Templates Checked
- ✅ `.specify/templates/` — holds no copies (the spec-kit templates are user-level since #179).
    Task grouping is carried by each plan's Constitution Check, not by a template copy here.
- ✅ `docs/dry-run.md` — already describes the non-publishing entry; this file points to it.
- ⚠ The maintainer's untracked `CLAUDE.local.md` ("Spec closeout 綁定") said closeout always
    happens in the PR that completes the work. It is not in version control; it is updated on the
    maintainer's machine with this change.

### Deferred Items
- None
-->

# Garyu News Scraper Constitution
## (台灣機車交通 & FFXIV 資訊聚合系統)

## Core Principles

### I. Pipeline Integrity

The system is a strictly ordered data pipeline:
**Collect → Filter → Analyze → Store → Publish**.

- Each stage MUST complete successfully before the next begins.
- Stage failures MUST surface with actionable error messages; silent failures are forbidden.
- No stage may skip upstream output or produce output without valid upstream input.
- Both content types (traffic news and FFXIV information) MUST pass through the same
  pipeline stage contract; content-type-specific logic is encapsulated within each stage.
- The scheduled pipeline workflows on GitHub Actions (the daily traffic buffer and the two weekly
  runs, one per content type) are the authoritative execution environment; local runs are for
  development and debugging only.
- Traffic runs across two workflows: every run, daily and weekly, collects, filters and stores
  into a buffer, and the weekly traffic workflow then analyzes that buffer and publishes. The
  buffer is the upstream output the weekly Analyze stage consumes, so the weekly Analyze and
  Publish stages do not wait on the weekly run's own collection: when that collection fails or
  stores nothing, they still run on what earlier runs stored, and the run MUST end as failed so
  the gap is visible. FFXIV runs entirely in its own weekly workflow.

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

- The canonical test for a full pipeline run is a manual dispatch of both weekly workflows,
  `.github/workflows/weekly-traffic.yml` and `.github/workflows/weekly-ffxiv.yml`, each confirmed
  by its run concluding successfully. The weekly verification routine (`routines/weekly-verify/`)
  verifies the scheduled weekly runs; its report confirms a manual dispatch only when that
  dispatch is a run it verified.
- The non-publishing entry is a manual dispatch of `.github/workflows/weekly-dry-run.yml`. It
  runs the weekly pipeline on GitHub Actions, the same environment as the scheduled workflows,
  without storing, publishing or deploying. It verifies wiring and output against the buffer and
  pool as they are when it is dispatched; it is not a rehearsal of the next scheduled run, and it
  MUST NOT cancel or block one. Its LLM calls count against the same budget as the scheduled
  runs (Principle IV). How to dispatch it and what it leaves behind: `docs/dry-run.md`.
- Local development MUST use `.env` (copied from `.env.example`) and local copies of both
  `config/sources_traffic.yml` and `config/sources_ffxiv.yml` (copied from their `.example`
  counterparts). All four files MUST remain in `.gitignore`.
- To add or modify traffic or FFXIV sources: edit `SOURCES_TRAFFIC_YML` or `SOURCES_FFXIV_YML`
  in GitHub Environment Variables. If that variable has a mirror (Principle II), update the
  mirror to match in a PR; the scheduled drift check fails when it was skipped.
- To rotate secrets: update the relevant GitHub Secret. No PR needed.
- The `SUPABASE_SERVICE_ROLE_KEY` secret MUST be shared between the weekly workflows and the
  Cloudflare Worker; both require the ability to bypass RLS on the `articles` table.
- To add or modify KB terms manually: insert or update rows in the Supabase `knowledge_base`
  table directly (dashboard or migration script). Set `auto_generated = false` for manually
  verified entries. No PR required.
- Auto-generated KB entries are written by `scripts/auto_kb.py` after each weekly pipeline
  run. They take effect on the next pipeline run. Review auto-generated entries periodically
  via the Supabase dashboard to verify accuracy.

## Layered Acceptance

How a change is split for delivery and how each part is accepted. It applies to spec-driven work
and to PRs opened directly. For this project only, it overrides the user-level convention of one
PR per spec.

**Slices**

- A change MUST be split by acceptance scope. Each slice is one PR and is accepted on its own.
- Each slice MUST state its acceptance scope, the verification it uses, and whether it has to
  wait for a real run. Only the slice that needs a real run waits for one; the others merge
  without it.
- A slice that fails acceptance is fixed in a slice of its own, with its own PR. Slices already
  merged stay complete.

**Acceptance scopes**

Each scope has a verification that is enough for it. The list gives the scopes met so far; it is
not complete.

| Scope | What the slice proves | Enough to verify it |
|---|---|---|
| The function itself | the logic, or the rule or record text, is what the requirement asks for | unit tests; for text, a review against the requirements it implements |
| Required input | the run obtains what it needs: sources are reachable, collected and selected | a non-publishing run up to selection on GitHub Actions (reachability depends on where the run executes), or the log of a daily run |
| Output | what the pipeline produces from that input is right | a non-publishing run that reaches the output in question, or a replay of stored input |
| Read-back | the change behaves in a real run once it is live | reading one named real run; this is the slice that waits |
| Correction | a fix for a slice that failed acceptance | the verification that failed, run again |
| State across runs | marks, fingerprints, expiry and cross-run deduplication | two consecutive real runs; a single non-publishing run cannot show it and MUST NOT write that state |
| Scheduling and chaining | the schedule fires; follow-up workflows and deployments are triggered | a real scheduled event for the schedule itself; a manual dispatch for the rest |
| Resources | run time, API cost, rate limiting | a real run, or a non-publishing run that calls the LLM |

- Observation is waiting for data to accumulate, not accepting a change. It MUST be written apart
  from acceptance and MUST NOT be an acceptance condition of any slice.
- A change that needs a scope not listed names it in its plan, or in the PR description when the
  PR is opened directly, with what the slice proves and the verification that is enough for it.
  Adding the scope to this table is an amendment.

**Writing acceptance conditions**

- An acceptance condition MUST name the earliest verification that is enough: a non-publishing
  run, a replay, or the log of a daily run. Waiting for a scheduled weekly run is used only for
  what no other verification can show, and the condition MUST say why nothing else can.
- A condition that needs several real runs ("two weeks in a row") belongs to the read-back slice,
  not to the slices that deliver the function.

**Process**

- In spec-driven work, tasks MUST be grouped by acceptance scope. Each group is a slice: it states
  its scope and verification and maps to one PR. A group that waits for a real run MUST be placed
  where it does not block the other groups. Each plan's Constitution Check carries this into the
  feature.
- A PR opened directly MUST state its slice's acceptance scope, verification and result in its
  description, and name the slices that remain when there are more.
- Going live and acceptance complete are two moments. A read-back is a slice of the same change,
  with its own PR and its own BACKLOG row; the merge and completion of the slices that deliver
  the function do not wait for it.
- When a change ships as several PRs, its BACKLOG row is removed in the PR of the last slice that
  can be verified before going live. When a read-back remains, that same PR opens the read-back's
  row. The PR of every earlier slice says why the row is still there.
- A read-back MUST have a reminder that fires on its own, attached to its BACKLOG row as a date;
  an unticked task or an untracked handoff file is not one. When the reminder fires, first confirm
  that the run exists, then read it. A read-back whose row cannot carry a date MUST instead be
  written into `routines/weekly-verify/FOCUS.md`, and each weekly roll of that file MUST carry
  the items not yet read back.

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
  `src/analyzer.py`, `src/storage.py`, `src/publisher.py`) MUST verify
  compliance with Principles I–III in the PR description.
- PRs that touch FFXIV analysis logic MUST also verify compliance with Principle VI.
- Every PR that delivers a slice of a change MUST state in its description the slice's
  acceptance scope, the verification used and its result (Layered Acceptance).
- Complexity violations (e.g., a new cross-module dependency) MUST be documented in the
  plan's Complexity Tracking table before implementation begins.

**Version**: 2.3.0 | **Ratified**: 2026-04-25 | **Last Amended**: 2026-11-28
