# Integration Test Scenarios: Gemini-Powered Self-Evolving Knowledge Base

**Branch**: `005-gemini-kb-auto-resolve` | **Date**: 2026-05-11

---

## Prerequisites

1. Supabase `knowledge_base` table created and migration script run successfully
2. `knowledge-base.md` retired (deleted from repo)
3. All environment variables set: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL_NAME`

---

## Scenario 1 — Pipeline reads KB from Supabase (P2 core)

**Goal**: Confirm the weekly pipeline no longer reads `knowledge-base.md` and uses Supabase KB instead.

**Steps**:
1. Confirm `knowledge-base.md` does not exist in the repo root.
2. Add a test term row directly to the Supabase `knowledge_base` table via dashboard: e.g., `jp_term = "テスト用語"`, `tw_term = "測試術語"`, `en_term = "Test Term"`, `category = "遊戲"`.
3. Trigger the weekly pipeline via `workflow_dispatch`.
4. In the pipeline log, verify: `"知識庫載入完成：N 個術語"` where N ≥ 1.
5. Verify no `FileNotFoundError` or `RuntimeError` about `knowledge-base.md` in logs.

**Pass condition**: Pipeline completes successfully; log shows KB loaded from Supabase.

---

## Scenario 2 — Pipeline halts on empty KB (failure safety)

**Goal**: Confirm the pipeline halts (not silently continues) if the KB table is empty.

**Steps**:
1. Temporarily rename or truncate the `knowledge_base` table (or use a test environment with an empty table).
2. Trigger the weekly pipeline via `workflow_dispatch`.
3. Verify the run fails with a `RuntimeError` log message about empty KB.

**Pass condition**: Pipeline step fails visibly with an informative error; does not produce FFXIV analysis with empty translations.

---

## Scenario 3 — Auto-KB job resolves a known miss (P1 core)

**Goal**: Confirm `auto_kb.py` collects a `[[term]]` from Supabase, resolves it via Gemini, writes the row, and patches the article.

**Steps**:
1. Manually INSERT a test article row to Supabase `articles` with `content_type = 'ffxiv'` and `analysis = '{"summary": "[[曉月のフィナーレ]] テスト"}'`. (Use a term you know Gemini can resolve.)
2. Confirm the term is NOT in the `knowledge_base` table.
3. Run `python scripts/auto_kb.py` locally (with env vars set).
4. Verify in Supabase `knowledge_base`: a new row with `jp_term = "曉月のフィナーレ"` (or whichever term was inserted), `auto_generated = true`.
5. Verify in Supabase `articles`: the test article's `analysis` no longer contains `[[曉月のフィナーレ]]` — the marker was replaced with the TW term.
6. Verify the log contains no `[KB AUTO-MISS]` for this term.

**Pass condition**: KB row written; article patched; no AUTO-MISS warning for the resolved term.

---

## Scenario 4 — Auto-KB job handles unresolvable terms (KB AUTO-MISS path)

**Goal**: Confirm `auto_kb.py` does not write guesses and emits a proper warning.

**Steps**:
1. Insert a test article with `analysis = '{"summary": "[[AAAAテスト新造語BBBB]]"}'` — a term guaranteed to be unknown to Gemini.
2. Confirm the term is NOT in `knowledge_base`.
3. Run `python scripts/auto_kb.py` locally.
4. Verify `knowledge_base` does NOT contain a row for `AAAAテスト新造語BBBB`.
5. Verify the log contains `[KB AUTO-MISS]` with the term listed.
6. Verify the article's `analysis` still contains `[[AAAAテスト新造語BBBB]]` (not patched).

**Pass condition**: No KB row inserted; article unchanged; AUTO-MISS warning emitted.

---

## Scenario 5 — Auto-KB job skips when no misses (empty run)

**Goal**: Confirm the job exits cleanly with no errors when there are no `[[term]]` markers.

**Steps**:
1. Ensure all FFXIV articles in Supabase have no `[[term]]` markers (or use a test table with zero matching rows).
2. Run `python scripts/auto_kb.py` locally.
3. Verify log contains "no unknown terms to resolve" (or equivalent) and no errors.
4. Verify no new rows in `knowledge_base`.

**Pass condition**: Script exits 0; no insertions; no errors.

---

## Scenario 6 — Frontend tag cloud appears and disappears (P3)

**Goal**: Confirm the tag pool section is visible when misses exist and hidden when none exist.

**Steps (misses present)**:
1. Ensure at least one FFXIV article in Supabase has an `analysis` field containing `[[SomeTerm]]`.
2. Open the FFXIV news page in a browser.
3. Verify the `#unknown-term-pool` section is visible above the tag bar.
4. Verify `SomeTerm` appears as a floating tag inside the pool.

**Steps (no misses)**:
5. Remove all `[[term]]` markers from Supabase articles (or switch to a week with no misses).
6. Reload the page.
7. Verify `#unknown-term-pool` has `display: none` — no empty box visible.

**Pass condition**: Pool shows/hides correctly; tags are scattered (not in a row); tag content matches actual `[[term]]` values in article data.

---

## Scenario 7 — `workflow_run` trigger fires after weekly pipeline (P4)

**Goal**: Confirm `auto-kb.yml` triggers on successful weekly pipeline completion.

**Steps**:
1. Trigger `Garyu News Scraper 週報` via `workflow_dispatch`.
2. After it completes successfully, check GitHub Actions for a new `Auto KB Expansion` run.
3. Verify the run was triggered automatically (not manually).
4. Verify the run completes successfully (or exits 0 with no misses if KB is fully resolved).

**Pass condition**: `auto-kb.yml` run appears within ~60 seconds of the weekly pipeline finishing; conclusion is success.

---

## Scenario 8 — Migration idempotency

**Goal**: Confirm `migrate_kb.py` can be run multiple times without creating duplicate rows.

**Steps**:
1. Run `python scripts/migrate_kb.py` once.
2. Note the row count in `knowledge_base`.
3. Run `python scripts/migrate_kb.py` a second time.
4. Verify the row count in `knowledge_base` is identical to step 2.
5. Verify no errors in the second run.

**Pass condition**: Same row count both runs; no errors.
