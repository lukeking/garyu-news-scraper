# Quickstart: Separate CF Pages + Modular Pipeline

**Feature**: 002-cf-pages-modular-pipeline  
**Date**: 2026-05-04

---

## Running the Pipeline Locally

No new setup steps beyond feature 001. Both content types run by default.

```bash
cp config/sources_traffic.example.yml config/sources_traffic.yml
cp config/sources_ffxiv.example.yml   config/sources_ffxiv.yml
# edit both files to enable at least one source per type

python main.py
```

After the run:
- `pages/traffic/` — traffic static site output (migrated from `pages/`)
- `pages/ffxiv/` — FFXIV static site output (new in this feature)

---

## Running a Single Category Manually

```python
# Run only the traffic category
from src.pipeline.traffic import TrafficCategory
cat = TrafficCategory()
articles = cat.collect()
articles = cat.filter(articles)
articles = cat.analyze(articles)
week_id  = cat.publish(articles)
print(f"Traffic published: {week_id}, {len(articles)} articles")
```

```python
# Run only the FFXIV category
from src.pipeline.ffxiv import FFXIVCategory
cat = FFXIVCategory()
# ... same pattern as above
```

---

## Deploying the FFXIV Site

The FFXIV site (`pages-ffxiv/`) is deployed via `.github/workflows/deploy-pages-ffxiv.yml`.

**First-time setup**:
1. Create a new Cloudflare Pages project named `garyu-ffxiv-news` in the CF dashboard
2. Ensure `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` secrets are set in GitHub
   (these are shared with the existing traffic site deployment)
3. Run the `deploy-pages-ffxiv.yml` workflow manually from the Actions tab

**Subsequent deployments**: Triggered automatically when `pages/ffxiv/**` is pushed to `main`.

---

## Adding a New Content Category

1. **Create the module**: `src/pipeline/<name>.py` implementing the `Category` protocol (see `contracts/category-protocol.md`)
2. **Register it**: Add `<Name>Category()` to the `CATEGORIES` list in `main.py`
3. **Add sources config**: `config/sources_<name>.example.yml` with `content_type: "<name>"` entries
4. **Add deploy workflow**: `.github/workflows/deploy-pages-<name>.yml` (copy `deploy-pages-ffxiv.yml`, change `projectName` and `directory`)
5. **Add to weekly workflow**: If sources are injected via GitHub Variables, add an injection step to `weekly.yml`

No changes to any existing category modules, `src/collector.py`, `src/filter.py`, `src/analyzer.py`, or `src/publisher.py`.

---

## Environment Variables (New in This Feature)

| Variable | Where set | Purpose |
|---|---|---|
| `FFXIV_SITE_URL` | GitHub Environment Variable (optional) | Public URL of FFXIV CF Pages site; defaults to `https://garyu-ffxiv-news.pages.dev` |

All other env vars are unchanged from feature 001.

---

## Verifying a Full Run

After `python main.py` completes:

```bash
# Check traffic output
ls pages/traffic/data/
ls pages/traffic/week/

# Check FFXIV output (new)
ls pages/ffxiv/data/
ls pages/ffxiv/week/

# Check Supabase has both content types for this week
# (use the Supabase SQL editor or Worker API)
# GET /articles?week_id=2026-W19&content_type=traffic
# GET /articles?week_id=2026-W19&content_type=ffxiv
```
