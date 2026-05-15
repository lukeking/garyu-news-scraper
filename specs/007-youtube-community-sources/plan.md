# Implementation Plan: YouTube Community Sources

**Branch**: `007-youtube-community-sources` | **Date**: 2026-05-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/007-youtube-community-sources/spec.md`

## Summary

Add `type: youtube` as a new source type to the traffic news pipeline. The fetcher polls
configured YouTube channels via the Data API v3 `playlistItems` endpoint, extracts video
transcripts via `youtube-transcript-api` (with a graceful fallback to title + description),
filters Shorts (≤ 60s), applies the existing keyword filter, then feeds articles into the
existing embedding dedup and a new video-specific Gemini summarization prompt. No new pipeline
stages — this is a pure extension of the existing `FETCHERS` dispatch table in `src/collector.py`
and a new prompt variant in `src/analyzer.py`.

## Technical Context

**Language/Version**: Python 3.x (matches existing runtime)
**Primary Dependencies**: `google-api-python-client` (YouTube Data API v3), `youtube-transcript-api` (PyPI transcript scraping)
**Storage**: Supabase — existing `articles` table; no schema changes needed
**Testing**: Manual trigger via GitHub Actions; local `.env` run with a known channel ID
**Target Platform**: GitHub Actions (Linux runner, Ubuntu)
**Performance Goals**: Full run with 3 YouTube channels must complete within the existing 10-minute workflow budget; YouTube API calls must stay under 50 units per run
**Constraints**: Transcript extraction may fail on GitHub Actions IPs (cloud block); fallback to title + description is acceptable for v1; no OAuth required
**Scale/Scope**: Expected 3–10 configured channels initially, 5 videos each = 15–50 videos fetched per run before keyword filtering

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| I. Pipeline Integrity | ✓ Pass | YouTube articles flow through collect → filter → analyze → store unchanged |
| II. Configuration over Code | ✓ Pass | Channel IDs in `sources_traffic.yml` (env var); API key in GitHub Secrets |
| III. Idempotency | ✓ Pass | Video URL as `link`; existing upsert-on-conflict handles re-runs |
| IV. Free Tier | ✓ Pass | `playlistItems` = 1 unit/call; 10 channels × 1 call + 50 `videos.list` calls = 60 units (well within 10k/day) |
| V. Single Responsibility | ✓ Pass | Fetcher in `src/collector.py`; prompt in `src/analyzer.py`; no new modules |
| VI. KB Integrity | N/A | Traffic content only; FFXIV KB not involved |

**No violations. Proceed.**

## Project Structure

### Documentation (this feature)

```text
specs/007-youtube-community-sources/
├── plan.md              ← this file
├── research.md          ← research findings (pre-existing)
├── spec.md              ← feature specification
├── data-model.md        ← Phase 1 output
├── contracts/
│   └── sources-youtube.md   ← YAML config schema for type: youtube
└── tasks.md             ← Phase 2 output (/speckit-tasks)
```

### Source Code Changes

```text
src/
├── collector.py         ← add _fetch_youtube(); register in FETCHERS
└── analyzer.py          ← add YOUTUBE_SYSTEM_PROMPT + YOUTUBE_ANALYSIS_PROMPT_TEMPLATE;
                            update analyze_article() dispatch

config/
└── sources_traffic.example.yml   ← add type: youtube example entries

requirements.txt         ← add google-api-python-client, youtube-transcript-api
```

**No new modules.** Both changes are additive within existing files, consistent with
Principle V (no new cross-module dependencies introduced).

## Phase 0: Research

### Findings

All key decisions were resolved during the research phase (see `research.md`) and clarification
session. Recorded here for plan completeness.

---

**Decision: YouTube Data API v3 via `playlistItems` endpoint (not `search`)**
- Rationale: `playlistItems` costs 1 quota unit per call vs. 100 for `search`. Each channel
  has an uploads playlist ID derivable from the channel ID (`UU` + channel_id[2:]). This
  approach scales to 100 channels/day on the free tier.
- Alternative considered: `search` endpoint — rejected due to 100× higher quota cost.

---

**Decision: `youtube-transcript-api` for transcript extraction, with fallback**
- Rationale: No credentials required; supports zh-TW/zh auto-captions; actively maintained.
  Cloud IP blocking risk on GitHub Actions is accepted for v1 — the fallback to title +
  description is already the standard RSS article body length and Gemini handles it fine.
- Alternative considered: Official `captions.download` API — requires OAuth (user-scoped),
  too complex for this use case.

---

**Decision: Shorts excluded by duration filter (≤ 60s) at fetch time**
- Rationale: Shorts rarely have transcripts and contain no analytical depth. Duration is
  returned by `videos.list` in ISO 8601 format (e.g., `PT58S`); parsing is trivial.
- Implementation: Parse `contentDetails.duration` for each video; skip if total seconds ≤ 60.

---

**Decision: Fixed 2-day lookback window**
- Rationale: Simple; the existing daily cadence already has a 1-day safety overlap built in.
  Dynamic lookback adds state management complexity not justified by occasional missed runs.

---

**Decision: Video-specific Gemini prompt (not shared with news articles)**
- Rationale: Video transcripts are conversational and build a comparative argument over time.
  A news prompt would produce shallow event summaries that miss the analytical value.
  The new prompt instructs Gemini to extract the core argument and comparative insight.
- Output format: Same structured fields (摘要/分析/重要性/標籤/地區) for downstream
  compatibility — only the framing instruction changes.

---

**Decision: Non-Chinese transcripts accepted as-is (any language → Gemini)**
- Rationale: Channels comparing Taiwan traffic to Japan/EU/US may publish in Japanese or
  English. Gemini handles multilingual input and produces consistent Traditional Chinese output
  without an explicit translation step.

---

**Decision: `source_type: "youtube"` field for analyzer dispatch**
- Rationale: `content_type` is reserved for `traffic` vs `ffxiv` pipeline routing (storage,
  dedup). A separate `source_type` field on the article dict signals to `analyze_article()`
  to use the video prompt without affecting storage schema.
- This field is not persisted to Supabase (the `analysis` JSON column stores the output,
  not the input metadata).

## Phase 1: Design & Contracts

### Data Model → `data-model.md`

See [data-model.md](data-model.md).

### Interface Contracts → `contracts/sources-youtube.md`

See [contracts/sources-youtube.md](contracts/sources-youtube.md).

### Implementation Notes (for task generation)

**`src/collector.py` — `_fetch_youtube(source: dict) -> list`**

```
1. Build uploads playlist ID: "UU" + channel_id[2:]
2. Call playlistItems.list(playlistId, part="snippet", maxResults=max_items)
   - Filter by publishedAt >= now - lookback_days
3. Collect video IDs from snippet.resourceId.videoId
4. Call videos.list(id=<comma-joined>, part="contentDetails,snippet")
   - Skip videos where duration ≤ 60s (parse ISO 8601 PT#M#S)
5. For each remaining video:
   a. Attempt transcript via youtube-transcript-api(['zh-TW','zh','en','ja'])
   b. On any exception: fallback body = title + "\n" + description[:500]
   c. Truncate transcript to 4000 chars
   d. Build article dict with source_type="youtube"
6. Return list of article dicts
```

On `googleapiclient.errors.HttpError` with status 403/429 (quota exceeded):
- Log error, return empty list for this source, do not raise.

**`src/analyzer.py` — new prompt constants**

```
YOUTUBE_SYSTEM_PROMPT: instructs Gemini it is analyzing a video commentary/analysis,
  not a news article. Same language/tone as SYSTEM_PROMPT.

YOUTUBE_ANALYSIS_PROMPT_TEMPLATE: same output fields as ANALYSIS_PROMPT_TEMPLATE
  (摘要/分析/重要性/重要性原因/標籤/地區) but the input framing says:
  "以下是一段 YouTube 影片評論/分析的逐字稿或說明" and the 分析 instruction
  asks Gemini to identify the core comparative or analytical argument, not just
  summarize a news event.
```

`analyze_article()` dispatch: add `elif article.get("source_type") == "youtube":` branch
before the existing traffic branch, using `YOUTUBE_ANALYSIS_PROMPT_TEMPLATE` +
`YOUTUBE_SYSTEM_PROMPT`.

**`requirements.txt` additions**
- `google-api-python-client`
- `youtube-transcript-api`

**`config/sources_traffic.example.yml` additions**
- New `type: youtube` example block with `channel_id`, `max_items`, `lookback_days`

**GitHub Secrets / Environment Variables**
- New secret: `YOUTUBE_API_KEY` — read in `_fetch_youtube()` from `os.environ`
- No change to `SOURCES_TRAFFIC_YML` loading logic — new entries just add `type: youtube`
  blocks inline

## Complexity Tracking

No constitution violations. No complexity justification needed.
