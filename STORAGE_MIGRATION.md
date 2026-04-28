# 儲存方案遷移計畫

> 狀態：📋 規劃中
> 建立日期：2026-04-28
> 背景：目前使用 GitHub Actions Artifacts 部署靜態資產至 GitHub Pages，資料不進 git。此方案適合早期驗證，但長期需要可靠的持久化儲存。

---

## 現況問題

| 問題 | 說明 |
|------|------|
| 資料不持久 | Artifacts 預設保留 90 天，到期自動刪除 |
| 無法查詢 | JSON 檔案無法做跨週搜尋、統計、過濾 |
| 擴充困難 | 加新欄位需手動處理所有歷史 JSON |
| 無備援 | repo 搬移或 Pages 設定異動就歸零 |
| 標籤管理弱 | `tags.json` 每次跑才更新，無法跨 session 累積 |

---

## 目標架構

```
GitHub Actions（每週一）
  ↓ 分析完成
publisher.py
  ├── 寫入 DB / Storage（持久）
  ├── 產生 docs/data/*.json（供前端讀取）
  └── 產生 docs/feed.xml（RSS）
  ↓
GitHub Pages（靜態展示層，不變）
```

前端繼續讀 JSON，DB 作為資料來源與備援，兩層解耦。

---

## 方案比較

### 方案 A｜Supabase（PostgreSQL）⭐ 推薦

**適用場景：** 需要 SQL 查詢、未來可能開放 API 或做統計分析

| 項目 | 說明 |
|------|------|
| 費用 | 免費 tier：500MB DB + 1GB Storage，足夠數年資料 |
| 連線方式 | `psycopg2` 或 Supabase Python SDK |
| GitHub Actions 整合 | 加 `SUPABASE_URL` + `SUPABASE_KEY` 兩個 Secret |
| 資料格式 | 結構化，支援 JSONB 欄位存 `analysis` |
| 查詢能力 | 完整 SQL，可做跨週趨勢、標籤統計 |
| 風險 | 免費 tier 閒置 7 天暫停（需定期 ping）|

**Schema 草案：**
```sql
CREATE TABLE articles (
  id          SERIAL PRIMARY KEY,
  week_id     TEXT NOT NULL,          -- '2026-W18'
  title       TEXT NOT NULL,
  link        TEXT UNIQUE,
  source      TEXT,
  published   TEXT,
  summary     TEXT,
  analysis    JSONB,                  -- {summary, analysis, importance, tags, ...}
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_articles_week_id ON articles(week_id);
CREATE INDEX idx_articles_importance ON articles((analysis->>'importance'));
```

---

### 方案 B｜GitHub Releases（Asset 儲存）

**適用場景：** 零外部依賴，維持純 GitHub 生態

| 項目 | 說明 |
|------|------|
| 費用 | 免費，Release Assets 無到期限制 |
| 連線方式 | GitHub API（`requests` + `GITHUB_TOKEN`） |
| 資料格式 | JSON 檔案，每週一個 Release |
| 查詢能力 | 無，需自行下載合併 |
| 風險 | API rate limit；repo 搬移仍有影響 |

---

### 方案 C｜Cloudflare R2（Object Storage）

**適用場景：** 大量靜態資產、未來可能儲存圖片或附件

| 項目 | 說明 |
|------|------|
| 費用 | 免費 tier：10GB 儲存 + 每月 1000 萬次 Class A 操作 |
| 連線方式 | S3 相容 API（`boto3`） |
| 資料格式 | JSON / 任意檔案 |
| 查詢能力 | 無原生查詢，需搭配 D1 或外部 DB |
| 風險 | 需 Cloudflare 帳號，設定較複雜 |

---

### 方案 D｜git-based（資料進 repo）

**適用場景：** 最簡單，完全不依賴外部服務

| 項目 | 說明 |
|------|------|
| 費用 | 免費 |
| 方式 | Actions 執行後 `git commit docs/data/` 寫回 repo |
| 風險 | 每週多一個 commit，歷史記錄雜亂；大量資料會讓 repo 膨脹 |
| 注意 | 需要 `contents: write` 權限，weekly.yml 須調整 |

---

## 推薦執行路徑

```
現況（Artifacts）
    ↓ 近期
方案 D（git-based）  ← 最快實作，先確保資料不丟失
    ↓ 資料量達 ~50 週或需要查詢功能時
方案 A（Supabase）   ← 加 DB 層，前端仍讀 JSON
```

**理由：**
- 方案 D 改動最小（weekly.yml 加 3 行），立即解決 90 天到期問題
- 方案 A 等真的需要跨週查詢或統計時再做，避免過早工程化

---

## 方案 D 實作步驟（git-based，近期可做）

### 1. 調整 weekly.yml 權限

```yaml
permissions:
  contents: write   # 原本是 read，改為 write
  pages: write
  id-token: write
```

### 2. 在 `執行週報程式` 步驟後加 commit

```yaml
- name: 提交資料更新
  run: |
    git config user.name  "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add docs/data/
    git diff --staged --quiet || git commit -m "data: W$(date +%V) 週報資料 [skip ci]"
    git push
```

> `[skip ci]` 避免 push 後觸發二次 workflow。

### 3. weekly.yml 中移除 docs/data/ 的 .gitignore 排除

確認 `.gitignore` 不包含 `docs/data/`（目前應該沒有，但需確認）。

**預期效果：** 每週多一個 data commit，資料永久保留在 repo，不依賴 Artifacts。

---

## 方案 A 實作步驟（Supabase，未來做）

### 1. 建立 Supabase 專案

1. [supabase.com](https://supabase.com) 建立新專案
2. 執行上方 Schema SQL
3. 取得 `Project URL` 和 `anon key`

### 2. 新增 GitHub Secrets

| Secret 名稱 | 說明 |
|-------------|------|
| `SUPABASE_URL` | `https://xxxx.supabase.co` |
| `SUPABASE_KEY` | anon public key |

### 3. requirements.txt 加入

```
supabase==2.x.x
```

### 4. 新增 `storage.py`

```python
from supabase import create_client
import os

def get_client():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)

def upsert_articles(articles: list, week_id: str):
    client = get_client()
    rows = [
        {
            "week_id": week_id,
            "title": a["title"],
            "link": a["link"],
            "source": a["source"],
            "published": a.get("published", ""),
            "analysis": a.get("analysis", {}),
        }
        for a in articles
    ]
    client.table("articles").upsert(rows, on_conflict="link").execute()

def get_week(week_id: str) -> list:
    client = get_client()
    resp = client.table("articles").select("*").eq("week_id", week_id).execute()
    return resp.data
```

### 5. publisher.py 整合

在 `publish()` 中加一行：

```python
from storage import upsert_articles
upsert_articles(articles, week_id)
```

### 6. 防止免費 tier 暫停

在 weekly.yml 加一個每週 ping（或用 Supabase cron）：

```yaml
- name: Ping Supabase（防閒置暫停）
  run: curl -s "$SUPABASE_URL/rest/v1/" -H "apikey: $SUPABASE_KEY" > /dev/null
  env:
    SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
    SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
```

---

## 遷移時資料補齊

切換到新儲存方案時，需要把既有的 JSON 補入 DB：

```python
# 一次性執行腳本（本機跑）
import json, glob
from storage import upsert_articles

for path in sorted(glob.glob("docs/data/2026-W*.json")):
    data = json.load(open(path))
    upsert_articles(data["articles"], data["week_id"])
    print(f"匯入 {data['week_id']}：{data['article_count']} 篇")
```

---

## 決策紀錄

| 日期 | 決定 | 原因 |
|------|------|------|
| 2026-04-28 | 暫維持 Artifacts 方案 | 系統剛上線，優先穩定運作 |
| 2026-04-28 | 規劃方案 D → 方案 A 路徑 | 漸進遷移，避免過早複雜化 |
| — | （待填）方案 D 實作 | — |
| — | （待填）方案 A 實作 | — |