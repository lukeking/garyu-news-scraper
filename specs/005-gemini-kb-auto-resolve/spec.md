# Feature Specification: Gemini-Powered Self-Evolving Knowledge Base

**Feature Branch**: `005-gemini-kb-auto-resolve`  
**Created**: 2026-05-11  
**Status**: Draft  
**Input**: User description: "is it possible to ask gemini do the same thing as the subagent `ffxiv-term-translator` do? because I also want to automate kb resolution, make it self-evolving knowledge base. thus we also need a cron job to run this process every week right after ffxiv weekly news has finished deploying."

## Background

The FFXIV news pipeline uses a knowledge base to translate Japanese FFXIV terms into Traditional Chinese (TW) equivalents used by TW players. When the AI analysis encounters a term not in the KB, it writes a `[[term]]` placeholder in the article's analysis data.

Previously the KB lived in `knowledge-base.md` — a manually maintained file requiring a PR to update. This feature replaces that file with a **Supabase `knowledge_base` table** as the single source of truth, automates KB expansion via Gemini, migrates the existing pipeline to read terms from Supabase, and surfaces still-unresolvable terms as a tag cloud on the FFXIV news page so users can see what's missing.

The full automated loop:
1. Weekly pipeline fetches KB terms from Supabase → analyzes articles → writes `[[term]]` for unknowns
2. Auto-KB job runs after pipeline → collects misses → Gemini resolves → writes new terms directly to Supabase → re-resolves `[[term]]` markers in articles inline
3. Terms Gemini cannot resolve appear as a tag cloud on the FFXIV news page

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Automated KB Expansion via Gemini (Priority: P1)

Every Monday, after the weekly FFXIV news pipeline finishes deploying, an auto-KB job runs. It collects all unique `[[term]]` placeholders from Supabase articles, asks Gemini to identify the correct TW colloquial equivalent for each unknown term, writes confident results directly to the Supabase `knowledge_base` table, then immediately re-resolves all `[[term]]` markers in articles that can now be patched — no PR, no manual step.

**Why this priority**: This is the core loop that makes the KB self-evolving. Every weekly run either resolves outstanding unknowns or surfaces them clearly.

**Independent Test**: Insert a `[[テスト用語]]` placeholder into a Supabase article row, trigger the auto-KB job, and verify the Supabase `knowledge_base` table gains a new row for that term and the article's `[[テスト用語]]` placeholder is replaced.

**Acceptance Scenarios**:

1. **Given** the weekly pipeline has completed and Supabase contains FFXIV articles with `[[term]]` placeholders, **When** the auto-KB job runs, **Then** each confidently-resolved term is written as a new row to the Supabase `knowledge_base` table and all matching `[[term]]` markers in articles are replaced inline.
2. **Given** Gemini identifies a TW equivalent confidently, **When** the entry is written to Supabase, **Then** the row contains JP Term, TW Term, EN Term, Category, and Notes in the standard KB schema.
3. **Given** Gemini cannot confidently identify a TW equivalent, **When** the job runs, **Then** that term is NOT written to Supabase and is logged as `[KB AUTO-MISS]` — no guesses.
4. **Given** there are no `[[term]]` placeholders in Supabase, **When** the auto-KB job runs, **Then** it exits cleanly with a log message indicating nothing to resolve.

---

### User Story 2 — Pipeline Reads KB from Supabase (Priority: P2)

The existing weekly pipeline, which currently reads `knowledge-base.md` to build the translation lookup for Gemini's analysis prompt, is migrated to read KB terms directly from the Supabase `knowledge_base` table instead. `knowledge-base.md` is retired entirely.

**Why this priority**: Without this migration, newly auto-added KB terms never reach the weekly analysis pipeline — the two halves of the system remain disconnected. This is the prerequisite that makes the KB self-evolving end-to-end.

**Independent Test**: Add a new term row to the Supabase `knowledge_base` table, trigger the weekly pipeline via `workflow_dispatch`, and verify the analysis output uses the new TW term instead of writing `[[term]]`.

**Acceptance Scenarios**:

1. **Given** a term exists in the Supabase `knowledge_base` table, **When** the weekly pipeline runs, **Then** Gemini's analysis prompt includes that term and the resulting article analysis contains the TW translation, not a `[[term]]` placeholder.
2. **Given** `knowledge-base.md` is removed from the repository, **When** the weekly pipeline runs, **Then** it completes without error, reading all KB terms from Supabase.
3. **Given** the Supabase `knowledge_base` query fails at pipeline startup, **When** the failure occurs, **Then** the pipeline logs an error and halts rather than running with an empty KB that would produce all `[[term]]` output.

---

### User Story 3 — Tag Cloud of Unresolved Terms on FFXIV Page (Priority: P3)

Terms that remain unresolved after the auto-KB job (Gemini could not confidently translate them) are displayed as a tag cloud at the top of the FFXIV news page. Each tag represents one untranslated term. The cloud is visually distinct — not a list or table — and communicates to users that these terms need attention.

**Why this priority**: Makes the system's knowledge gaps visible to the people most likely to know the answers — FFXIV players reading the news. Transforms a silent pipeline failure into a transparent, human-readable signal.

**Independent Test**: Ensure at least one `[[term]]` placeholder remains unresolved in Supabase, load the FFXIV news page, and verify the tag cloud section appears at the top with that term as a tag.

**Acceptance Scenarios**:

1. **Given** one or more `[[term]]` placeholders exist in Supabase articles after the auto-KB job runs, **When** a user loads the FFXIV news page, **Then** a tag cloud section appears at the top of the page showing each unique unresolved term as a tag.
2. **Given** all `[[term]]` placeholders have been resolved, **When** a user loads the FFXIV news page, **Then** the tag cloud section is hidden (not rendered as an empty section).
3. **Given** the same term appears across multiple articles, **When** the tag cloud is rendered, **Then** it appears as a single tag (deduplicated), not repeated.

---

### User Story 4 — Auto-KB Job Triggered After Weekly Deploy (Priority: P4)

The auto-KB job triggers automatically on successful completion of the weekly pipeline workflow — not on a fixed clock offset — so it always runs after new KB miss data has been written to Supabase.

**Why this priority**: A `workflow_run` trigger eliminates the race condition where a fixed-offset cron fires before the pipeline has written this week's `[[term]]` misses.

**Independent Test**: Run the weekly pipeline via `workflow_dispatch` and verify the auto-KB job starts within seconds of the pipeline's final step completing.

**Acceptance Scenarios**:

1. **Given** the weekly pipeline completes successfully, **When** the pipeline finishes, **Then** the auto-KB job triggers automatically.
2. **Given** the weekly pipeline fails mid-run, **When** the failure occurs, **Then** the auto-KB job does NOT trigger.

---

### Edge Cases

- What happens when Gemini suggests a term that already exists in the Supabase `knowledge_base` table? The auto-KB job skips it (deduplication happens before the Gemini call) and logs `[KB CONFLICT]`.
- What happens when the Gemini API is unavailable? The job logs the failure, exits 0 (non-blocking), and existing `[[term]]` markers remain for the next run.
- What happens when the same unknown term appears across many articles? Deduplication ensures Gemini is queried once per unique term per run.
- What happens when the Supabase `knowledge_base` query fails at auto-KB job startup? Job logs error and exits 0 — does not proceed with empty KB context.
- What happens when the FFXIV page has no unresolved terms? The tag cloud section is hidden entirely — no empty placeholder shown.

## Requirements *(mandatory)*

### Functional Requirements

**Auto-KB job**

- **FR-001**: The auto-KB job MUST collect all unique `[[term]]` KB miss placeholders from Supabase FFXIV articles.
- **FR-002**: The auto-KB job MUST deduplicate collected terms against the current Supabase `knowledge_base` table before querying Gemini — only truly unknown terms are sent.
- **FR-003**: The auto-KB job MUST query Gemini with unknown terms and instruct it to return only high-confidence TW equivalents (sourced from official FFXIV TW resources, wikis, or player community usage) — no guesses.
- **FR-004**: The auto-KB job MUST write each confidently-resolved term directly to the Supabase `knowledge_base` table without opening a PR or requiring human intervention.
- **FR-005**: The auto-KB job MUST immediately re-resolve `[[term]]` markers in Supabase articles after writing new KB entries (inline re-resolution, same run).
- **FR-006**: The auto-KB job MUST log `[KB AUTO-MISS]` for each term Gemini cannot confidently resolve and MUST NOT write those terms to Supabase.
- **FR-007**: The auto-KB job MUST NOT trigger if the weekly pipeline workflow failed.
- **FR-008**: The auto-KB job MUST complete within 10 minutes.

**Pipeline migration**

- **FR-009**: All ~60 existing term rows in `knowledge-base.md` MUST be migrated to the Supabase `knowledge_base` table via a one-time migration script before `knowledge-base.md` is deleted — no existing terms are lost or rebuilt from scratch.
- **FR-010**: The weekly pipeline MUST read KB terms from the Supabase `knowledge_base` table at startup and use them to build the Gemini analysis context — it MUST NOT read `knowledge-base.md`.
- **FR-011**: If the Supabase `knowledge_base` query fails at pipeline startup, the pipeline MUST halt with an error rather than continuing with an empty KB.
- **FR-012**: `knowledge-base.md` MUST be removed from the repository only after the migration script has been run and the row count in Supabase is verified to match the original file.

**Frontend tag cloud**

- **FR-013**: The FFXIV news page MUST display a tag cloud section at the top of the page containing all unique `[[term]]` values found across displayed articles.
- **FR-014**: The tag cloud MUST be hidden when no unresolved terms exist.
- **FR-015**: Each term MUST appear as a single deduplicated tag regardless of how many articles contain it.
- **FR-016**: The tag cloud MUST NOT use a list or table layout — tags must be rendered as a freeform visual pool.

### Key Entities

- **KB Term** (Supabase `knowledge_base` table row): The live source of truth for all TW translations. Contains JP Term, TW Term, EN Term, Category, Notes, and an `auto_generated` flag indicating whether the row was added by the auto-KB job or manually.
- **KB Miss Term**: A unique string `T` found inside a `[[T]]` marker in Supabase `articles.analysis` JSONB, where `T` is absent from the `knowledge_base` table.
- **Auto-KB Entry**: A new KB Term row written directly to Supabase by the auto-KB job after Gemini resolution — no PR involved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After each weekly pipeline run that produces KB misses, the auto-KB job completes and writes resolved terms to Supabase within 15 minutes of the pipeline finishing — no manual steps required.
- **SC-002**: 80% or more of recurring `[[term]]` placeholders (appearing in at least two consecutive weekly runs) are resolved within one weekly cycle after this feature ships.
- **SC-003**: The weekly pipeline runs successfully with zero references to `knowledge-base.md` — verified by removing the file and confirming no pipeline errors.
- **SC-004**: The `[[term]]` placeholder count in Supabase trends toward zero over four consecutive weeks.
- **SC-005**: The FFXIV news page tag cloud correctly appears and disappears based on the presence of unresolved terms — verified by controlled Supabase state.
- **SC-006**: The auto-KB job never blocks or fails the weekly pipeline — all auto-KB failures are non-blocking and logged.

## Assumptions

- The `GEMINI_API_KEY` GitHub Secret already exists and is reused by the auto-KB job — no new credentials needed.
- A new `knowledge_base` table is created in Supabase with columns: `jp_term`, `tw_term`, `en_term`, `category`, `notes`, `auto_generated` (bool). Existing KB content from `knowledge-base.md` is migrated to this table as part of this feature.
- The auto-KB job uses the same Gemini model already configured for the weekly pipeline (`GEMINI_MODEL_NAME`).
- The auto-KB job is triggered via `workflow_run` on successful completion of the `Garyu News Scraper 週報` workflow.
- The Cloudflare Worker API already serves `articles.analysis` JSONB to the frontend; the frontend can extract `[[term]]` patterns client-side from the analysis data it already receives — no new API endpoint is needed for the tag cloud.
- The existing `resolve-kb-misses.yml` workflow (triggered by `knowledge-base.md` pushes) is retired as part of this feature — re-resolution is now handled inline by the auto-KB job.
- Tag size proportional to term frequency across articles is explicitly deferred as a future enhancement and is not in scope for this feature.
- Human review of auto-generated KB entries is not required before they become active — Gemini's confidence gate is the quality control mechanism.

## Clarifications

### Session 2026-05-11

- Q: Should the KB live in `knowledge-base.md` (PR-gated), move entirely to Supabase, or use dual storage? → A: Supabase as sole SSoT — no `.md` snapshot, file retired entirely. Pipeline migration included in this feature scope.
- Q: Does this feature include migrating the existing pipeline's KB lookup from `knowledge-base.md` to Supabase, or is that a follow-up? → A: In scope — full migration, `knowledge-base.md` retired. New user story added for pipeline migration (P2). Frontend tag cloud added for still-unresolved terms (P3).

### Session 2026-05-11 (post-plan)

- Q: Should existing ~60 terms in `knowledge-base.md` be migrated to Supabase, or should the KB start empty and be rebuilt by the auto-KB job? → A: Migrate existing terms via a one-time script (FR-009) — no terms lost, no degraded transition week. `knowledge-base.md` deleted only after migration row count is verified.
