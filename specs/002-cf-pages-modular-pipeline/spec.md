# Feature Specification: Separate CF Pages + Modular Pipeline

**Feature Branch**: `002-cf-pages-modular-pipeline`
**Created**: 2026-05-04
**Status**: Draft
**Input**: User description: "separate CF pages first, then modular pipeline"

## Clarifications

### Session 2026-05-04

- Q: Should content-type outputs live as subdirectories under a shared `pages/` parent, or as separate root-level directories? → A: Subdirectories under `pages/` — `pages/traffic/` for traffic, `pages/ffxiv/` for FFXIV.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Independent Site per Content Type (Priority: P1)

A reader visiting the traffic news site sees only traffic articles. A different reader
visiting the FFXIV news site sees only FFXIV articles. Both sites are published from the
same weekly pipeline run, deployed to separate URLs, and operated independently.

**Why this priority**: Directly reader-visible value delivered without any internal
refactoring. Traffic readers are unaffected; FFXIV readers get a dedicated site.
Can be shipped immediately after the pipeline is stable.

**Independent Test**: After a weekly pipeline run, confirm that a traffic-only URL
shows only traffic articles and a separate FFXIV-only URL shows only FFXIV articles.
Both URLs must respond after the run completes.

**Acceptance Scenarios**:

1. **Given** the pipeline completes a weekly run with both traffic and FFXIV articles,
   **When** the traffic site is visited,
   **Then** only traffic articles appear; no FFXIV content is present.

2. **Given** the pipeline completes a weekly run with both traffic and FFXIV articles,
   **When** the FFXIV site is visited,
   **Then** only FFXIV articles appear; no traffic content is present.

3. **Given** the FFXIV source config is absent or all sources are disabled,
   **When** the pipeline runs,
   **Then** the traffic site is published normally; the FFXIV site is either skipped
   or left unchanged from the previous run.

4. **Given** a deployment failure for the FFXIV site,
   **When** the pipeline runs,
   **Then** the traffic site deployment is unaffected and completes successfully.

---

### User Story 2 - Content Module Architecture (Priority: P2)

A developer adding a new content category (e.g., cycling news, anime news) creates one
self-contained module that defines how to collect, filter, analyze, and publish that
category — without modifying any existing module, `main.py` logic, or shared pipeline
code beyond registering the new module.

**Why this priority**: Internal architecture improvement. Reduces future maintenance
burden and enables category-level independent testing. Depends on US1 being stable
first so the publisher parameterization is already in place.

**Independent Test**: Create a stub module for a hypothetical third category, register
it, and confirm the pipeline runs it alongside traffic and FFXIV without changes to
any other file. Remove the stub and confirm nothing breaks.

**Acceptance Scenarios**:

1. **Given** the traffic and FFXIV modules are registered,
   **When** the pipeline runs,
   **Then** both categories are collected, analyzed, and published as before — no
   behavioral regression.

2. **Given** a new category module is registered,
   **When** the pipeline runs,
   **Then** the new category is collected, analyzed, and published with no changes
   to existing modules.

3. **Given** one category module's collection stage fails,
   **When** the pipeline runs,
   **Then** other category modules complete normally; the failure is logged with the
   failing category name.

---

### Edge Cases

- What if `pages/traffic/` or `pages/ffxiv/` output dir doesn't exist yet? Publisher creates it on first run.
- What if FFXIV articles list is empty? FFXIV site is skipped for that run; traffic site publishes normally.
- What if a category module raises an unhandled exception? The orchestrator catches it, logs the error with the category name, and continues with remaining modules.
- What if both sites deploy to the same CF Pages project by misconfiguration? The spec requires distinct project names; this is a deployment configuration error, not a pipeline concern.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The pipeline MUST publish traffic articles to `pages/traffic/` and FFXIV articles to `pages/ffxiv/`; each is a subdirectory under the shared `pages/` parent.
- **FR-002**: Each output subdirectory MUST be deployed to its own independent CF Pages project via the automated workflow.
- **FR-003**: A deployment failure for one content type MUST NOT block or fail the deployment of another content type.
- **FR-004**: The traffic site output and deployment behavior MUST be functionally identical to the current behavior after this feature merges (same content, same structure — source directory path changes from `pages/` to `pages/traffic/`).
- **FR-005**: The pipeline orchestrator MUST support registering content category modules; each module MUST encapsulate its own collect, filter, analyze, and publish stages.
- **FR-006**: Adding a new content category MUST require no changes to existing category modules or the orchestrator beyond registering the new module.
- **FR-007**: Each category module MUST be independently runnable for testing without invoking other category modules.
- **FR-008**: The weekly automated workflow MUST deploy both sites in the same run without requiring separate manual triggers.

### Key Entities

- **ContentCategory**: A registered pipeline unit with: `name`, `content_type`, `max_articles`, `output_dir`; exposes `collect → filter → analyze → publish` stages.
- **OutputSite**: A content-type-specific static site directory (`pages/traffic/` for traffic, `pages/ffxiv/` for FFXIV) mapped to a distinct CF Pages hosting project.
- **DeployWorkflow**: A per-site automated deployment definition triggered after the pipeline produces its output directory.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Both sites are live and independently accessible within one pipeline run cycle after this feature merges.
- **SC-002**: Zero regressions in the traffic site — content and layout are unchanged from the pre-feature baseline; source directory migrates from `pages/` to `pages/traffic/`.
- **SC-003**: The full pipeline run (collect + analyze + publish + deploy both sites) completes within 15 minutes on the automated workflow.
- **SC-004**: Adding a third content category requires changes to exactly one new file plus a one-line registration — no edits to existing source files.
- **SC-005**: Each category module can be invoked in isolation (with stub inputs) and produce verifiable output without running the full pipeline.

## Assumptions

- A second Cloudflare Pages project for FFXIV content can be created on the existing free-tier account without additional cost.
- Output directories are organized as subdirectories under `pages/`: `pages/traffic/` for traffic and `pages/ffxiv/` for FFXIV. Adding a third category appends a new subdirectory (`pages/<name>/`) without adding root-level directories.
- Migrating the existing traffic site from `pages/` to `pages/traffic/` requires updating `deploy-pages.yml` (`directory: pages/traffic`) and moving existing files — a one-time migration step.
- The modular pipeline refactor (US2) reuses all existing logic from `src/collector.py`, `src/filter.py`, `src/analyzer.py`, and `src/publisher.py` — no logic duplication; modules are thin orchestration wrappers.
- No database schema changes are required for this feature; `content_type` column from the previous feature is sufficient.
- Email digest (`src/mailer.py`) is out of scope for this feature.
