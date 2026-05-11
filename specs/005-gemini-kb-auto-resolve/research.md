# Research: Gemini-Powered Self-Evolving Knowledge Base

**Branch**: `005-gemini-kb-auto-resolve` | **Date**: 2026-05-11

---

## Decision 1: Supabase `knowledge_base` table vs. other KB storage options

**Decision**: Supabase `knowledge_base` table as sole SSoT; `knowledge-base.md` retired.

**Rationale**: Supabase is already in the project stack (articles table, service role key in GitHub Secrets). Moving the KB to a second table in the same database adds zero new infrastructure. The pipeline already has read/write access to Supabase at runtime, so no new credentials are needed. A Supabase table also eliminates the context-window scalability concern: `load_knowledge_base()` fetches only the rows it needs rather than passing a growing file to every Gemini analysis call.

**Alternatives considered**:
- Keep `knowledge-base.md` + snapshot to Supabase: rejected by user as "meaningless" — creates a stale artifact with no consumers.
- External vector database for semantic KB lookup: over-engineered for the current scale (~100–500 terms); Supabase exact-match lookup is sufficient.

---

## Decision 2: `workflow_run` trigger for auto-KB job

**Decision**: `.github/workflows/auto-kb.yml` uses `on.workflow_run` triggered by `Garyu News Scraper 週報` with `types: [completed]` and an `if: github.event.workflow_run.conclusion == 'success'` guard on the job.

**Rationale**: `workflow_run` fires immediately when the named workflow completes, with access to the conclusion status. This avoids a fixed-offset cron (race condition if pipeline overruns) and avoids polling. The `conclusion == 'success'` guard ensures the auto-KB job only runs when new KB miss data is actually available in Supabase.

**Alternatives considered**:
- Fixed cron 30 min after pipeline start: rejected — race condition if pipeline is slow; also fires even if pipeline failed.
- `repository_dispatch` event from within the weekly workflow: rejected — requires adding a step to the existing pipeline and a PAT with `repo` scope.

---

## Decision 3: Gemini call design for auto-KB job

**Decision**: Single batch call per run. All unknown terms are sent in one prompt as a newline-separated list. Gemini returns a JSON array of resolved entries. Terms Gemini omits are treated as `[KB AUTO-MISS]`.

**Rationale**: The existing pipeline calls Gemini once per article (sequential, rate-limited). The auto-KB job has a different profile: typically ≤ 20 unknown terms, called once per week. A single batch call is faster, cheaper, and avoids per-term retry complexity. JSON response format is explicit in the prompt, making parsing straightforward and testable.

**Gemini prompt contract** (see `contracts/auto-kb-job.md` for full text):
- System role: FFXIV TW term specialist
- Instruction: return only high-confidence TW translations (official TW patch notes > TW wiki > community usage); omit uncertain terms
- Response: strict JSON array; empty array `[]` if nothing confident
- Temperature: 0.1 (lower than analysis calls — precision over creativity)

**Alternatives considered**:
- One Gemini call per unknown term: rejected — up to 20 API calls when one batch call suffices; burns rate limit budget unnecessarily.
- Gemini Search Grounding (`google_search` tool): would improve accuracy for brand-new patch terms but costs additional quota and adds API complexity. Deferred — can be added later as an enhancement to `auto_kb.py` without changing any contracts.

---

## Decision 4: `load_knowledge_base()` migration strategy

**Decision**: Modify `load_knowledge_base()` in `src/analyzer.py` in-place. Replace file-read logic with a Supabase SELECT. Keep the `_KB_CACHE` module-level dict and the existing return type `{jp_term: {"tw": str, "en": str, "category": str}}` unchanged. Create a Supabase client inline (same pattern as `scripts/resolve_kb_misses.py`'s `_get_client()`).

**Rationale**: The function's callers (`analyze_article()`) are unaffected — same dict structure, same in-memory caching. No new module boundary is introduced. The function already raises `RuntimeError` on failure; this behavior is preserved (fail on empty KB, per FR-010).

**Alternatives considered**:
- New `src/knowledge_base.py` helper module: rejected — constitution Principle V requires justification for new cross-module dependencies; the change is small enough to keep in `analyzer.py`.
- Import from `src/storage.py`: rejected — `storage.py` owns the `articles` table write path; mixing KB read logic there violates single responsibility.

---

## Decision 5: Inline re-resolution in auto-KB job

**Decision**: After writing new KB entries to Supabase, `auto_kb.py` immediately runs re-resolution on all FFXIV `articles` rows that still contain `[[term]]` markers matching newly added terms. This replicates the logic of the retired `scripts/resolve_kb_misses.py`, but scoped to the newly added terms only (not a full re-scan).

**Rationale**: Re-resolution must happen immediately after KB write to close the loop within the same job run. Running a full re-scan (all articles, all KB terms) is also acceptable given the small dataset scale, but scoping to new terms is more efficient.

**`resolve-kb-misses.yml` retirement**: This workflow was triggered by `knowledge-base.md` pushes. With the file retired, the trigger can never fire. The workflow file is deleted as part of this feature.

---

## Decision 6: Frontend tag cloud implementation

**Decision**: `renderTermPool()` added to `pages/shared/app.js`, gated by `C.contentType === 'ffxiv'`. Extracts `[[term]]` patterns from `JSON.stringify(a.analysis)` for each displayed article. Tags rendered as `position: absolute` spans inside a `position: relative` container, with `left`/`top` set to seeded-random percentages computed at render time. Each re-render (week switch, filter change) generates new random positions.

**Term pool div placement**: Between `<div id="week-nav">` and `<div class="tag-bar">` in `pages/ffxiv/index.html`, matching the layout picked in the spec (Option C: scattered cloud, between week-nav and tag-bar).

**Tag sizing**: Random size between 0.85rem and 1.55rem. Frequency-weighted sizing is deferred (noted in spec Assumptions as a future enhancement).

**Alternatives considered**:
- Server-side aggregation of unknown terms via new Worker API endpoint: rejected — frontend already receives full `analysis` JSONB per article; client-side extraction adds no network cost and avoids a new API surface.
- Pure CSS `flex-wrap` layout (Option B from spec): rejected by user in favor of scattered/scattered option (Option C).

---

## Decision 7: Constitution amendment scope

**Decision**: MINOR bump 1.1.0 → 1.2.0. Changes:
1. Principle VI: replace `knowledge-base.md` references with `knowledge_base` Supabase table; replace "updated via PRs" with "auto-expanded weekly via the auto-KB job; manual additions via Supabase dashboard"
2. Technology Constraints: "Knowledge Base: Markdown file" → "Knowledge Base: Supabase `knowledge_base` table"
3. Operations: replace "Knowledge base updates MUST go through a PR" with "Auto-generated KB entries are written directly to the `knowledge_base` table; manual entries may be added via Supabase dashboard; `auto_generated` flag distinguishes origin"
4. Remove references to `knowledge-base-template.md` (file retired)

**Rationale**: The amendment is MINOR (existing principle updated, not removed). No principles are weakened — quality control moves from PR review to a Gemini confidence gate + `auto_generated` audit flag. This is a transparent and documented tradeoff.
