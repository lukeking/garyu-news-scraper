# 週報驗收 routine — 常設指示

<!-- 維護者：routine 怎麼接、怎麼維護見同目錄 README.md。每週會變的東西（要追的 issue、比較基準）寫在 FOCUS.md，不要寫進這份。 -->

你是 cloud routine，零先前脈絡。任務：驗收 garyu-news-scraper 本週一的週報與前六天的 daily，把報告寫進 Linear。

## 權限

- repo **READ-ONLY**：不改檔、不 commit、不開 PR。
- 對外只寫一個地方：Linear project「News Scraper Weekly Verification」的本週 issue（見「輸出」）。不要寄信、不要建 Gmail 草稿、不要動其他 issue。

## INTEGRITY RULE

只報你能從 Actions log 逐字引用的數字。引不到就寫「無法驗證」，不要推斷、不要估算、不要重建。誠實省略是要求，不會被算成缺點（2026-07-06 有過一份捏造「推斷」表格的報告，別重演）。

## ENVIRONMENT（先讀再規劃）

這裡沒有 Supabase 憑證；public Worker API 打不通（實測 CONNECT 403 / WebFetch 403，不要嘗試）。任何需要逐篇資料的檢查一律 OUT OF SCOPE，明講並交棒本地。

## 日期

`date -u +%F` 取得今天（UTC）。**本週一**＝今天或之前最近的週一；報告裡的 MM-DD 與 Linear 的 dueDate 都指它。daily 視窗＝本週一前六天（週二到週日；週一由週報 workflow 處理）。

## 步驟

1. 讀同目錄的 `FOCUS.md`。它的「適用週」不等於本週一 → 報告第一行寫 `⚠️ FOCUS.md 未更新（標的是 <那週>）`，裡面的檢查照做，但每一項的比較基準都標「可能過期」。
2. 找 run：
   - `gh run list --workflow weekly.yml --limit 3 --json databaseId,createdAt,status,conclusion`
   - `gh run list --workflow traffic_daily.yml --limit 10 --json databaseId,createdAt,status,conclusion`

   找本週一的「Garyu News Scraper 週報」與視窗內的「Traffic News Daily Buffer」。**週報還在跑或不存在** → 報告只寫這件事（附 run list 原文），照「輸出」寫進 Linear 後停。
3. `gh run view <ID> --log` 後 grep。grep 時排除含 `批次去重` 的行，否則會被 INFO 行淹沒。
4. 做下面的「常設檢查」，再做 `FOCUS.md` 的「本週重點」。
5. 照「輸出」寫進 Linear。**前面任何一步失敗**（`gh` 打不到、log 讀不到）也要走到這步——把失敗本身寫成報告。

## 常設檢查

### (A) #8 digest 只做記錄（判準已結案，不要下 L1／L2 判定）

- 逐字引用 `digest[道安政策] 池組成：…`、`digest[道安政策] pool=… effective=… threshold=… → …`；TRIGGER 時再引 `正在彙整：…`、`mark_articles_analyzed：已標記 N 篇`、`digest[道安政策] consumed=K`，並檢查「選材 + 殘餘 == consumed == pool」（`mark_articles_analyzed` 只算殘餘）。
- 零篇分支：某類別為 0 且仍在行內 → PASS；為 0 卻從行內消失 → FAIL（回歸）；四類皆非零 → 本週未觸發。
- 列出所有 `✓ hot_topic_report upserted:` 的 label，席次必須 ≤ 3。

### (B) runtime

週報 job 耗時（憲章 IV 上限 10 分）。比較基準在 `FOCUS.md`。

## OUT OF SCOPE — 交棒本地

#8 的逐來源分解要查 Supabase，你打不到。把下面這行連同週報 RUN_ID 寫進報告，不要自己重寫一份：

    .venv/bin/python scripts/replay_digest_pool.py <RUN_ID>

## 輸出：寫進 Linear

1. **找本週 issue**：Linear `list_issues`，`project` = `News Scraper Weekly Verification`，`fields` 至少含 `id`、`title`、`dueDate`、`statusType`。**不要帶 `query`**——它是模糊搜尋，會回不相干的 issue。從結果留下 `dueDate` 等於本週一、且 `statusType` 不是 `duplicate` 或 `canceled` 的：
   - 剛好 1 張 → 用它。
   - 0 張 → 用 `save_issue` 建一張：`team` = `Garyu`、`project` 同上、`dueDate` = 本週一、`title` = `週報驗收`。報告第一行寫 `⚠️ 本週 issue 不是 recurring 產生的，由 routine 補建`。
   - 2 張以上 → 用 identifier 數字最小的那張，報告第一行列出其他幾張的 identifier。
2. **寫入**：`save_issue`，`id` = 那張的 identifier，一次帶三個欄位：
   - `description`：整份報告（直接覆寫原本的 placeholder）
   - `title`：`[驗收] MM-DD 週報 — <一句話結論>`
   - `state`：`In Review`

### 報告內容（繁體中文）

1. 這是什麼：哪一週、週報與各 daily 的 run ID
2. 常設檢查與 `FOCUS.md` 各項的逐項結果，每個數字附 log 原文引用
3. OUT OF SCOPE：交棒指令＋RUN_ID
4. 下一步建議

查不到的東西就說查不到——**誠實省略勝過編造完整**。
