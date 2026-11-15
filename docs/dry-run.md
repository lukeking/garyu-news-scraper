# 不發布的週報執行

`.github/workflows/weekly-dry-run.yml`：在正式執行環境（GitHub Actions、`production` environment、正式的資料庫與 LLM key）跑一次週報流程，
不寫入正式資料、不發布、不部署。行為的契約在 `specs/020-layered-acceptance/contracts/dry-run.md`，這份是操作說明。

## 它驗什麼，不驗什麼

- 驗的是接線與輸出：這個分支的程式在正式環境抓不抓得到輸入、過濾與入選的結果、分析的全文長什麼樣子、每條呼叫路徑讀到哪一組設定。
- 不是預演週一。它讀的是觸發當下的 buffer 與彙整池，跟週一排程那一刻不同；入選與報告換一個時間跑就會不一樣。
- 驗不到跨次執行的狀態（彙整池的已分析標記、指紋、buffer 過期、跨次去重）：這些要看連續兩次正式執行，不發布的執行自己也不寫它們。
- 驗不到排程本身有沒有觸發：只有真的排程事件能證明。

## 怎麼觸發

只能手動觸發，沒有排程。`level` 是必填的選項：

```bash
gh workflow run weekly-dry-run.yml --ref <要驗的分支> -f level=dry-input
gh workflow run weekly-dry-run.yml --ref <要驗的分支> -f level=dry-full
```

網頁上是 Actions → `Garyu News Scraper 不發布週報` → Run workflow，選分支與 `level`。

- 跑的是 `--ref` 那個分支的程式與那個分支的 workflow 檔，所以還沒 merge 的分支也能驗。
- workflow 檔要先在預設分支上才觸發得了（GitHub 的行為，這個 repo 的第一次實測是 spec 020 的 T021）。分支是在這個檔進 `main` 之前切的，先 merge `main` 再觸發。
- 次數沒有上限。第二級跟正式週報共用同一把 Gemini key 與同一個月預算（`docs/external-services.md` 的 Gemini 那一列），緊接在週一排程之前觸發可能讓正式那次碰到額度上限；每支程式結尾印出這次送出的呼叫次數。
- 跟正式的排程同時跑：兩個 workflow 沒有共用的 concurrency 設定，不發布的這次不會讓排程那次被取消或排隊；資料面只有讀。同時跑會讓計數對不上，見下面「比對不同時怎麼讀」。
- 成功結束不會連帶觸發 `auto-kb.yml`：那個檔的 `workflow_run` 只認 `Garyu News Scraper 週報` 這個名字。

## 兩級各做什麼

| | `dry-input`（第一級） | `dry-full`（第二級） |
|---|---|---|
| 收集、過濾、充實、入選 | 做 | 做 |
| 交通過濾階段的 embedding 去重 | 呼叫（它是入選的一部分） | 呼叫 |
| FFXIV 逐篇分析、三軸與彙整報告 | 不做：停在第一次生成式呼叫之前 | 做，全文寫進產物 |
| 每份報告跑一次 `check_report()` | 不做 | 做，命中寫進產物，標明未經逐條判定，不擋任何東西 |
| 術語收錄 | 不跑那一步 | 跑，用這次 FFXIV 的分析輸出當輸入，印出會寫入的條目，不寫術語庫 |
| 寫入資料庫（文章、buffer、報告、已分析標記、buffer 過期、術語庫） | 不寫，每一種略過各印一行 | 不寫，每一種略過各印一行 |
| 產生站台檔、部署兩個站 | 不做 | 不做 |

workflow 的步驟依序是：準備（跟 `weekly.yml` 逐步相同）→ 檢查 `level` → 計數（開始）→ `python main.py` → `python scripts/traffic_weekly_analysis.py` →
術語收錄（只有第二級）→ 計數（結束）→ 比對 → 上傳產物。檢查 `level` 那一步在值不是 `dry-input`、`dry-full` 時直接失敗：
程式把沒設或空的模式當成正式模式，而缺少必填輸入的觸發 GitHub 會不會擋下沒有實測，所以 workflow 自己擋，不讓空值變成一次正式寫入。
前面的程式步驟失敗時，後面的程式步驟照預設不跑；
計數（結束）、比對與上傳照跑：跑到一半死掉的那一次，最需要知道有沒有寫進任何東西。

## 讀執行紀錄

`gh run view <run id> --log`。每支程式的第一行標明是哪一級（`[不發布] 第一級：…`／`[不發布] 第二級：…`），
每一種被略過的寫入一行 `[不發布] 略過 <寫入函式的名字>：<N> 筆`，第一級停下的地方一行 `[不發布] 第一級在 <階段> 之前停下`，
每支程式結尾一行 `[不發布] 生成式 LLM 呼叫 <N> 次，embedding 呼叫 <M> 次`（第一級的 N 是 0）。
這幾行的完整清單在 contract 的「執行紀錄裡的固定行」。「略過了」有一行、「沒跑到那裡」沒有，兩者分得開。

## 產物

| 產物 | 哪一級 | 檔 |
|---|---|---|
| `ffxiv-pool` | 兩級 | `ffxiv_pool.json`：FFXIV 整個候選池與入選（跟正式週報的同名產物相同，只多了頂層的 `run_mode`） |
| `traffic-pool` | 兩級 | `collected.json`：逐來源的收集數與過濾後數、正式執行會寫進 buffer 的那些列；`selection.json`：選出的熱點 bucket、每個彙整類別的池（篇數、來源分布、入選）；`counts_before.json`、`counts_after.json`：前後兩份計數 |
| `analysis-output` | 第二級 | `ffxiv_articles.json`：FFXIV 逐篇分析全文；`traffic_reports.json`：每份三軸與彙整報告的全文與 `check_report()` 的命中；`auto_kb_entries.json`：術語收錄會寫入的條目 |

每個檔的頂層有 `run_mode`（`dry-input` 或 `dry-full`），寫明來自哪一級。目錄裡的檔名與 `TRAFFIC_POOL_DIR`、`ANALYSIS_OUTPUT_DIR` 兩個變數名是提案（contract）。
路徑變數沒設或寫不進去時，執行紀錄各有一行說明，不會靜靜少一個檔。

讀回：

```bash
gh run download <run id> -n traffic-pool -D dry-run-<run id>/traffic-pool
gh run download <run id> -n analysis-output -D dry-run-<run id>/analysis-output
gh run download <run id> -n ffxiv-pool -D dry-run-<run id>/ffxiv-pool
```

產物之後可以拿來重播。保留天數跟著 repo 的 Actions 設定，這個檔沒有另外設。
這個 repo 是公開的：執行紀錄與產物（含分析全文與入選清單）外人讀得到，這是已定可以的（spec 020 Clarifications，2026-11-15）。
「不發布」只保證不上站、不寫正式資料，不是不讓人讀到。

## 五個計數

`scripts/dry_run_counts.py` 在開頭與結尾各取一次（`take`），最後比對兩份（`compare`）；有任何一項不同或未取得，比對那一步失敗，job 跟著失敗。
它只發 GET。列數用 PostgREST 的 `Prefer: count=exact` 從回應的 `Content-Range` 總數取，不抓列，所以不受單次 1000 列的上限影響（BACKLOG `GNS-20261103-f71`）。
取不到的項目寫「未取得：原因」，不補值；未取得在比對時算沒有通過。

spec 的「五個計數」在這裡是七項：報告數沒寫是哪一張表，兩張都數；最後部署時間有兩個站。

| 項目 | 定義 | 請求 | 正式執行時會改它的寫入 |
|---|---|---|---|
| 報告數（`hot_topic_reports`） | 整張表的列數 | `GET /rest/v1/hot_topic_reports?select=id&limit=1` | 新的一份熱點或彙整報告 |
| 報告數（`articles`） | 整張表的列數 | `GET /rest/v1/articles?select=id&limit=1` | FFXIV 的文章、交通的新 buffer 列、buffer 過期刪除 |
| buffer 筆數 | `articles` 裡 `content_type=traffic`、`hot_topic_analyzed=false` 的列數，不看過期時間 | 上一列再加 `content_type=eq.traffic&hot_topic_analyzed=eq.false` | 新的 buffer 列、過期刪除、報告把文章標成已分析 |
| 彙整池未分析筆數 | buffer 筆數再限 `major_category` 在彙整類別裡：`pipeline_config` 的 `category_digest` 每一類加上它的 `include_categories` | 上一列再加 `major_category=in.(…)` | 同上，加上彙整的消耗（`mark_articles_analyzed`） |
| 術語庫條目數 | `knowledge_base` 整張表的列數 | `GET /rest/v1/knowledge_base?select=jp_term&limit=1` | 術語收錄寫入新條目 |
| 最後部署時間（`garyu-traffic-news`、`garyu-ffxiv-news`） | Cloudflare Pages 專案的 `latest_deployment.created_on`，不分 production 與 preview | `GET https://api.cloudflare.com/client/v4/accounts/<CLOUDFLARE_ACCOUNT_ID>/pages/projects/<專案名>` | 週報的兩個部署步驟、`deploy-pages-*.yml` |

- Supabase 的四張表用 `SUPABASE_SERVICE_ROLE_KEY`（沒有就用 `SUPABASE_KEY`）；部署時間用 `CLOUDFLARE_API_TOKEN` 與 `CLOUDFLARE_ACCOUNT_ID`，只讀，這個 workflow 沒有部署步驟。
- 部署時間的讀法照 Cloudflare 的 API 文件（Pages 的 Get project，讀 `result.latest_deployment.created_on`；需要 Pages Read 或 Pages Write 的權限），2026-11-15 讀的。
  現有的 token 有沒有這個權限、正式回應是不是這個形狀，第一次實跑（T021）才知道；取不到時那兩項寫「未取得：HTTP 403：…」之類的原因，比對不會通過。
- buffer 與彙整池刻意不看 `buffer_expires_at`：週報讀 buffer 時篩「還沒過期」，但一次執行十幾分鐘，跨過過期時間的列會讓計數在沒有任何寫入時就變。
  不篩的話，只有真的刪掉過期列才會改變計數，那正是要抓的寫入。所以這裡的 buffer 筆數比執行紀錄裡 `buffer 中有 N 篇待分析文章` 大，兩者本來就不相等。
- 彙整池這一項是所有彙整類別加起來的未分析列數，不分類別，也不扣掉分析當下排除的連結（`select_digest_pool` 的 `excluded_links`），
  所以不等於執行紀錄裡每個類別各自的池篇數。
- 計數抓不到既有的列被改寫（例如同一週的報告被覆蓋、某篇文章的內容被改）；那一半由 `tests/unit/test_storage_dry_run.py` 與 `tests/unit/test_auto_kb_dry_run.py` 守。

檔的格式（`take` 寫出的 JSON）：

```json
{"run_mode": "dry-input", "taken_at": "2026-11-16T05:00:00+00:00",
 "items": {"buffer": {"name": "buffer 筆數", "value": 760},
           "deploy_ffxiv": {"name": "最後部署時間（garyu-ffxiv-news）", "unavailable": "HTTP 403：…"}}}
```

每一項剛好有 `value` 或 `unavailable` 其中一個。`compare` 逐項印一行，最後一行一定是 `[計數比對] 結果：…`：全部相同、不同與未取得各是哪幾項，或檔案找不到、不是 JSON、形狀不對而沒有比對。
本機也能跑（會載入 `.env`，只讀）：`--help` 有完整的呼叫方式與結束碼。

### 比對不同時怎麼讀

先看是哪幾項、往哪個方向變，再看兩份計數的 `taken_at` 之間有沒有別的 workflow 在跑：

```bash
gh run list --workflow traffic_daily.yml --limit 5 --json databaseId,createdAt,updatedAt,conclusion
gh run list --workflow weekly.yml --limit 3 --json databaseId,createdAt,updatedAt,conclusion
gh run list --workflow auto-kb.yml --limit 3 --json databaseId,createdAt,updatedAt,conclusion
```

- 只有 `articles`、buffer 筆數（可能連彙整池）變多，而 `traffic_daily.yml` 的某一次跟這段時間重疊：多半是每日的交通執行寫進來的（它只新增 buffer 列，不刪、不標已分析）。
  cron 寫 00:00Z，實際起跑常晚幾個小時，所以要看 run 的 `createdAt`、`updatedAt`，不看 cron。避開那段時間重跑一次，兩份相同才算通過。
- 只有部署時間變了：這一項不分 production 與 preview，而 push 到 PR 分支時 Cloudflare Pages 會自己建一次部署
  （2026-11-15 `#225` 的 `f0fd1ef` 上有 `Cloudflare Pages: garyu-traffic-news`、`Cloudflare Pages: garyu-ffxiv-news` 兩項 check；同一天 `main` 的 `6551186` 上沒有，
  別種分支會不會建沒有查）。先看兩份計數的 `taken_at` 之間有沒有 commit 帶這兩項 check：`gh pr checks <PR>` 或
  `gh api "repos/{owner}/{repo}/commits/<sha>/check-runs" --jq '.check_runs[] | "\(.name) \(.started_at)"'`。有的話避開重跑一次。
- 報告數（`hot_topic_reports`）、術語庫變了，buffer 與彙整池變少，或部署時間變了而那段時間沒有 push：每日的交通執行改不到這些。
  先看同一段時間有沒有正式週報、`auto-kb.yml` 或 `deploy-pages-*.yml` 在跑；都沒有，就是這次不發布的執行寫進了東西，先停用、查是哪一個寫入沒有檢查模式。
- 未取得：照那一行的原因處理（金鑰沒設、權限不夠、回應形狀不對），修好再跑一次；未取得的項目不能當成相同。

## 跟 `weekly.yml` 保持一致

`tests/unit/test_workflow_parity.py` 比對：準備步驟逐步相同；程式步驟的 env 鍵與值跟 `weekly.yml`（術語收錄那一步跟 `auto-kb.yml`）相同，
多的只能是 `GARYU_RUN_MODE` 與產物路徑；`timeout-minutes`、`environment`、`permissions` 相同；沒有排程、沒有部署、沒有讀回驗證那一步。
改 `weekly.yml` 或 `auto-kb.yml`（例如加一個模型變數）時，這條測試會指出這個檔要跟著改哪裡。
