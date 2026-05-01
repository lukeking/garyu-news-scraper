# Runbook: Supabase + Cloudflare Deployment

This runbook is for first-time setup from zero to production.

## 0) Prerequisites

- GitHub repo already contains this project.
- Supabase project already created, and `articles` table schema applied.
- You can log into Cloudflare and GitHub repo settings.

## 1) Create Cloudflare Pages project

1. Open [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Go to `Workers & Pages` -> `Create` -> `Pages` -> `Connect to Git`.
3. Select this GitHub repo.
4. Build settings:
   - Framework preset: `None`
   - Build command: leave empty
   - Build output directory: `docs`
5. Create/deploy.
6. Keep the Pages project name (used by `deploy-pages.yml`).

## 2) Create Cloudflare Worker project

1. In Cloudflare Dashboard, go to `Workers & Pages` -> `Create` -> `Workers`.
2. Create a worker with name matching `workers/api/wrangler.toml` (default: `traffic-issue-api`).
3. Save the generated `*.workers.dev` URL.

## 3) Configure Worker runtime secrets/vars

In Worker settings (`Settings` -> `Variables and Secrets`):

- Add variable:
  - `SUPABASE_URL` = `https://<your-project>.supabase.co`
- Add secret:
  - `SUPABASE_SERVICE_ROLE_KEY` = your Supabase service role key

## 4) GitHub Secrets setup

Go to repo -> `Settings` -> `Secrets and variables` -> `Actions` and add:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`（**service_role**，與 Worker 相同；週報 `main.py` 寫入優先使用此 secret，`articles` 表若啟用 RLS，anon key 會得到 42501）
- `SUPABASE_KEY`（選填；僅在尚未設定 service role secret 時後備）
- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

Notes:
- Reuse the same **service_role** JWT for the weekly GitHub Action and the Worker (both need to bypass RLS for server-side reads/writes).
- Do not put the **anon** `public` key in `SUPABASE_KEY` expecting writes to succeed when RLS is enabled on `articles`.
- Safer long-term: separate keys/roles when you later refine access control.

## 5) Create CLOUDFLARE_API_TOKEN with minimum scope

Create a custom Cloudflare API token with:

- Account permissions:
  - `Cloudflare Pages:Edit`
  - `Workers Scripts:Edit`
- Account resources:
  - include only your target account

Optional only if you later manage routes via CI:
- `Workers Routes:Edit`

## 6) Confirm repo config before deploy

1. Check `workers/api/wrangler.toml`:
   - `name` should match Worker name.
2. Check `.github/workflows/deploy-pages.yml`:
   - `projectName` should match your actual Pages project.
3. Check `docs/index.html`:
   - default is `'/api'`.
   - if you cannot bind `/api/*` on Pages UI, set API base to Worker URL:
     - `https://<worker>.workers.dev/api`

## 7) Deploy order (recommended)

1. Run GitHub Action: `Deploy Cloudflare Worker API`.
2. Verify Worker endpoints:
   - `https://<worker>.workers.dev/api/weeks`
   - `https://<worker>.workers.dev/api/tags`
3. Run GitHub Action: `Deploy Cloudflare Pages`.
4. Open Pages site and test:
   - week switch
   - importance filter
   - tag filter
   - keyword search

## 8) Run weekly pipeline smoke test

1. Run GitHub Action: `台灣機車交通週報` (`workflow_dispatch`).
2. Confirm job logs include:
   - Supabase ping status
   - `Supabase read-after-write OK: <week_id>`
3. Refresh Pages frontend and verify newest week appears.

## 9) Historical data backfill

Run locally (once):

```bash
python backfill_supabase.py --dry-run
python backfill_supabase.py
```

## 10) Troubleshooting

- **Pages cannot bind `/api/*` to Worker in UI**
  - Use Worker public URL directly in frontend API base.
- **403/401 from Supabase in Worker**
  - Check `SUPABASE_SERVICE_ROLE_KEY` secret exists in Worker runtime.
- **Deploy-worker action fails auth**
  - Recheck `CLOUDFLARE_API_TOKEN` scopes and account restriction.
- **Pages deploy succeeds but site has no data**
  - Check browser network calls for `/api/weeks` and confirm CORS/API base URL.
