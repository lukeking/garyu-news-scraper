# Evaluation: 分層驗收（spec 020）

片 1 的實跑（tasks.md Phase 4，T021 起）。片 1（`#225`）2026-11-16 進 `main`，這裡記的是它在正式執行環境第一次被觸發的結果。
沒有另外標明的都是實測。

## 觸發這件事本身（T021 之前量的）

**時間**：2026-11-16（UTC）。對象都是 `main` 的 `5dfff91`。

- **不帶 `level` 觸發**（13:19:54Z，`gh workflow run weekly-dry-run.yml --ref main`）：GitHub 直接拒絕，
  `HTTP 422: Required input 'level' not provided`，沒有產生 run。所以缺少必填輸入的觸發到不了 workflow 裡「檢查 level」那一步。
  選項以外的值（例如 `-f level=formal`）會不會同樣被拒絕，沒有量。
- **workflow 檔進預設分支之後觸發得了**：兩次帶 `level=dry-input` 的觸發都建立了 run。「進預設分支之前觸發不了」那一半沒有量（檔已經在 `main`）。
- **第一次觸發的 run 卡了 40 分鐘才起跑**：run `43874777760`，13:20:10Z 建立，停在 `queued`、0 個 job、`updated_at` 沒動。
  - 卡住期間三種取消都不成立：`gh run cancel` 回 `Cannot cancel a workflow run that is completed`；
    force-cancel 的 API 回 409 `Cannot cancel a workflow run that has not been queued yet`；網頁上的取消回 `Failed to cancel workflow.`。
  - 同一段時間 `production` environment 沒有保護規則、沒有待核准的部署，workflow 沒有 concurrency 設定，repo 沒有別的 run 在跑。
    GitHub 狀態頁的 Actions 是 operational；Pull Requests 是 degraded（merge 逾時，11:59Z 起）。
  - 14:00:24Z 它自己起跑，跟下面那一次重疊 49 秒；14:01 取消成功，停在「執行週報程式（不發布）」（cancelled），後面的步驟都是 skipped。
  - 成因沒查到。排除不了的一點：這次觸發在被 422 拒絕的那一次之後 14 秒。同一個檔、同一個 commit、同一個輸入在 13:58:18Z 重新觸發，6 秒起跑。

## 第一級（T021）：run `43880951609`

**來源**：`gh run view 43880951609 --log`（比對前剝掉全部 CSI 控制碼與時間戳）；
`gh run download 43880951609 -n traffic-pool`、`-n ffxiv-pool`。`analysis-output` 這一級沒有，下載回 `no artifact matches`，符合 contract。

13:58:20Z 建立，14:01:13Z 結束，結論 success。「執行週報程式（不發布）」2 分 15 秒，「週交通熱點分析（不發布）」5 秒。

### 固定行

```text
執行週報程式（不發布）
[不發布] 第一級：只到入選，不呼叫生成式 LLM
[不發布] 略過 upsert_traffic_buffer：19 筆
[不發布] 第一級在 FFXIV 分析 之前停下
[不發布] 生成式 LLM 呼叫 0 次，embedding 呼叫 55 次

週交通熱點分析（不發布）
[不發布] 第一級：只到入選，不呼叫生成式 LLM
[不發布] 略過 expire_buffer_articles：沒有查資料庫，筆數未知
[不發布] 分析的輸入：buffer 642 篇，加上這次收集的 19 篇（其中 0 篇 buffer 裡已經有）
[不發布] 生成式 LLM 呼叫 0 次，embedding 呼叫 0 次
```

- SC-002 的第一級那一半成立：兩支程式的生成式呼叫都是 0 次；embedding 55 次都在「執行週報程式」那一步，交通分析那一步是 0 次。
- 交通分析沒有 `第一級在 … 之前停下` 那一行：這一次沒有任何 bucket 通過 novelty gate，彙整池也沒到門檻，程式沒有走到會呼叫生成式 LLM 的地方。
  「沒跑到那裡」不印行，跟 contract 一致；所以第一級在交通分析裡停下的那一行，這一次沒有被實跑驗到。
- 兩支程式的 log 前綴不同（`main.py` 是 `YYYY-MM-DD HH:MM:SS,mmm [INFO] `，交通分析是 `YYYY-MM-DDTHH:MM:SS INFO <logger>: `）；
  用行首比對 `[不發布]` 的讀法要先剝掉兩種前綴，否則交通分析那四行會被漏掉。

### 計數（SC-001 的第一級那一半）

`counts_before.json` 取於 13:58:41Z，`counts_after.json` 取於 14:01:05Z；七項都取得，比對那一步印 `[計數比對] 結果：7 項都相同`。

| 項目 | 前 | 後 |
|---|---|---|
| 報告數（`hot_topic_reports`） | 58 | 58 |
| 報告數（`articles`） | 2350 | 2350 |
| buffer 筆數 | 678 | 678 |
| 彙整池未分析筆數 | 0 | 0 |
| 術語庫條目數 | 222 | 222 |
| 最後部署時間（`garyu-traffic-news`） | `2026-11-16T13:06:38.654151Z` | 同左 |
| 最後部署時間（`garyu-ffxiv-news`） | `2026-11-16T13:06:38.654151Z` | 同左 |

- 現有的 Cloudflare token 讀得到 Pages 專案，回應有 `result.latest_deployment.created_on`。
- 兩個站的部署時間到微秒都相同，比 `#228` 的 merge（13:06:36Z）晚 2 秒。merge 到 `main` 會讓兩個專案各建一次部署這一點對得上；
  但兩次請求是分開發的，值卻完全相同，是兩個專案真的共用同一個事件時間，還是別的原因，沒有驗。
  本機的 `.env` 沒有 Cloudflare 的金鑰，查不了。能定案的：兩個專案 `latest_deployment` 的 id 各是什麼（Cloudflare 的 dashboard，或計數多印一欄 id）。
- 彙整池這一項讀到 0。11-16 的排程週報發布過一份彙整，池被標成已分析，0 說得通；但 0 分不出「真的沒有」與「`major_category=in.(…)` 的寫法比不中任何列」。
  要一次讀到非 0 才能定案（之後幾天 daily 收進彙整類別的文章之後再取一次）。`limit=1` 配 `count=exact` 在另外四項讀到的都是整張表的總數，
  結果是空的那一種也讀得回 0，不是「未取得」。
- buffer 筆數 678 比執行紀錄的 `buffer 642 篇` 大，符合 `docs/dry-run.md` 的說明（計數不看過期時間）。
- 重疊的那 49 秒裡另一個 run 也是第一級、不寫入，比對沒有受影響。

### 交通：收集、過濾與入選

25 個來源，`來源失敗：0/25`。收集 277 筆，留下 19 筆（正式執行會寫進 buffer 的就是這 19 筆，這次是 `略過 upsert_traffic_buffer：19 筆`）。

| 來源 | 收集 | 新鮮度後 | 關鍵字後 | 來源封鎖後 | 批次去重後 | 向量去重後 | 留下 | 留下且屬彙整匯流的類別（`kept_in_confluence`） |
|---|---|---|---|---|---|---|---|---|
| Google News 機車交通 | 9 | 6 | 6 | 5 | 5 | 1 | 1 | 0 |
| Google News 重機 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 白牌機車 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 機車法規 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News Gogoro | 3 | 2 | 1 | 0 | 0 | 0 | 0 | 0 |
| Google News 機車路權 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 機車事故 | 1 | 1 | 1 | 1 | 1 | 1 | 1 | 0 |
| Google News 紅黃牌重機 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 中時新聞網 | 100 | 96 | 8 | 7 | 7 | 4 | 4 | 0 |
| Google News 道安統計 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 行人地獄 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| Google News 科技執法 | 14 | 10 | 10 | 8 | 7 | 3 | 3 | 3 |
| Google News 道安會報 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 交通安全基本法 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News Vision Zero | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 交通部 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 交通安全教育 | 12 | 10 | 10 | 10 | 10 | 4 | 4 | 4 |
| Google News 處罰條例 | 17 | 10 | 8 | 6 | 6 | 1 | 1 | 0 |
| Google News 禁行機車 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| Google News 機車待轉 | 2 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| Google News 停讓行人 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| UDN 聯合報 | 100 | 94 | 25 | 20 | 18 | 4 | 4 | 0 |
| Google News 交通部道安 | 3 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| Google News 高齡換照 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| Google News 人本交通 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 合計 | 277 | 235 | 74 | 59 | 55 | 19 | 19 | 8 |

- 留下的 19 筆依類別：機車事故 5、道安政策 5、科技執法 3、路口安全 2、未分類 4。
- 充實：`GN 充實：19 篇中 19 還原連結、15 補摘要、18 補圖、16 用媒體頁日期、0 失敗`。
- 熱點：通過 novelty gate 的 topic 是 0 個（`selection.json` 的 `hot_topics` 是空的）。
- 彙整（道安政策）：池 8 篇（道安政策 5、科技執法 3），有效 8，門檻 10，這一次不分析（`selected_for_analysis: false`）。
  來源是 Google News 交通安全教育 4、Google News 科技執法 3、Google News 交通部道安 1。這 8 篇都是這次收集、被疊上去的；資料庫裡的彙整池是 0。

### FFXIV：候選池與入選

11 個來源，`來源失敗：0/11`。候選池 9 篇，入選 9 篇：FFXIV JP Forum - DPS 3、FFXIV JP Forum - TANK 2、FFXIV EN Forum - Other Battle Systems 2、
FFXIV JP Forum - HEALER 1、FFXIV EN Forum - Healer Roles 1。最新的一篇發表於 11-13 22:35Z，最舊的 11-09 11:33Z。

### 這一次沒有驗到的

`#225` 內文「沒驗、要等第一次實跑」那幾項裡，第一級碰不到或這一次剛好沒走到的：

- 第一級在交通分析裡停下的那一行（上面「固定行」）。
- 彙整池計數的 `in.(…)` 寫法、兩個站部署時間為什麼相同（上面「計數」）。
- 資料庫讀回的 `published` 是不是 UTC 的 ISO 字串：這一次疊上去的 19 篇裡 `其中 0 篇 buffer 裡已經有`，對照沒有被用到。
- link 已在資料庫、但不在這次讀到的 buffer 裡的收集列會不會被疊上去：同上，沒有出現這種列。
- 第二級才有的幾項（報告全文、`check_report()` 的命中、術語收錄的條目與修補篇數、Gemini 的用量）：T022。

對第二級的影響：觸發當下沒有 topic 通過 novelty gate、彙整池沒到門檻，這時候跑第二級不會產生任何交通報告，
三軸與彙整兩條呼叫路徑不會被走到；T022 的「每份報告的全文」與 T023 要記的四條路徑裡的這兩條，要挑池子夠的時候觸發才驗得到。

## 第二級（T022）：run `43882293476`，FFXIV 與術語收錄那一半

**來源**：`gh run view 43882293476 --log`；`gh run download 43882293476 -n traffic-pool`、`-n ffxiv-pool`、`-n analysis-output`。

2026-11-16 14:06:23Z 建立（14:06:21Z 觸發，幾秒內分到 job），14:12:50Z 結束，結論 success。
「執行週報程式（不發布）」5 分 35 秒，「週交通熱點分析（不發布）」5 秒，「術語收錄（不寫入，只有第二級）」17 秒。

T022 還沒做完：這一次沒有任何交通報告（見「這一次第二級沒有走到的」），交通報告那一半要另外挑池子夠的時候再觸發一次。

### 固定行

```text
執行週報程式（不發布）
[不發布] 第二級：呼叫 LLM，不寫入、不發布
[不發布] 略過 upsert_traffic_buffer：19 筆
[不發布] 略過 站台檔 pages/ffxiv：9 筆
[不發布] 略過 upsert_articles：9 筆
[不發布] 生成式 LLM 呼叫 9 次，embedding 呼叫 55 次

週交通熱點分析（不發布）
[不發布] 第二級：呼叫 LLM，不寫入、不發布
[不發布] 略過 expire_buffer_articles：沒有查資料庫，筆數未知
[不發布] 分析的輸入：buffer 642 篇，加上這次收集的 19 篇（其中 0 篇 buffer 裡已經有）
[不發布] 生成式 LLM 呼叫 0 次，embedding 呼叫 0 次

術語收錄（不寫入，只有第二級）
[不發布] 第二級：呼叫 LLM，不寫入、不發布
[不發布] 術語收錄的輸入：analysis-output/ffxiv_articles.json 的 9 篇，其中 3 篇帶標記
[不發布] 術語收錄：會寫入 2 條，沒有寫入
[不發布] 略過 articles 的內聯修補：2 筆
[不發布] 生成式 LLM 呼叫 1 次，embedding 呼叫 0 次
```

三支程式的 log 前綴是三種（術語收錄是 `INFO `／`WARNING ` 開頭，沒有時間）；用行首比對固定行的讀法三種都要剝。

### 計數（SC-001 的第二級那一半）

`counts_before.json` 取於 14:06:40Z，`counts_after.json` 取於 14:12:41Z；七項都取得，值跟第一級那一次完全相同
（58／2350／678／0／222／兩個站都是 `2026-11-16T13:06:38.654151Z`），比對印 `[計數比對] 結果：7 項都相同`。
術語庫條目數在術語收錄跑過之後仍是 222。

### FFXIV 逐篇分析與術語收錄（SC-002 的第二級那一半）

- 候選池 9 篇、入選 9 篇，跟第一級那一次相同。`=== 開始 AI 分析，模型尾段=flash，maxOutputTokens=8192，共 9 篇（間隔 6s，預估 0.9 分鐘）===`，9 篇都是 `✓ 分析完成`。
- `analysis-output/ffxiv_articles.json`：`run_mode` 是 `dry-full`，9 篇，每一篇的 `analysis` 都讀得回來（轉成 JSON 字串 436～570 個字元），其中 3 篇帶 `[[` 標記，跟術語收錄讀到的「3 篇帶標記」一致。
- `main.py` 結尾的 KB MISS 清單 8 個詞（6 個帶標記、2 個未標記）；術語收錄發現未知術語 6 個，會寫入 2 條，4 個仍待審查。
- `analysis-output/auto_kb_entries.json`：`entry_count` 2。會寫入的兩條是 `三連魔 → 三連詠唱`（Triplecast，技能）與 `ペット → 寵物`（Pet，系統），都是 `auto_generated: true`；譯名對不對沒有判讀。
- 術語修補篇數這一次是 2 筆，只含這次輸出裡帶標記的文章；正式執行修補的是資料庫裡所有帶標記的 FFXIV 列（`#225` 內文的已知差異，沒有另外量）。

### Gemini 的用量（spec 的假設「第二級與正式執行共用額度不會讓正式週報額度不足」）

- 這一次送出的請求：生成式 10 次（FFXIV 逐篇 9、術語收錄 1、交通分析 0），embedding 55 次。重試也算在內，沒有看到重試的行。
- 執行紀錄不印 token 數與金額，所以這一次花了多少、佔 `docs/external-services.md` 的月預算（NT$300）多少，從紀錄算不出來。
- `docs/external-services.md` 寫的「每次大約多一份週報的用量」：就請求數來說，這一次不超過一份正式週報（少了交通報告那幾次）。
  這是用請求數推的，不是量到的金額；能定案的是 AI Studio 上那個 project 在觸發前後的花費。假設還沒有被實測到。

### 這一次第二級沒有走到的

- 交通報告：通過 novelty gate 的 topic 0 個，彙整池 8 篇（門檻 10）。三軸與彙整都沒有呼叫，`analysis-output` 裡沒有 `traffic_reports.json`，
  `check_report()` 一次都沒有跑。所以「每份報告的全文讀不讀得回來」與「`check_report()` 的命中」沒有驗到。
- 沒有報告時 `traffic_reports.json` 不產生，執行紀錄也沒有一行寫「沒有報告，不寫這個檔」；讀的人要從 `無 bucket 達到 min_threshold，跳過本週熱點發布`
  與 `selection.json` 推回來。要不要補一行，未定。
- 第一級那一節列的幾項（彙整池計數的 `in.(…)`、兩個站部署時間相同、`published` 的格式、不在 buffer 裡的既有 link）這一次同樣沒有碰到。

什麼時候補：彙整池要資料庫裡有彙整類別的未分析列加上當次收集的，合計到 10；11-16 的排程週報剛消耗過，預期要幾天的 daily 之後。
三軸要有 topic 通過 novelty gate，11-16 的排程週報與今天兩次都沒有，哪一天會有不知道。
