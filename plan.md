## Plan: Extend Garyu News Scraper for FFXIV Integration

Extend the existing traffic-issue-scraper codebase into garyu-news-scraper by adding FFXIV 8.0 battle information scraping capabilities, implementing a knowledge base for term normalization, and preserving all existing traffic news functionality.

**Steps**
1. Refactor project structure: Create `src/scrapers/traffic/` and `src/scrapers/ffxiv/` directories, moving existing scraper logic into `traffic/` and preparing `ffxiv/` for new implementation.
2. Implement FFXIV data collection: Add new fetchers in `collector.py` for Reddit RSS and JP forum HTML scraping, with source configuration in separate `sources_ffxiv.yml`.
3. Initialize knowledge base: Create `knowledge-base.md` from `knowledge-base-template.md`, implement lookup functions in analyzer, and add auto-update logic for new terms.
4. Update AI analyzer: Modify `analyzer.py` to support FFXIV-specific prompts referencing the knowledge base, with separate analysis modes for traffic vs. FFXIV content.
5. Enhance filtering and publishing: Update `filter.py` and `publisher.py` to handle dual content types, with parallel filtering logic and unified storage in Supabase.
6. Repair GitHub Actions workflows: Fix any broken workflows in `.github/workflows/`, ensuring weekly runs and deployments work correctly.
7. Deploy separate frontends: Configure separate Cloudflare Pages deployments for traffic and FFXIV content, with distinct domains or paths.
8. Clean up: Delete `README_v2.md` file after plan approval. Keep `knowledge-base-template.md` for ongoing improvements and term refinement.

**Relevant files**
- `collector.py` — Add FFXIV fetchers (_fetch_reddit, _fetch_jp_forum)
- `sources_ffxiv.yml` — New file for FFXIV source configurations
- `analyzer.py` — Add FFXIV prompt and knowledge base integration
- `filter.py` — Add FFXIV keyword lists and filtering logic
- `publisher.py` — Update for dual content publishing
- `knowledge-base.md` — New file for term mappings
- `.github/workflows/` — Repair broken workflows
- `docs/` — Split into traffic and ffxiv subdirs for separate deployments

**Verification**
1. Run `python main.py` with traffic sources to ensure existing functionality unchanged.
2. Add FFXIV sources to `sources_ffxiv.yml` and test collection of sample articles.
3. Verify knowledge base lookup prevents unknown terms in summaries.
4. Execute full pipeline and check Supabase storage for both content types.
5. Test separate frontend deployments for traffic and FFXIV.
6. Confirm GitHub Actions run successfully without errors.

**Decisions**
- Preserve existing traffic news pipeline without disruption.
- Use shared Supabase schema for both content types, differentiated by tags or source.
- Implement knowledge base as markdown file with CI validation, auto-updating via PRs.
- Exclude non-technical content from FFXIV summaries per template guidelines.
- Separate source definitions: `sources_traffic.yml` for traffic, `sources_ffxiv.yml` for FFXIV.
- Separate frontend deployments: Traffic on main domain, FFXIV on subdomain or separate Pages project.

**Further Considerations**
1. Should FFXIV and traffic content be separated in the frontend UI, or integrated with filters?
2. How to handle multi-language sources (JP forums) for consistent Chinese summaries?
3. For FFXIV scraping: Official sites like ffxiv.com.tw and jp.finalfantasyxiv.com have patch notes and guides, but no RSS. Scrape HTML from patch note logs (e.g., https://www.ffxiv.com.tw/web/special/patchnote_log/index.html) for new entries. For forums, identify JP FFXIV community forums (e.g., search for "FFXIV JP forum" to find sites like https://forum.square-enix.com/ffxiv/ or similar). Reddit RSS available via https://www.reddit.com/r/ffxiv/new/.rss. Problem: Parsing unstructured forum posts vs. structured patch notes; may need different filtering logic for relevance.