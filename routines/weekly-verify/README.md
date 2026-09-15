# 週報驗收 routine

每週一 07:00Z（台北 15:00）由 cloud routine 驗收當週週報，報告寫進 Linear project
「News Scraper Weekly Verification」的本週 issue。

| 檔案 | 讀者 | 內容 |
|---|---|---|
| `PROMPT.md` | routine | 常設指示：找 run、INTEGRITY、常設檢查、寫進 Linear |
| `FOCUS.md` | routine | 本週重點：要追的 issue 與比較基準，每週更新 |
| `README.md` | 人 | 本檔：routine 怎麼接、怎麼維護 |

routine 在執行時從 `main` 讀 `PROMPT.md` 與 `FOCUS.md`——**改它們＝改 routine 的行為，走 PR，且要在週一 07:00Z 前 merge。**

## 每週維護

讀完本週報告、把 issue 移 Done 之前，更新 `FOCUS.md`：改「適用週」、換比較基準、增刪要追的項目。
沒更新不會漏跑：routine 照舊版做，並在報告第一行標出 `FOCUS.md` 過期。

## 怎麼知道它沒跑

**週一晚上本週 issue 還停在 Todo ＝ routine 沒跑完。** routine 沒有自動重試，失敗也不保證會通知；
補救只有到 routine 頁面手動 Run now。

## routine 設定（重建用）

- ID：`trig_01CwfWU47Bh7w5r8NFKGQCED`
- cron：`0 7 * * 1`（UTC）
- model：`claude-sonnet-5`；tools：`Bash`、`Read`、`Grep`、`Glob`
- connector：Linear（只有這一個）
- repo：`lukeking/garyu-news-scraper`
- 開場 prompt（routine 物件裡只有這段，其餘都在 `PROMPT.md`）：

```text
你是 cloud routine，零先前脈絡。讀 repo 的 `routines/weekly-verify/PROMPT.md`，完整照做（它會叫你讀同目錄的 `FOCUS.md`）。

讀不到 PROMPT.md 時不要自己猜任務，只做這件事就停：用 Linear `list_issues`（`project` = `News Scraper Weekly Verification`，不要帶 `query`）找 `dueDate` 等於本週一（UTC，用 `date -u` 算）、`statusType` 不是 `duplicate` 或 `canceled` 的 issue，用 `save_issue` 把 `title` 改成 `[驗收] MM-DD 週報 — ⚠️ routine 讀不到 PROMPT.md`、`state` 改成 `In Review`，`description` 寫上 `ls routines/weekly-verify` 與 `git log -1 --format='%h %cI'` 的輸出。找不到 issue 就在最後一則訊息說明。
```
