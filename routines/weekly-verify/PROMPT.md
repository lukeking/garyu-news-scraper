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

`date -u +%F` 取得今天（UTC）。**本週一**＝今天或之前最近的週一；報告裡的 MM-DD 與 Linear 的 dueDate 都指它。daily 視窗＝本週一前六天（週二到週日；週一由交通那一支週報處理）。

## 步驟

1. 讀同目錄的 `FOCUS.md`。它的「適用週」不等於本週一 → 報告第一行寫 `⚠️ FOCUS.md 未更新（標的是 <那週>）`，裡面的檢查照做，但每一項的比較基準都標「可能過期」。
2. 找 run：
   - `gh run list --workflow weekly-traffic.yml --limit 3 --json databaseId,createdAt,status,conclusion`
   - `gh run list --workflow weekly-ffxiv.yml --limit 3 --json databaseId,createdAt,status,conclusion`
   - `gh run list --workflow traffic_daily.yml --limit 15 --json databaseId,createdAt,status,conclusion`（routine 週四跑，週一之後的 daily 也會列在前面）

   找本週一的「Garyu News Scraper 週報（交通）」與「Garyu News Scraper 週報（FFXIV）」各一個，加上視窗內的「Traffic News Daily Buffer」。
   週報是兩支 workflow，各跑一類、各有自己的 run 與 log（2026-11-23 那一週起；之前是單一支 `weekly.yml`，已刪）。
   - **兩支都沒有跑完的 run**（各自還在跑或不存在，兩支的狀態不必相同） → 報告只寫這件事（附 run list 原文），照「輸出」寫進 Linear 後停。
   - **只有一支還在跑或不存在** → 報告第一行寫 `⚠️ 週報（<交通或 FFXIV>）還在跑／不存在`，附那一支的 run list 原文；另一支與各 daily 的檢查照做。
     要讀缺的那一支 log 的檢查，逐項寫「沒檢查到（那一支沒有 log）」，不寫成通過。
   - **任一支的 `conclusion` 不是 `success`** → 不停。`gh run view <ID> --json jobs` 列出 `conclusion` 不是 `success` 的步驟，寫在報告最前面；那一支的 log 照讀、檢查照做。
     交通那一支只有最後一步「驗證本週資料可由 Supabase 讀取」失敗時，熱點分析與部署已經跑完：那一步排在部署之後，只把 run 標紅。
     這時逐字引用 `✓ traffic buffer upsert 完成：` 那行、`所有 category 均無文章` 那行與 `[traffic] 處理失敗：` 開頭的行（有哪幾行引哪幾行，都沒有就寫沒有），
     再逐字引用驗證那一步自己最後的錯誤行。錯誤行說的是讀不到本週的交通資料（`尚未讀到本週 traffic 資料`）→ 照前面引到的行寫出是週一沒有新的交通列，還是收集失敗。
     是別的錯誤（HTTP 錯誤、逾時、金鑰未設定）→ 寫「驗證那一步自己失敗」並引那一行，不歸到前兩種。引到的行分不出是哪一種 → 寫「無法驗證」。
3. 每個 run 各自 `gh run view <ID> --log` 後 grep。grep 時排除含 `批次去重` 的行，否則會被 INFO 行淹沒。
   交通的檢查讀交通那一支的 log，FFXIV 的檢查讀 FFXIV 那一支的；`FOCUS.md` 每一節寫了讀哪一支，沒寫的兩支都讀。
4. 做下面的「常設檢查」，再做 `FOCUS.md` 的「本週重點」。
5. 照「輸出」寫進 Linear。**前面任何一步失敗**（`gh` 打不到、log 讀不到）也要走到這步——把失敗本身寫成報告。

## 常設檢查

### (A) digest：記錄，並判定 L1 常設 reopen 條件（L2 只記錄；BACKLOG `GNS-20261019-dkm`）

讀交通那一支的 log（下面這些行都在「週交通熱點分析」那一步）。

- 逐字引用 `digest[道安政策] 池組成：…`、`digest[道安政策] pool=… effective=… threshold=… → …`；TRIGGER 時再引 `正在彙整：…`、`mark_articles_analyzed：已標記 N 篇`、`digest[道安政策] consumed=K`，並檢查「選材 + 殘餘 == consumed == pool」（`mark_articles_analyzed` 只算殘餘）。
- 逐字引用 `digest[道安政策] 最大來源：… 抽掉最大剩 N`。N 小於 pool 那行的 `threshold` → 本週 L1 ❌，否則 ✅。**這行不存在 → FAIL**：它是 `GNS-20261019-dkm` 常設 reopen 條件唯一的執行者。
- 同一行括號裡的佔比 ≤ 50% → 本週 L2 ✅，否則 ❌。只記錄，不觸發任何動作（spec 014 SC-001 L2，由 BACKLOG 那一列逐週記）。
- 拿 `FOCUS.md`「L1 前兩週」的兩個值加上本週，判定常設 reopen 條件（任意連續三週裡 L1 有兩週 ❌ → 開 spec 補來源，出處 `specs/BACKLOG.md` `GNS-20261019-dkm` 節的「重開條件」）：
  - **觸發** → 報告第一行寫 `⚠️ GNS-20261019-dkm reopen 條件觸發`，列出三週的值。
  - **未觸發** → 在本節寫一行「未觸發（前兩週 ✅／❌、本週 ✅／❌）」。
- 零篇分支：某類別為 0 且仍在行內 → PASS；為 0 卻從行內消失 → FAIL（回歸）；四類皆非零 → 本週未觸發。
- 列出所有 `✓ hot_topic_report upserted:` 的 label，席次必須 ≤ 3。

### (B) runtime

兩支週報 job 各自的耗時。比較基準在 `FOCUS.md`。憲章 IV（1.3.0 起）沒有單次 10 分的上限了，上限是各自 workflow 檔裡的 `timeout-minutes`
（`.github/workflows/weekly-traffic.yml`、`weekly-ffxiv.yml`；2026-11-17 是 25 與 30）：
job 耗時達到自己那一支的上限、且 run 沒有成功結束（被 timeout 砍掉）→ FAIL；其餘只跟比較基準比，不判 FAIL。

## OUT OF SCOPE — 交棒本地

#8 的逐來源分解要查 Supabase，你打不到。把下面這行連同交通那一支的 RUN_ID 寫進報告（彙整池的紀錄在那一支的 log 裡），不要自己重寫一份：

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
3. **寫不進去，或你判斷不該寫**：用 `PushNotification` 說明卡在哪一步、錯誤原文或你的理由。不然使用者要到週四晚上看到 issue 還停在 Todo 才會知道。

### 報告內容（繁體中文）

1. 這是什麼：哪一週、兩支週報與各 daily 的 run ID
2. 常設檢查與 `FOCUS.md` 各項的逐項結果，每個數字附 log 原文引用
3. OUT OF SCOPE：交棒指令＋RUN_ID
4. 下一步建議

查不到的東西就說查不到——**誠實省略勝過編造完整**。
