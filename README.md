# 🏍️ 台灣機車交通週報自動系統

每週自動收集台灣機車交通相關新聞，透過 Gemini AI 分析摘要，寄送至 Gmail，並將資料寫入 Supabase。

完整部署步驟請看 [`docs/runbook.md`](docs/runbook.md)。

## 架構

```
收集（collector.py）
  ├── Google News RSS
  ├── PTT 機車板 / SuperBike 重機板
  ├── 聯合/中時/自由/TVBS/ETtoday RSS
  └── 交通部 / 公路局公告
        ↓
過濾去重（filter.py）
        ↓
AI 分析（analyzer.py）── Gemini 2.0 Flash（免費）
        ↓
寫入 Supabase（storage.py）
        ↓
Cloudflare Worker API（/api/*）
        ↓
Cloudflare Pages 前端 + Gmail 寄送（mailer.py）
```

## 排程

每週一台灣時間 08:00 自動執行（GitHub Actions）。

---

## 設定步驟

### 1. Fork 或 clone 此 repo

### 2. 取得必要的 API Key / 密碼

| 項目 | 取得方式 |
|------|---------|
| Gemini API Key | [aistudio.google.com](https://aistudio.google.com) → Get API key |
| Gmail App Password | Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼（16 位數）|

### 3. 在 GitHub 建立 Environment 並設定 Secrets / Variables

前往 repo → **Settings → Environments → New environment**，命名為 `production`。

#### Secrets（機敏資訊，內容隱藏）

在 production environment 加入以下 secrets：

| Secret 名稱 | 說明 |
|------------|------|
| `GEMINI_API_KEY` | Gemini API 金鑰 |
| `GMAIL_APP_PASSWORD` | Gmail 應用程式密碼（16 位數，格式：`xxxx xxxx xxxx xxxx`）|
| `GMAIL_SENDER` | 你的 Gmail 地址（同時為收件者）|
| `GEMINI_MODEL_NAME` | 選填，預設 `gemini-2.0-flash`，可改為 `gemini-2.5-flash` 等 |
| `SUPABASE_URL` | Supabase project URL（`https://xxx.supabase.co`） |
| `SUPABASE_SERVICE_ROLE_KEY` | **必備**：Supabase **service_role** key（Dashboard → Settings → API）。週報寫入與 Worker 皆需略過 RLS；勿用 anon key 當寫入金鑰 |
| `SUPABASE_KEY` | 選填；僅在未設定 `SUPABASE_SERVICE_ROLE_KEY` 時作為後備（仍須為可寫入的金鑰，不可誤用 anon） |
| `CLOUDFLARE_API_TOKEN` | GitHub Actions 部署 Worker 用 token |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account id |

#### Variables（非機敏設定，內容可見可編輯）

在 production environment 加入以下 variable：

| Variable 名稱 | 說明 |
|--------------|------|
| `SOURCES_YML` | `config/sources.yml` 的完整內容（見下方說明）|

> **Secrets vs Variables 的差別：**
> Secrets 的值一旦儲存就無法再看到（只能覆蓋）；Variables 的值可以隨時查看和編輯，
> 適合用來存放不含密碼的設定，例如 `config/sources.yml`。

### 4. 設定 `SOURCES_YML` Variable

`config/sources.yml` 定義所有新聞來源，**不進 git**，改為存在 GitHub Variable 中。
每次 workflow 執行時會自動把 variable 的內容寫成 `config/sources.yml` 檔案。

**步驟：**

1. 複製 `sources.example.yml` 的內容（或參考下方格式）
2. 前往 repo → **Settings → Environments → production → Environment variables → Add variable**
3. Name 填 `SOURCES_YML`，Value 貼上 YAML 內容
4. 儲存

**之後要新增/停用來源，只要：**

Settings → Environments → production → `SOURCES_YML` → 鉛筆圖示編輯 → 儲存。
下次 workflow 執行就自動生效，完全不需要動程式碼。

### 5. 手動執行測試

在 GitHub → **Actions → 台灣機車交通週報 → Run workflow**，
觀察 log 確認最後出現 `信件寄送成功` 即完成設定。

---

## `config/sources.yml` 格式說明

`config/sources.yml` 支援三種 type，詳細欄位說明請見 `config/sources.example.yml`。

### type: rss — RSS / Atom feed

```yaml
- name: Google News 機車交通      # 顯示在 log 與信件來源標籤
  type: rss
  enabled: true                   # false 可停用，不需要刪除
  url: "https://news.google.com/rss/search?q=機車+交通&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
```

- Google News RSS 支援 `site:` 運算子，可鎖定特定媒體，例如：
  ```
  q=機車+site:udn.com
  ```
- 主流新聞網 RSS（非 Google News）會用關鍵字二次過濾，Google News 不需要（query 已鎖定主題）。

### type: ptt — PTT 看板爬蟲

```yaml
- name: PTT/biker
  type: ptt
  enabled: true
  board: biker          # 板名，注意大小寫（biker、SuperBike）
  min_pushes: 5         # 只收推文數 >= 5 的文章；「爆」自動視為 10
```

- PTT 板名**大小寫有別**，例如 `SuperBike`（S 和 B 要大寫）。
- `min_pushes` 可調整，發文較少的板可以設低一點（如 3）。

### type: web — 網頁爬蟲

```yaml
- name: 交通部
  type: web
  enabled: true
  url: "https://www.motc.gov.tw/ch/home.jsp?id=14&parentpath=0,2"
  max_items: 10         # 最多抓幾筆命中關鍵字的連結
```

### 常用操作速查

| 想做什麼 | 怎麼改 |
|---------|-------|
| 停用某來源 | `enabled: false` |
| 新增 Google News 主題 | 複製任一 `type: rss` block，修改 `name` 和 `url` 的 query 參數 |
| 新增 PTT 看板 | 複製任一 `type: ptt` block，修改 `name` 和 `board` |
| 調整推文門檻 | 修改 `min_pushes` 數字 |
| 新增官網爬蟲 | 複製任一 `type: web` block，修改 `name` 和 `url` |

---

## 本機測試

```bash
# 安裝相依套件
pip install -r requirements.txt

# 複製 .env 範本並填入實際值
cp .env.example .env
# 編輯 .env，填入 GEMINI_API_KEY、GMAIL_APP_PASSWORD、GMAIL_SENDER

# 複製 config/sources.yml 範本（或直接用 config/sources.example.yml 的內容）
cp config/sources.example.yml config/sources.yml
# 依需求編輯 config/sources.yml

# 執行
python main.py

# 啟動 Cloudflare Worker API（另一個終端）
# 需先設定 workers/api 的本機環境變數
npx wrangler dev workers/api/src/index.js
```

`.env` 和 `config/sources.yml` 已在 `.gitignore` 中排除，不會被 commit。

---

## 檔案說明

| 檔案 | 說明 | 進 git？ |
|------|------|---------|
| `main.py` | 主程式入口 | ✅ |
| `collector.py` | 多來源新聞抓取，由 `config/sources.yml` 驅動 | ✅ |
| `filter.py` | 機車關鍵字過濾 + 去重複 | ✅ |
| `analyzer.py` | Gemini API 摘要與深度分析 | ✅ |
| `mailer.py` | HTML 信件組裝 + Gmail SMTP 寄送 | ✅ |
| `requirements.txt` | Python 相依套件 | ✅ |
| `.github/workflows/weekly.yml` | GitHub Actions 排程設定 | ✅ |
| `config/sources.example.yml` | `config/sources.yml` 格式範本，含欄位說明 | ✅ |
| `.env.example` | 本機測試環境變數範本 | ✅ |
| `config/sources.yml` | 實際使用的來源設定（不進 git） | ❌ |
| `.env` | 本機測試用的 API key / 密碼（不進 git） | ❌ |

---

## 注意事項

- Gemini 免費 tier 每分鐘有請求數限制，程式已內建 2.5 秒間隔
- 每次最多分析 30 篇文章（可在 `main.py` 調整 `filtered[:30]`）
- GitHub Actions 免費方案每月 2,000 分鐘，本 job 每次約 5 分鐘，一年約用 260 分鐘
- 切換 Gemini 模型不需改 code，在 GitHub Secrets 設定 `GEMINI_MODEL_NAME` 即可
- 前端預設讀取 `/api/*`，Cloudflare Pages 需將 `/api/*` 路由到 Worker