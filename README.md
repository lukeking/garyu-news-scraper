# Garyu News Scraper

每週自動收集新聞、透過 Gemini AI 分析摘要，並部署至 Cloudflare Pages。

目前支援兩條 pipeline：

| Pipeline | 內容 | 前端網址 |
|----------|------|---------|
| 🏍️ 台灣機車交通週報 | 台灣機車交通相關新聞 | `garyu-traffic-news.pages.dev` |
| ⚔️ Garyu FFXIV 週報 | FFXIV 最終幻想 XIV 資訊 | `garyu-ffxiv-news.pages.dev` |

---

## 架構

```
收集（collector.py）
  ├── Google News RSS
  ├── PTT 看板爬蟲
  ├── 各大新聞網 RSS
  └── 官網爬蟲（交通部等）
        ↓
新鮮度過濾（filter.py）
  ├── 跨週標題指紋去重（Supabase 歷史比對）
  └── 30 天時效過濾（pubDate / Google News URL 日期）
        ↓
關鍵字過濾 + 去重（filter.py）
        ↓
AI 分析（analyzer.py）── Gemini（可設定模型）
  └── FFXIV pipeline 額外載入 knowledge-base.md 術語對照
        ↓
寫入 Supabase（storage.py）
        ↓
發布靜態檔案（publisher.py）── feed.xml、week/*.html
        ↓
部署至 Cloudflare Pages（weekly.yml 觸發）
        ↓
前端讀取 CF Worker API（/api/*）← 從 Supabase 查詢資料
```

**排程**：每週一 UTC 00:00（台灣 08:00）自動執行。

---

## Cloudflare 部署架構

```
garyu-traffic-news (CF Pages)  →  pages/traffic/
garyu-ffxiv-news   (CF Pages)  →  pages/ffxiv/
garyu-news-scraper (CF Worker) →  workers/api/   ← 兩個 Pages 共用
```

`pages/*/index.html` 的 `/api/*` 請求，由 `functions/api/[[path]].js`（CF Pages Function）代理至 Worker（透過 `API` Service Binding 設定）。

---

## 設定步驟

### 1. Fork 或 clone 此 repo

### 2. Supabase — 建立資料庫

1. 建立 Supabase project
2. 在 SQL Editor 執行 `db/supabase_schema.sql`
3. 若升級既有資料庫，依序執行 `db/supabase_migrations/` 內的 SQL

### 3. Cloudflare — 建立三個專案

**CF Worker（API）**

1. Dashboard → Workers & Pages → Create → Workers
2. 建立後不需手動配置，CI 會在首次部署時自動寫入 Secret 與設定

**CF Pages（Traffic + FFXIV）**

各建一個 Pages project，設定如下：

| 設定 | Traffic | FFXIV |
|------|---------|-------|
| 連結 GitHub repo | ✓ | ✓ |
| Build command | 留空 | 留空 |
| Build output directory | `pages/traffic` | `pages/ffxiv` |

> Pages project name 決定 `*.pages.dev` 網址，建立後無法更改，請謹慎命名。

**CF Pages Function — API Binding**

兩個 Pages 專案均需設定 Service Binding：

Dashboard → Pages 專案 → Settings → Functions → Service bindings → Add:
- Variable name: `API`
- Service: 選擇 `garyu-news-scraper` Worker

### 4. GitHub — 建立 Environment 並設定 Secrets / Variables

前往 repo → Settings → Environments → New environment，命名為 `production`。

#### Secrets（機敏，儲存後無法查看）

| Secret | 說明 |
|--------|------|
| `GEMINI_API_KEY` | Gemini API 金鑰（[aistudio.google.com](https://aistudio.google.com)） |
| `SUPABASE_URL` | Supabase project URL（`https://xxx.supabase.co`） |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase **service_role** key（Dashboard → Settings → API）。週報寫入與 Worker 均需略過 RLS，勿用 anon key |
| `CLOUDFLARE_API_TOKEN` | 需有 `Cloudflare Pages:Edit` 與 `Workers Scripts:Edit` 權限 |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID |

#### Variables（可見可編輯）

| Variable | 說明 |
|----------|------|
| `GEMINI_MODEL_NAME` | 模型 ID，例如 `gemini-2.0-flash`（建議存為 Variable 避免 log 遮罩） |
| `SOURCES_TRAFFIC_YML` | `config/sources_traffic.yml` 的完整內容（見下方說明） |
| `SOURCES_FFXIV_YML` | `config/sources_ffxiv.yml` 的完整內容（選填，不設定則跳過 FFXIV pipeline） |
| `TRAFFIC_SITE_URL` | Traffic 前端網址，例如 `https://garyu-traffic-news.pages.dev` |
| `FFXIV_SITE_URL` | FFXIV 前端網址，例如 `https://garyu-ffxiv-news.pages.dev` |

### 5. 設定來源 YAML

`config/sources_*.yml` 不進 git，改存在 GitHub Variables。每次 workflow 執行時自動還原為檔案。

複製範本內容：
- `config/sources_traffic.example.yml` → 填入 `SOURCES_TRAFFIC_YML`
- `config/sources_ffxiv.example.yml` → 填入 `SOURCES_FFXIV_YML`

**之後新增/停用來源**：Settings → Environments → production → 對應 Variable → 編輯儲存。

### 6. 首次部署

依序執行 GitHub Actions（手動觸發 workflow_dispatch）：

1. `Deploy Cloudflare Worker API` — 建立 Worker 並上傳 Secret
2. `Garyu News Scraper 週報` — 執行完整 pipeline 並部署兩個 Pages

---

## 來源設定格式（`sources_*.yml`）

### type: rss

```yaml
- name: Google News 機車交通
  type: rss
  enabled: true
  url: "https://news.google.com/rss/search?q=機車+交通&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
```

### type: ptt

```yaml
- name: PTT/biker
  type: ptt
  enabled: true
  board: biker       # 板名大小寫有別（biker、SuperBike）
  min_pushes: 5      # 只收推文數 >= N 的文章
```

### type: web

```yaml
- name: 交通部
  type: web
  enabled: true
  url: "https://www.motc.gov.tw/ch/home.jsp?id=14&parentpath=0,2"
  max_items: 10
```

| 常用操作 | 方法 |
|---------|------|
| 停用來源 | `enabled: false` |
| 新增 Google News 主題 | 複製 rss block，修改 `url` 的 `q=` 參數 |
| 新增 PTT 看板 | 複製 ptt block，修改 `board` |
| 調整推文門檻 | 修改 `min_pushes` |

---

## FFXIV 知識庫

`knowledge-base.md` 提供術語對照表（JP → TW / EN），供 Gemini 分析時使用。格式說明見 `config/knowledge-base-template.md`。

Pipeline 執行後若出現 `[KB MISS]` 日誌，代表出現未收錄術語。使用 `ffxiv-term-translator` subagent 查詢後，將新詞條加入 `knowledge-base.md`。

---

## 本機測試

```bash
# 安裝相依套件
pip install -r requirements.txt

# 複製並填寫環境變數
cp .env.example .env

# 複製來源設定
cp config/sources_traffic.example.yml config/sources_traffic.yml
cp config/sources_ffxiv.example.yml config/sources_ffxiv.yml

# 執行 pipeline
python main.py

# 啟動 Worker API（另一個終端）
cd workers/api && npx wrangler dev
```

`.env` 和 `config/sources_*.yml` 已在 `.gitignore` 排除。

---

## 主要檔案

| 路徑 | 說明 |
|------|------|
| `main.py` | 入口（shim → `src/main.py`） |
| `src/main.py` | 主程式：依序執行各 pipeline |
| `src/collector.py` | 多來源新聞收集 |
| `src/filter.py` | 新鮮度過濾 + 關鍵字過濾 + 去重 |
| `src/analyzer.py` | Gemini AI 摘要與分析 |
| `src/storage.py` | Supabase 讀寫 |
| `src/publisher.py` | 靜態檔案輸出（feed.xml、week/*.html） |
| `src/pipeline/traffic.py` | Traffic pipeline 設定 |
| `src/pipeline/ffxiv.py` | FFXIV pipeline 設定 |
| `knowledge-base.md` | FFXIV 術語對照表（JP/TW/EN） |
| `workers/api/src/index.js` | CF Worker API（讀取 Supabase） |
| `functions/api/[[path]].js` | CF Pages Function（代理 `/api/*` 至 Worker） |
| `pages/traffic/index.html` | Traffic 前端（含深色模式、過時標記） |
| `pages/ffxiv/index.html` | FFXIV 前端（含深色模式、過時標記） |
| `config/sources_traffic.example.yml` | Traffic 來源設定範本 |
| `config/sources_ffxiv.example.yml` | FFXIV 來源設定範本 |
| `config/knowledge-base-template.md` | KB 詞條格式說明 |
| `db/supabase_schema.sql` | 資料庫 schema |
| `db/supabase_migrations/` | 增量 migration SQL |
| `.github/workflows/weekly.yml` | 週報 pipeline + 部署 |
| `.github/workflows/deploy-worker.yml` | Worker 手動部署 |
| `.github/workflows/deploy-pages-traffic.yml` | Traffic Pages 快速部署（index.html 異動時） |
| `.github/workflows/deploy-pages-ffxiv.yml` | FFXIV Pages 快速部署（index.html 異動時） |

---

## 注意事項

- Gemini 免費 tier 每分鐘有請求數限制，程式內建間隔避免 429
- `SUPABASE_KEY` secret 為舊版後備，建議統一使用 `SUPABASE_SERVICE_ROLE_KEY`
- Pipeline 執行失敗時可直接重跑 `workflow_dispatch`；新鮮度指紋去重會跳過已寫入 Supabase 的文章
