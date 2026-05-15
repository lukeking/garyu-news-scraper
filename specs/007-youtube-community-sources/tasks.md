# Tasks: YouTube Community Sources

**Input**: Design documents from `specs/007-youtube-community-sources/`
**Prerequisites**: plan.md ✓, spec.md ✓, data-model.md ✓, contracts/ ✓, research.md ✓

**Organization**: Tasks grouped by user story. No tests requested in spec — implementation only.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no shared dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Install dependencies and wire up secrets before any code is written.

- [x] T001 Add `google-api-python-client` and `youtube-transcript-api` to `requirements.txt`
- [x] T00X [P] Add `YOUTUBE_API_KEY=` placeholder line to `.env.example`
- [x] T00X [P] Add `YOUTUBE_API_KEY: ${{ secrets.YOUTUBE_API_KEY }}` to the run-pipeline step env block in `.github/workflows/traffic_daily.yml` (alongside the existing `GEMINI_API_KEY` line)
- [x] T00X [P] Add `type: youtube` example block to `config/sources_traffic.example.yml` per the contract in `specs/007-youtube-community-sources/contracts/sources-youtube.md`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared helpers in `src/collector.py` that the YouTube fetcher depends on. Must complete before Phase 3.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T00X Add `_parse_iso8601_duration(duration: str) -> int` helper in `src/collector.py` — parses ISO 8601 duration strings (e.g., `"PT1M30S"`) and returns total seconds as an integer
- [x] T00X Add `_build_youtube_client()` helper in `src/collector.py` — reads `YOUTUBE_API_KEY` from `os.environ`; returns a `googleapiclient` discovery resource for the YouTube v3 API; logs an error and returns `None` if the key is absent

**Checkpoint**: Helpers ready — user story implementation can begin.

---

## Phase 3: User Story 1 — Configure YouTube Channel as Source (Priority: P1) 🎯 MVP

**Goal**: A `type: youtube` entry in `sources_traffic.yml` causes the daily pipeline to fetch recent uploads from that channel and produce article dicts in the same shape as RSS sources.

**Independent Test**: Add one channel ID to `sources_traffic.yml`, run `python -m src.pipeline.traffic` locally, verify at least one article dict with `source_type="youtube"` appears in the collected output log.

- [x] T00X [US1] Implement `_fetch_youtube(source: dict) -> list` skeleton in `src/collector.py` — call `_build_youtube_client()`; derive uploads playlist ID (`"UU" + channel_id[2:]`); call `playlistItems.list(playlistId=..., part="snippet", maxResults=max_items)` and filter items to those published within `lookback_days`; collect `resourceId.videoId` values
- [x] T00X [P] [US1] Add `videos.list` call in `_fetch_youtube()` in `src/collector.py` — fetch `contentDetails` (duration) and `snippet` (title, description, publishedAt) for each collected video ID; filter out videos where `_parse_iso8601_duration(duration) <= 60` (Shorts)
- [x] T00X [US1] Add quota exhaustion error handling in `_fetch_youtube()` in `src/collector.py` — catch `googleapiclient.errors.HttpError` with status 403 or 429; log a warning and return `[]` for this source without raising; all other sources continue unaffected
- [x] T0XX [US1] Register `"youtube": _fetch_youtube` in the `FETCHERS` dict in `src/collector.py`

**Checkpoint**: `collect_sources()` now dispatches YouTube entries. US1 independently testable.

---

## Phase 4: User Story 2 — Transcript Extraction with Graceful Fallback (Priority: P2)

**Goal**: Each fetched video attempts zh-TW/zh/en/ja transcript extraction; on any failure, the pipeline falls back to title + description. A video-specific Gemini prompt extracts the analytical argument rather than summarizing a news event.

**Independent Test**: (a) Point a source at a channel with auto-captions — verify `summary` field contains transcript text. (b) Disable `youtube-transcript-api` or use a captionless video — verify `summary` falls back to title + description and no exception is raised. (c) Verify `analyze_article()` uses the YouTube prompt when `source_type == "youtube"`.

- [x] T0XX [US2] Add transcript extraction inside `_fetch_youtube()` in `src/collector.py` — for each non-Short video, call `YouTubeTranscriptApi.get_transcript(video_id, languages=['zh-TW', 'zh', 'en', 'ja'])`; join transcript segments into one string; truncate to 4000 characters; set this as the `summary` field and set `source_type="youtube"` on the article dict
- [x] T0XX [P] [US2] Add fallback in `_fetch_youtube()` in `src/collector.py` — wrap the transcript call in a bare `except Exception`; on failure log a warning (`[youtube] 逐字稿取得失敗，使用標題+描述：{title}`) and set `summary = title + "\n" + description[:500]`; ensure `source_type="youtube"` is still set
- [x] T0XX [P] [US2] Add `YOUTUBE_SYSTEM_PROMPT` constant in `src/analyzer.py` — same structure as `SYSTEM_PROMPT` but identifies Gemini as a video commentary analyst, not a news analyst; same language/tone requirements
- [x] T0XX [P] [US2] Add `YOUTUBE_ANALYSIS_PROMPT_TEMPLATE` constant in `src/analyzer.py` — same output fields as `ANALYSIS_PROMPT_TEMPLATE` (摘要/分析/重要性/重要性原因/標籤/地區) but input framing reads `"以下是一段 YouTube 影片評論或分析的逐字稿（或說明）："` and the 分析 instruction asks Gemini to identify the core comparative or analytical argument, not just summarize an event
- [x] T0XX [US2] Add `elif article.get("source_type") == "youtube":` dispatch branch in `analyze_article()` in `src/analyzer.py` — place it before the existing traffic branch; call `_call_gemini()` with `YOUTUBE_ANALYSIS_PROMPT_TEMPLATE` and `YOUTUBE_SYSTEM_PROMPT`

**Checkpoint**: Transcripts extracted, fallback works, video-specific prompt active. US2 independently testable.

---

## Phase 5: User Story 3 — Keyword Filtering for YouTube Articles (Priority: P3)

**Goal**: YouTube articles (transcript or fallback body) pass through the existing `MOTORCYCLE_KEYWORDS` filter before entering dedup. Off-topic videos are dropped.

**Independent Test**: Configure a YouTube channel that posts mixed content; run the pipeline; verify only articles whose `summary` contains at least one `MOTORCYCLE_KEYWORDS` term appear in the output.

- [x] T0XX [US3] Trace the keyword filtering path for a YouTube article dict through `src/filter.py` — confirm `MOTORCYCLE_KEYWORDS` is applied to the `summary` field (which holds the transcript or fallback body); if the filter checks a different field or skips `source_type="youtube"` entries, fix the logic; add a targeted debug log line: `[youtube] 關鍵字篩選：通過 / 已過濾：{title}`

**Checkpoint**: Keyword filter correctly applied to YouTube article bodies. All three user stories independently testable.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T0XX [P] Write `specs/007-youtube-community-sources/quickstart.md` with local testing steps: how to find a channel ID, set `YOUTUBE_API_KEY` in `.env`, add a `type: youtube` entry to `config/sources_traffic.yml`, and run the traffic pipeline locally to verify output
- [x] T0XX [P] Update `config/sources_traffic.example.yml` with descriptive comments under the `type: youtube` block explaining the three categories of useful channels (TW traffic commentary, foreign traffic comparison, road safety/advocacy) and how to find channel IDs

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T002/T003/T004 can run in parallel
- **Phase 2 (Foundational)**: Requires Phase 1 complete — **blocks Phases 3–5**
- **Phase 3 (US1)**: Requires Phase 2 — T008 can run in parallel with T007 once T005/T006 done; T009/T010 depend on T007
- **Phase 4 (US2)**: Requires Phase 2 — T013/T014 are fully parallel; T011/T012 depend on T007 (US1); T015 depends on T013/T014
- **Phase 5 (US3)**: Requires Phase 2 — independent of US1/US2 (filter is a separate module)
- **Phase 6 (Polish)**: Requires all story phases complete; T017/T018 fully parallel

### User Story Dependencies

- **US1**: No dependency on US2 or US3 — independently testable after Phase 2
- **US2**: Depends on US1's `_fetch_youtube()` skeleton (T007) for the transcript and fallback tasks (T011, T012); prompt constants (T013, T014) are independent
- **US3**: Independent — `src/filter.py` is a separate module

---

## Parallel Opportunities

### Phase 1 (all parallel after T001)
```
T001 → T002, T003, T004 (all parallel)
```

### Phase 3 (US1)
```
T007 (playlist fetch skeleton)
  ↓
T008 [P] (videos.list + Shorts filter) ← can start immediately after T007
T009 (error handling) ← can start immediately after T007
  ↓
T010 (register in FETCHERS)
```

### Phase 4 (US2)
```
T013 [P] YOUTUBE_SYSTEM_PROMPT      ← fully independent, start any time
T014 [P] YOUTUBE_ANALYSIS_PROMPT    ← fully independent, start any time
T011 (transcript extraction)        ← depends on T007 from US1
  ↓
T012 [P] (fallback)                 ← can run in parallel with T011 once skeleton exists
T015 (dispatch in analyze_article)  ← depends on T013, T014
```

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Phase 1: Setup (T001–T004)
2. Phase 2: Foundational (T005–T006)
3. Phase 3: US1 (T007–T010)
4. **STOP AND VALIDATE**: Add a test channel to `sources_traffic.yml`, run pipeline, confirm articles appear in Supabase with correct schema
5. Ship if working — US2 and US3 add quality, not correctness

### Incremental Delivery

1. Setup + Foundational → run passes without errors (no YouTube channels configured yet)
2. US1 → articles fetched and stored (summaries are raw transcript/description, not Gemini-analysed yet if US2 not done)
3. US2 → Gemini video prompt active, transcripts extracted
4. US3 → keyword filter confirmed; off-topic videos dropped
5. Polish → docs complete, quickstart validated
