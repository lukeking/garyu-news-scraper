# Feature Specification: Modular News Processing Engine

**Feature Branch**: `006-traffic-news-pipeline`
**Created**: 2026-05-12
**Status**: Draft
**Input**: User description: "Modular News Processing Engine with Traffic Curation and Game Aggregation pipelines"

## Overview

Two separate processing pipelines — one for traffic news, one for game news — share a common preprocessing and deduplication core but apply different analysis strategies and scheduling. The FFXIV game pipeline fires inline on each crawl, executing the full collect→filter→analyze→publish flow in one operation. The traffic pipeline runs in two separate scheduled phases: a daily collect→filter→store phase (nothing published) and a weekly Monday phase that categorizes buffered articles, selects the top hot topics, performs deep analysis on each, and publishes only those hot-topic reports. Articles not ranked as hot topics are retained in the buffer for retrospective analysis the following week. The design goal is vertical, deep analysis of significant issues rather than high-volume low-value news output.

## Clarifications

### Session 2026-05-12

- Q: After the crawler collects new articles, how does the processing pipeline receive them? → A: FFXIV pipeline triggers inline on each crawl completion (single collect→filter→analyze→publish flow); Traffic pipeline uses two separate scheduled phases — daily (collect→filter→store only, nothing published) and weekly (Monday: categorize all buffered articles, select top hot topics, deep-analyze each, publish hot-topic reports only). Non-hot articles are retained in the weekly buffer for retrospective categorisation the following week.
- Q: How many hot topics are selected per week? → A: Variable 1–3, selected by a composite topic score (article count + source diversity across outlets + temporal spread across days of the week). Only topic buckets that pass a configurable minimum score threshold qualify for deep analysis; at most 3 per week.
- Q: What happens to articles with Jaccard similarity 0.40–0.45 (gap between cluster and merge ranges)? → A: Extend the topic clustering range to cover 0.20–0.45; the gap was a typo. Deduplication threshold stays at > 0.45. All similarity thresholds are configurable for post-launch tuning.
- Q: How long should non-hot articles remain in the weekly buffer, and how is the hot-topic threshold calculated? → A: No fixed weekly TTL. At ingestion, each article receives a major category label and an initial quality score. Category scores accumulate across weeks — a topic that recurs at sub-threshold levels in consecutive weeks can cross the threshold via cumulative momentum. A hard maximum buffer age (configurable, default 8 weeks) prevents ancient articles from distorting scores. Whether older articles decay in score contribution is deferred to planning.
- Q: How should major category labels be assigned to incoming traffic articles? → A: Rule-based keyword matching against an externally configurable category taxonomy (zero ingestion cost). The taxonomy starts with a seed set and is designed to grow over time. Articles matching no known category are placed in an "uncategorised" bucket, which serves as the discovery surface for identifying new categories to add to the taxonomy.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Monday Traffic Insight (Priority: P1)

A reader visiting the site on Monday morning finds a curated "Weekly Traffic Insight" report summarising the most significant traffic theme from the past week, written from a community or comparative-standards angle.

**Why this priority**: This is the primary high-value deliverable of the traffic pipeline. All other traffic logic exists to support it.

**Independent Test**: Can be tested by triggering the Monday pipeline manually against a seeded database containing one week of traffic articles and verifying that a Weekly Insight entry is persisted and retrievable via the existing API.

**Acceptance Scenarios**:

1. **Given** at least 3 traffic articles exist from the past 7 days, **When** the weekly trigger fires at 08:00 AM on Monday (Taiwan Standard Time), **Then** exactly one Weekly Insight record is created for that week.
2. **Given** the weekly trigger fires, **When** the top topic bucket contains 5–10 articles, **Then** the insight is generated from titles and 200-character snippets of those articles only (not full body text).
3. **Given** fewer than 3 traffic articles exist for the week, **When** the trigger fires, **Then** no insight is generated and the failure is logged; no AI call is made.

---

### User Story 2 - Daily Game News Feed (Priority: P1)

A reader visiting the site on any day sees a clean, chronological list of up to 20 unique game update articles, free of duplicate or near-duplicate entries.

**Why this priority**: This is the primary deliverable of the game pipeline and provides continuous value every day.

**Independent Test**: Can be tested by running the game pipeline against a seeded set of 40 articles with known duplicates and verifying the output list contains ≤ 20 entries with no detectable duplicates.

**Acceptance Scenarios**:

1. **Given** a crawl produces new game articles, **When** the game pipeline processes them, **Then** the resulting feed contains at most 20 unique entries.
2. **Given** two articles whose cleaned titles are near-identical (similarity > 0.5), **When** deduplication runs, **Then** only the earlier-published article is retained.
3. **Given** one article's cleaned title is fully contained within another's, **When** deduplication runs, **Then** the shorter (sub-string) title article is discarded.
4. **Given** all incoming articles are unique, **When** deduplication runs, **Then** all articles are preserved (up to the 20-item limit, newest first).

---

### User Story 3 - Traffic Topic Clustering (Priority: P2)

The system groups related traffic articles into topic buckets so that the Weekly Insight focuses on the dominant theme rather than a random article.

**Why this priority**: Without clustering, the insight may be generated from an isolated article rather than the week's true dominant topic.

**Independent Test**: Can be tested by running the clustering and scoring logic against a fixed set of articles with known similarity scores, source counts, and publication dates, verifying that buckets are scored correctly and only those meeting the threshold are selected.

**Acceptance Scenarios**:

1. **Given** two traffic articles with a Jaccard similarity score between 0.20 and 0.45, **When** clustering runs, **Then** both are placed in the same topic bucket.
2. **Given** two traffic articles with a Jaccard similarity score above 0.45, **When** deduplication runs, **Then** only the article with the higher word count is kept; the other is discarded.
3. **Given** multiple topic buckets, **When** hot topic selection runs, **Then** only buckets whose composite score (article count + source diversity + day spread) meets the configured threshold are selected, up to a maximum of 3.
4. **Given** a topic bucket with high article count but all articles from one source published on the same day, **When** scoring runs, **Then** its composite score is lower than a bucket with fewer articles but broader source and temporal spread.

---

### User Story 4 - Shared Text Normalisation (Priority: P2)

All articles — regardless of category — pass through a common normalisation step so that similarity scores are computed on clean, comparable tokens.

**Why this priority**: Accurate deduplication depends entirely on consistent normalisation; inconsistency here causes false negatives (missed duplicates).

**Independent Test**: Can be tested by passing a fixed set of raw article titles through the normaliser and asserting that media tags, journalist names, full-width characters, and Chinese numerals are all converted to the expected canonical form.

**Acceptance Scenarios**:

1. **Given** a title containing 【記者X報導】 or ［影片］, **When** normalisation runs, **Then** those tags are stripped.
2. **Given** a title containing full-width digits (e.g., ２０２５), **When** normalisation runs, **Then** they are converted to half-width (2025).
3. **Given** a title containing Chinese numerals (e.g., 三人), **When** normalisation runs, **Then** they are converted to Arabic numerals (3人).
4. **Given** a title containing a road name or a numerical fact (e.g., "3死57歲"), **When** tokenisation runs, **Then** these are preserved as single tokens and not split.

---

### Edge Cases

- What happens when the Monday trigger fires but the AI service is unavailable? (Log error, skip week, retry next Monday — no partial or corrupted insight stored.)
- What happens when two articles have identical cleaned titles but were published by different sources? (The article with the higher word count is kept; source origin is preserved as metadata.)
- What happens when a game article's title is a single word or very short, making Jaccard similarity unreliable? (Fall back to exact-match inclusion check only; do not apply similarity threshold.)
- What happens when the weekly article buffer contains articles from a public holiday with unusually low volume? (Threshold of 3 articles still applies; if unmet, no insight is generated and the week is skipped.)
- What happens when a significant volume of articles land in the "uncategorised" bucket? (They accumulate visibly; the operator reviews the bucket periodically to decide whether to add a new taxonomy category. Uncategorised articles are subject to the same 8-week maximum buffer age.)

## Requirements *(mandatory)*

### Functional Requirements

**Shared Preprocessing (both pipelines)**

- **FR-001**: The system MUST strip decorative media tags matching the patterns `【…】`, `（…）`, and `[…]` from article titles before processing.
- **FR-002**: The system MUST remove trailing journalist name attributions and "link to…" suffixes from article titles.
- **FR-003**: The system MUST convert full-width digits to half-width and Chinese numeral words to Arabic numerals during normalisation.
- **FR-004**: The system MUST preserve road names and numerical facts (e.g., "3傷", "57歲") as indivisible tokens during word segmentation.
- **FR-005**: The system MUST compute a Jaccard similarity score between any two articles using the intersection-over-union of their normalised token sets.
- **FR-006**: The system MUST search for near-duplicate candidates within a 10-day rolling lookback window.

**Game News Pipeline**

- **FR-007**: The game pipeline MUST trigger inline upon each crawl completion, executing the full collect→filter→analyze→publish flow in a single operation.
- **FR-008**: The game pipeline MUST discard an article if its cleaned title is fully contained within another article's cleaned title.
- **FR-009**: The game pipeline MUST discard an article if its Jaccard similarity score against any retained article exceeds 0.50.
- **FR-010**: The game pipeline MUST produce an output list of at most 20 unique articles, ordered chronologically (newest first).
- **FR-011**: The game pipeline MUST NOT invoke the AI service under any circumstances.

**Traffic News Pipeline — Daily Phase**

- **FR-012**: Each day, the traffic pipeline MUST collect new traffic articles, apply shared preprocessing and deduplication, and persist them to the weekly article buffer. Nothing is published to the frontend during this phase.

**Traffic News Pipeline — Weekly Analysis Phase**

- **FR-013**: The traffic pipeline MUST merge articles with a Jaccard similarity score above 0.45, retaining the version with the highest word count.
- **FR-014**: The traffic pipeline MUST group articles with a Jaccard similarity score between 0.20 and 0.45 (inclusive) into a shared topic bucket. All Jaccard thresholds (cluster lower bound, cluster upper bound, merge threshold) MUST be externally configurable to allow post-launch tuning.
- **FR-015**: At ingestion (daily phase), each traffic article MUST be assigned a major category label via keyword matching against an externally configurable category taxonomy. Articles that match no known category MUST be placed in an "uncategorised" bucket. The taxonomy MUST be stored as an external configuration file (not hardcoded) so new categories can be added without code changes.
- **FR-016**: The weekly analysis MUST compute a cumulative category score by summing individual article scores across all buffered weeks for each major category. The cumulative score reflects both current-week volume and recurring significance across previous weeks (temporal score accumulation / momentum scoring).
- **FR-016b**: Only categories whose cumulative score meets or exceeds a configurable minimum threshold are selected for deep analysis, up to a maximum of 3 per weekly run.
- **FR-016c**: Articles that are not part of a selected hot-topic category MUST remain in the weekly buffer for the following week's analysis. Articles older than a configurable maximum buffer age (default: 8 weeks) MUST be expired and removed from the buffer.
- **FR-017**: The traffic pipeline MUST trigger the weekly analysis phase at 08:00 AM Taiwan Standard Time every Monday.
- **FR-018**: For each selected hot topic, the weekly analysis MUST perform a dedicated deep-analysis AI call using the titles and 200-character body snippets of the top 5–10 articles in that bucket.
- **FR-019**: Each hot-topic deep-analysis report MUST be persisted to the existing database and exposed via the existing news API as a separate publishable record.
- **FR-020**: If fewer than 3 traffic articles are available in the weekly buffer, the system MUST skip all AI calls and log the reason.

### Key Entities

- **Article**: A raw news item with title, body text, source URL, publication timestamp, and pipeline category (traffic or game).
- **NormalisedArticle**: A processed article with cleaned title, token set, word count, assigned major category label, and initial quality score, derived from the raw article at ingestion time.
- **TopicBucket**: A labelled group of normalised traffic articles whose pairwise Jaccard scores fall within the 0.20–0.45 range, accumulating a cumulative score across multiple weekly buffer cycles.
- **HotTopicReport**: An AI-generated deep-analysis report for one hot topic, containing the report text, the week start date, the topic label, and the source article count. Multiple HotTopicReports can exist per week (one per selected hot topic).
- **GameFeed**: The ordered list of up to 20 deduplicated game articles produced per crawl cycle.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The game feed contains zero detectable duplicate articles across a 10-day rolling window, measured against a reference test set with known duplicates.
- **SC-002**: The weekly traffic insight is published by 08:05 AM TST every Monday (within 5 minutes of trigger), with 100% on-time delivery over 4 consecutive weeks.
- **SC-003**: Total AI cost for traffic news analysis does not exceed $0.05 per week (single batch call per week).
- **SC-004**: Game news processing produces a deduplicated 20-article feed within 30 seconds of crawl completion.
- **SC-005**: Text normalisation achieves 100% removal of known tag patterns (【】, （）, ［］) on a fixed reference test set of 50 titles.
- **SC-006**: No change to the traffic pipeline causes a regression in game feed output, and vice versa (verified by independent pipeline test suites passing simultaneously).

## Assumptions

- The existing scraping infrastructure already collects raw articles and stores them; this feature adds the processing and analysis layer on top.
- "Game news" refers specifically to FFXIV (Final Fantasy XIV) update and patch news as already scraped by the project.
- "Traffic news" refers to Taiwanese road/transportation news articles already collected by the project.
- Taiwan Standard Time (UTC+8) is the reference timezone for all scheduled triggers.
- The existing database schema can accommodate the new entity types (WeeklyInsight, token arrays) without a full redesign.
- The existing AI integration (already present in the project) is reused for the weekly hot-topic deep analysis; no new AI provider needs to be onboarded.
- The category taxonomy is seeded with an initial set of common Taiwanese traffic news categories (e.g. 大型車安全、酒駕、道路施工、行人事故) at launch; the seed list is defined during planning.
- The existing frontend and API layer are extended to surface both the GameFeed and WeeklyInsight; no new delivery channel (email, webhook) is in scope for v1.
- Articles without a body longer than 200 characters are included in the weekly batch using their full available text.
