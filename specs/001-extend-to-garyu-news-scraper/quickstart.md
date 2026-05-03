# Quickstart: Extend to Garyu News Scraper (FFXIV Integration)

**Date**: 2026-05-03

## Prerequisites

- Python 3.11+
- `.env` with `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- `config/sources.yml` (copy from `config/sources.example.yml`)
- `config/sources_ffxiv.yml` (copy from `config/sources_ffxiv.example.yml`)
- `knowledge-base.md` with ≥1 FFXIV term entry (≥20 recommended before production)

## 1. Install dependencies

```bash
pip install -r requirements.txt
```

## 2. Configure FFXIV sources locally

```bash
cp config/sources_ffxiv.example.yml config/sources_ffxiv.yml
# Edit sources_ffxiv.yml: set enabled: true/false per source
```

## 3. Seed the knowledge base

Edit `knowledge-base.md`. Add at minimum the core 8.0 content terms:

```markdown
| JP Term     | TW Term  | EN Term  | Category | Notes                |
|-------------|----------|----------|----------|----------------------|
| 零式        | 零式     | Savage   | Raid     | High-end raid tier   |
| 絶討伐戦    | 絕境戰   | Ultimate | Raid     | Highest difficulty   |
```

## 4. Apply the Supabase schema migration

Run in the Supabase SQL editor (Settings → SQL Editor):

```sql
ALTER TABLE articles
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'traffic';

CREATE INDEX IF NOT EXISTS articles_content_type_idx
  ON articles (content_type);
```

## 5. Run traffic-only (regression check)

```bash
python main.py
# Expected: existing traffic pipeline runs unchanged; no FFXIV articles yet
```

## 6. Run full pipeline (traffic + FFXIV)

```bash
# Ensure sources_ffxiv.yml exists with at least one enabled source
python main.py
# Expected: articles with content_type='ffxiv' appear in Supabase
```

Verify in Supabase:
```sql
SELECT content_type, COUNT(*) FROM articles
WHERE week_id = '2026-W19'
GROUP BY content_type;
-- Expected: traffic + ffxiv rows both present
```

## 7. Verify Cloudflare Worker filter

After deploying the updated Worker:
```
GET https://<worker-url>/articles?content_type=ffxiv&week_id=2026-W19
```
Expected: only FFXIV articles returned.

## GitHub Actions Setup

1. Add `SOURCES_FFXIV_YML` as a GitHub **Environment Variable** in the `production`
   environment (same location as `SOURCES_YML`).

2. The updated `weekly.yml` will inject it automatically:
   ```yaml
   - name: 寫入 config/sources_ffxiv.yml（從 GitHub Variable）
     run: echo "$SOURCES_FFXIV_YML" > config/sources_ffxiv.yml
     env:
       SOURCES_FFXIV_YML: ${{ vars.SOURCES_FFXIV_YML }}
   ```

3. Trigger manually: Actions → 台灣機車交通週報 → Run workflow.

4. Confirm run completes with no errors and `信件寄送成功` (or equivalent) in logs.

## Validation Checklist

- [ ] `python main.py` (traffic only) produces same output as before — no regression
- [ ] `python main.py` (with sources_ffxiv.yml) produces `content_type='ffxiv'` rows
- [ ] FFXIV summaries use terms from `knowledge-base.md`; no invented translations in logs
- [ ] No `[KB MISS]` log warnings for common FFXIV 8.0 terms
- [ ] Supabase `articles` has `content_type` column; existing rows show `'traffic'`
- [ ] Cloudflare Worker returns correct results for `?content_type=ffxiv`
- [ ] GitHub Actions run completes within 15 minutes
- [ ] `www.ffxiv.com.tw/robots.txt` checked before enabling TW site source
