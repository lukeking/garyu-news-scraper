# Research: Separate CF Pages + Modular Pipeline

**Feature**: 002-cf-pages-modular-pipeline  
**Date**: 2026-05-04

---

## Decision 1: Publisher Parameterization Strategy

**Decision**: Add `output_dir: str = "pages"` parameter to `publish()`. All internal path vars (`DOCS_DIR`, `DATA_DIR`, `WEEK_DIR`) are computed relative to `output_dir` at call time — no module-level constants.

**Rationale**: Minimal diff. The caller passes either `"pages"` (traffic) or `"pages-ffxiv"` (FFXIV); everything else is unchanged. Avoids duplicating the publish logic into a separate FFXIV function. Adding a `site_url` parameter alongside `output_dir` handles the per-site `SITE_URL` env var difference.

**Alternatives considered**:
- Separate `publish_ffxiv()` function: rejected — duplicates ~60 lines, violates DRY, doubles the maintenance surface.
- Subclass/inheritance: rejected — over-engineered for a single string parameter difference.
- Config object: deferred to US2 where it becomes the `output_dir` field on `Category`.

---

## Decision 2: FFXIV Deploy Workflow Trigger Mechanism

**Decision**: New `deploy-pages-ffxiv.yml` file, mirroring `deploy-pages.yml` exactly, with `projectName: garyu-ffxiv-news` (or user-chosen name) and `directory: pages-ffxiv`. Triggered on `push: paths: ["pages-ffxiv/**"]` and `workflow_dispatch`.

**Rationale**: Consistent with existing pattern. Deploy workflows are independent — a FFXIV deploy failure does not block traffic deploy (satisfies FR-003). Manual redeploy via `workflow_dispatch` is preserved for both sites independently.

**Alternatives considered**:
- Add inline deploy step to `weekly.yml`: rejected — mixes pipeline and deploy concerns; harder to manually redeploy without rerunning the full pipeline.
- `workflow_run` event: rejected — adds coupling; the deploy workflow running after `weekly.yml` finishes adds latency and makes debugging harder.

---

## Decision 3: Category Module Boundary (Thin Wrappers)

**Decision**: Each Category module (`traffic.py`, `ffxiv.py`) is a thin wrapper that calls the existing `src/collector.py`, `src/filter.py`, `src/analyzer.py`, and `src/publisher.py` functions. No logic is duplicated into the category modules. Shared stage logic stays in `src/`.

**Rationale**: Constitution Principle V explicitly requires sub-module promotions to be complete migrations with no logic duplication. Thin wrappers satisfy this — they orchestrate, not implement. The four existing stage modules become the "library"; the category modules become the "policy."

**Alternatives considered**:
- Move logic into category modules: rejected — duplicates code, violates Principle V, makes KB and filter logic diverge over time.
- Protocol-only approach (no base class): chosen — Python structural typing via `Protocol` is sufficient; no abstract base class needed.

---

## Decision 4: Cloudflare Pages Multi-Project Free Tier

**Decision**: CF Pages free tier supports unlimited projects. Second project (`garyu-ffxiv-news`) costs nothing additional.

**Rationale**: Verified from CF Pages pricing page — the free plan has no project count limit. Both projects share the same `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets already in the repo.

**Alternatives considered**: None — no cost, no alternative needed.

---

## Decision 5: Category Collect Decomposition

**Decision**: `collect_all()` in `src/collector.py` stays as-is. Each category module calls `collect_all()` and post-filters by `content_type`, or alternatively, `collect_all()` is refactored to expose `collect_traffic()` and `collect_ffxiv()` as separate public functions that `collect_all()` calls internally.

**Rationale**: The cleaner long-term design exposes per-source-type collect functions so category modules can call their own without running both. This aligns with Principle V (each module owns its concern). `collect_all()` is kept for backwards compatibility.

**Implementation choice**: Add `collect_by_type(content_type: str) -> list` to `src/collector.py` that returns only sources matching the given content type. Category modules call `collect_by_type("traffic")` or `collect_by_type("ffxiv")`.

---

## Decision 6: Supabase Write Scope (Centralized vs Per-Category)

**Decision**: Supabase write remains centralized in `main.py` after all categories finish. `publish()` (and category modules' publish stage) only handles the static file output.

**Rationale**: Supabase stores all articles in one table with `content_type` as a filter column. A single upsert with all articles is simpler and idempotent. If a second Supabase table is added for FFXIV in the future, that's a separate migration.

**Alternatives considered**: Per-category Supabase writes — rejected; adds complexity and partial-write risk if one category fails mid-run.

---

## Decision 7: Category Module Location

**Decision**: `src/pipeline/traffic.py` and `src/pipeline/ffxiv.py` with `src/pipeline/__init__.py` and `src/pipeline/base.py`. This is the sub-module path referenced in Constitution Principle V.

**Rationale**: Constitution explicitly names `src/scrapers/traffic/` and `src/scrapers/ffxiv/` as future sub-module paths for *collector* logic specifically. Since this refactor covers all four stages (not just collection), `src/pipeline/` is the correct location for full-stage category orchestrators.

---

## No Unresolved Clarifications

All design decisions are resolved. No `NEEDS CLARIFICATION` markers remain.
