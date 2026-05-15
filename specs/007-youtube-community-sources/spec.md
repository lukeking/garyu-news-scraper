# Feature Specification: YouTube Community Sources

**Feature Branch**: `008-youtube-community-sources`
**Created**: 2026-05-15
**Status**: Draft
**Input**: Research at `specs/007-youtube-community-sources/research.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure YouTube Channel as Source (Priority: P1)

A pipeline operator adds a YouTube channel to the traffic source configuration. On the
next daily run, the pipeline fetches recent uploads from that channel, extracts
transcripts, and feeds them through the existing filter, dedup, and summarization steps.

**Why this priority**: This is the core capability — without it, no YouTube content
enters the pipeline at all. Everything else builds on this.

**Independent Test**: Add one channel ID to `sources_traffic.yml`, trigger a manual
pipeline run, and verify that at least one article from that channel appears in the
Supabase articles table with a non-empty summary.

**Acceptance Scenarios**:

1. **Given** a `type: youtube` entry with a valid `channel_id` in `sources_traffic.yml`,
   **When** the daily traffic pipeline runs,
   **Then** recent uploads (up to `max_items`) from that channel are fetched and
   processed through filter → dedup → summarization.

2. **Given** a channel with no uploads in the past 7 days,
   **When** the pipeline runs,
   **Then** zero articles are added from that channel and a log entry notes the result.

3. **Given** a channel ID that no longer exists or is private,
   **When** the pipeline runs,
   **Then** the source is skipped with a warning log; the rest of the pipeline continues
   unaffected.

---

### User Story 2 - Transcript Extraction with Graceful Fallback (Priority: P2)

For each YouTube video fetched, the pipeline attempts to extract the spoken transcript
(auto-generated or manual captions in zh-TW/zh). If transcript extraction fails — due
to cloud IP blocking or caption unavailability — the pipeline falls back to using the
video title and description as the article body.

**Why this priority**: Transcripts are the key quality differentiator over RSS. The
fallback ensures the pipeline never hard-fails on a video, while still surfacing richer
content when transcripts are available.

**Independent Test**: Point a source at a channel known to have auto-captions; verify
the resulting article body contains transcript text. Then simulate a transcript failure
(disable the library or use a captionless video) and verify the article body falls back
to title + description.

**Acceptance Scenarios**:

1. **Given** a video with available zh-TW or zh auto-captions,
   **When** the pipeline processes it,
   **Then** the article body contains the extracted transcript text.

2. **Given** a video with no available captions,
   **When** the pipeline processes it,
   **Then** the article body is composed of the video title and description, and a
   debug log notes the fallback.

3. **Given** transcript extraction fails due to a network or IP block error,
   **When** the pipeline processes it,
   **Then** the fallback to title + description is used, no exception is raised,
   and a warning is logged.

---

### User Story 3 - Keyword Filtering for YouTube Articles (Priority: P3)

YouTube articles pass through the same `MOTORCYCLE_KEYWORDS` filter as RSS articles.
For transcript-backed articles, the filter is applied to the full transcript body. For
fallback (title + description) articles, it is applied to the combined title and
description text.

**Why this priority**: Without filtering, channels that occasionally post off-topic
content would pollute the pipeline. Filtering reuses existing logic — no new concepts,
just correct integration.

**Independent Test**: Add a channel that posts mixed content (some motorcycle-related,
some not). Verify that after a pipeline run, only articles matching `MOTORCYCLE_KEYWORDS`
appear in the output.

**Acceptance Scenarios**:

1. **Given** a YouTube video whose transcript contains motorcycle-related keywords,
   **When** the pipeline filters it,
   **Then** the article passes through to dedup and summarization.

2. **Given** a YouTube video whose transcript contains no motorcycle-related keywords,
   **When** the pipeline filters it,
   **Then** the article is dropped and a debug log notes the reason.

---

### Edge Cases

- What happens when the YouTube Data API daily quota (10,000 units) is exhausted?
  Pipeline should log a quota error and skip remaining YouTube sources for that run
  without failing the overall job.
- What happens when a video is longer than 60 minutes and the transcript is very large?
  Transcript should be truncated to a configurable character limit before summarization.
- What happens when the same video appears in multiple runs (e.g., re-indexed or
  re-uploaded)? The existing embedding dedup and link-based upsert in Supabase handle
  this — no special handling needed.
- What happens when `max_items` is not set? Default to 5 videos per channel per run.
- What happens when a video is a YouTube Short (duration ≤ 60 seconds)? It is excluded
  at fetch time by duration filter — Shorts have no analytical depth and typically
  lack transcripts.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST support a new source type `youtube` in `sources_traffic.yml`,
  accepting at minimum `channel_id` and optional `max_items` (default: 5).
- **FR-002**: For each configured YouTube channel, the pipeline MUST poll the channel's
  upload playlist and retrieve the `max_items` most recent videos published since the
  last run (or within a configurable lookback window).
- **FR-003**: The pipeline MUST attempt to extract a transcript for each video, preferring
  zh-TW captions, then zh, then any available language. Non-Chinese transcripts (Japanese,
  English, etc.) are accepted as-is and passed to the summarization step without translation.
- **FR-004**: When transcript extraction fails for any reason, the pipeline MUST fall back
  to using the video title and description as the article body, without raising an exception.
- **FR-005**: YouTube articles MUST pass through the existing `MOTORCYCLE_KEYWORDS` keyword
  filter before entering dedup and summarization.
- **FR-006**: YouTube articles MUST enter the existing embedding dedup step alongside RSS
  and other source articles — no separate dedup pass.
- **FR-007**: YouTube articles stored in Supabase MUST include `source` set to the channel
  name (from config), `link` set to the video URL, and `content_type` matching the pipeline
  type (e.g., `traffic`).
- **FR-008**: When the YouTube Data API quota is exhausted, the pipeline MUST log an error
  and skip remaining YouTube sources for that run without terminating the overall job.
- **FR-009**: Transcripts exceeding a configurable character limit MUST be truncated before
  being passed to the summarization step.
- **FR-010**: Videos with a duration of 60 seconds or less (YouTube Shorts) MUST be
  excluded at fetch time and never enter the filter or summarization steps.
- **FR-011**: The summarization step for YouTube articles MUST use a video-specific
  prompt that instructs the model to extract the analytical or comparative argument
  of the video, rather than the news-article prompt used for RSS sources.

### Key Entities

- **YouTubeSource**: A pipeline source configured with `channel_id`, `name`, `max_items`,
  and optional `lookback_days`. Produces article dicts in the same shape as RSS sources.
- **VideoArticle**: An article dict derived from a YouTube video — fields: `title`,
  `link` (video URL), `published`, `summary` (Gemini-generated), `source` (channel name),
  `embedding`, `content_type`.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least one YouTube channel can be configured and produces articles in a
  pipeline run with no code changes beyond adding a `type: youtube` entry to the source
  config.
- **SC-002**: Articles sourced from YouTube are indistinguishable from RSS articles in
  the Supabase output — same schema, same downstream hot-topic analysis.
- **SC-003**: When transcript extraction fails (tested by using a captionless video),
  the pipeline completes successfully with a fallback article rather than an exception.
- **SC-004**: YouTube articles that share the same event as an RSS article are correctly
  identified as duplicates by the embedding dedup step (similarity ≥ threshold) at least
  50% of the time in a real run.
- **SC-005**: A pipeline run with 3 YouTube channels configured consumes fewer than 50
  YouTube Data API quota units.

---

## Clarifications

### Session 2026-05-15

- Q: Should YouTube Shorts (videos ≤ 60s) be included or excluded? → A: Exclude at fetch time by duration filter (A)
- Q: Should the Gemini summarization prompt be adapted for video content? → A: Yes — a video-specific prompt that emphasizes extracting the analytical/comparative argument (B)
- Q: Should the lookback window be fixed or dynamic on pipeline failure? → A: Fixed 2-day window always (A)
- Q: Should non-Chinese transcripts (Japanese, English) be accepted for foreign-comparison channels? → A: Accept any language — pass transcript to Gemini as-is (A)

---

## Assumptions

- YouTube Data API v3 credentials (API key) are stored as a GitHub Actions secret and
  loaded via the existing `.env` / environment variable pattern.
- `youtube-transcript-api` is used for transcript extraction; if it is blocked by
  GitHub Actions IPs, the fallback (title + description) is acceptable for v1. A
  migration to the official captions endpoint can be done in a follow-up.
- The initial seed of channel IDs is provided by the operator in `sources_traffic.yml`
  (stored as a GitHub Actions environment variable); no automatic channel discovery is
  in scope.
- Transcript truncation limit defaults to 4,000 characters (~600 tokens), keeping
  summarization cost predictable.
- `type: youtube` entries live in the same `sources_traffic.yml` as RSS and other
  sources — no separate config file needed.
- The lookback window for "recent uploads" defaults to 2 days to match the daily
  pipeline cadence with a one-day safety overlap.
