# Research: YouTube Community Sources

**Date:** 2026-05-15
**Context:** The traffic news pipeline (006) surfaces mostly syndicated mainstream news.
When a hot event like 淡江大橋 breaks, 40+ outlets report the same story — after
embedding dedup, 67 candidates collapse to ~15 unique articles. The root problem is
that all current sources are news-media RSS feeds chasing the same events.

Community platforms (YouTube, FB, Threads) carry qualitatively different content:
long-form analysis, foreign traffic comparisons, community debate — none of which
appears in any RSS feed. This document records feasibility findings for adding those
platforms as pipeline sources.

---

## Platform Assessment

### YouTube — Viable ✓

**Data API v3**
- Credentials: Google Cloud API key only. No OAuth, no app review.
- Quota: 10,000 units/day free. `search` costs 100 units; `playlistItems` (polling a
  channel's uploads) costs 1 unit. Strategy: configure sources by channel ID and poll
  `playlistItems` — near-zero quota impact.
- Metadata returned: title, description, publishedAt, duration, tags, view/like counts.

**youtube-transcript-api (PyPI)**
- No credentials required — scrapes the caption endpoint directly.
- Supports auto-generated captions; `['zh-TW', 'zh']` preference list works.
- Version 1.2.4 (Jan 2026), actively maintained.
- **Cloud IP risk:** YouTube blocks requests from AWS/GCP/Azure. This pipeline runs on
  GitHub Actions — needs testing. Fallback: use the Data API's official caption endpoint
  (`captions.download`, requires OAuth) or accept transcript-less entries and rely on
  title + description for summarization.
- Transcript length: ~1,500 words / ~2,000 tokens for a 10-minute video. Fits cleanly
  within the existing Gemini summarization step.

**Pipeline integration estimate:** ~150 lines for a new `YouTubeSource` class.
Existing keyword filter, embedding dedup, and summarization steps work unchanged.
A new `type: youtube` entry in `sources_traffic.yml` taking `channel_id` and optional
`max_items` covers configuration.

**ToS note:** `youtube-transcript-api` scrapes an undocumented endpoint (gray area).
The Data API v3 itself is fully compliant.

---

### Facebook — Not Viable ✗

- **RSSHub** (`/facebook/page/{PageName}`): chronically broken. Meta aggressively
  blocks scrapers; the RSSHub FB route breaks repeatedly after layout changes. Community
  instances flag it as unreliable. Not suitable as a pipeline dependency.
- **Meta Graph API**: reading arbitrary public page posts requires the **Page Public
  Content Access (PPCA)** feature — business verification + detailed app review with
  screencast. Not practical for a personal/small project.
- **Meta Content Library API**: restricted to academic/non-profit researchers with
  institutional affiliation.
- **Third-party paid services** (RSS.app, FetchRSS): add cost and inherit the same
  underlying scraping fragility.

**Conclusion:** Blocked until Meta opens public read access. Revisit if PPCA review
requirements relax or a reliable third-party solution emerges.

---

### Threads — Not Viable ✗

Threads API is currently publishing-only (OAuth, user-scoped). Reading public posts
from arbitrary accounts is not available to general developers — requires Meta Content
Library access (academic/non-profit only). Not viable for this project.

---

## Recommendation

Build `type: youtube` only. Skip Facebook and Threads until the access model changes.

| Platform | Credential complexity | Content fit | New pipeline code | Viable |
|---|---|---|---|---|
| YouTube (Data API + transcript-api) | Low (API key) | High | ~150 lines | Yes |
| Facebook (RSSHub) | None, but unreliable | Medium | ~50 lines | No |
| Facebook (Graph API) | High (app review) | High | ~100 lines | No |
| Threads | High (app review) | Unknown | ~100 lines | No |

---

## Open Questions for Spec

1. GitHub Actions IP blocking for `youtube-transcript-api` — test first or build
   fallback (title + description only) from the start?
2. Which channel IDs to seed initially? Candidate categories:
   - TW traffic commentary channels
   - Foreign traffic comparison (JP/EU/US vs TW)
   - Road safety / advocacy channels
3. Should `type: youtube` entries go in the same `sources_traffic.yml` or a separate
   `sources_traffic_community.yml`?
4. Keyword filtering: transcripts are long — apply the existing `MOTORCYCLE_KEYWORDS`
   filter at the sentence level or whole-transcript level?
5. Quota monitoring: add a daily quota log or rely on Google Cloud Console alerts?
