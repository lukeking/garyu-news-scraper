# Research: 分層驗收（spec 020）

2026-11-15。每個決定寫：選了什麼、為什麼、比過哪些做法。「沿用既有的做法」也算決定，同樣列替代方案。
分數是 1–5 分（5 最好）乘權重；每一格的證據等級標在表下。硬門檻（Gate）跟加權分數分開看：過不了 Gate 的做法不看分數。

## 現況（2026-11-15 讀 code）

**週報流程會寫入與發布的地方**（不發布的執行要擋的全部）：

| 位置 | 做什麼 |
|---|---|
| `src/pipeline/traffic.py:247` | `upsert_traffic_buffer`：這次收集的交通文章寫進 buffer |
| `src/publisher.py:125` | `upsert_articles`：FFXIV 的分析結果寫進 `articles` |
| `scripts/traffic_weekly_analysis.py:65` | `expire_buffer_articles`：清過期的 buffer |
| `scripts/traffic_weekly_analysis.py:191`、`:235` | `upsert_hot_topic_report`：三軸報告與彙整報告 |
| `scripts/traffic_weekly_analysis.py:248` | `mark_articles_analyzed`：彙整池標成已分析 |
| `scripts/auto_kb.py:264`、`:321` | 直接用 client 寫 `knowledge_base`、改 `articles.analysis`（不經 `src/storage.py`） |
| `.github/workflows/weekly.yml:157`、`:167` | 部署兩個 Pages |
| `.github/workflows/auto-kb.yml:4–6` | 週報 workflow 成功結束就連帶觸發，手動觸發的也算 |

`src/storage.py` 的寫入函式只有 5 個（`upsert_articles`、`upsert_traffic_buffer`、`expire_buffer_articles`、`mark_articles_analyzed`、`upsert_hot_topic_report`），
`src/`、`scripts/` 裡正式流程的呼叫點就是上表那幾處（`grep` 排除量測與重播用的腳本）。

**週報與每日走同一段交通輸入**：每日的 `scripts/traffic_buffer.py:39–69` 是 `collect → filter → prefetch → publish`；週報的 `main.py:39–45` 是
`collect → filter → analyze → publish`，而交通的 `analyze` 就是 `prefetch`（`src/pipeline/traffic.py:225–229`）。spec 的那條 Unchecked 假設因此成立。

**交通分析讀的是 buffer，不是這次收集的結果**：正式執行時 `main.py` 先把這次收集的寫進 buffer，下一步 `traffic_weekly_analysis.py` 才讀 buffer。
不發布的執行不寫 buffer，所以分析那一步讀不到這次收集的文章，除非另外帶過去。

**一次週報用多少 LLM**：11-09 的排程執行（run `42556081408`，10.5 分鐘）log 裡 `✓ 分析完成` 20 行（FFXIV 逐篇 20 次）；三軸、彙整與發布前檢查的呼叫次數從 log 的行數對不出來，沒有數。
第二級一次大約是一份週報的用量；確切數字要等 FR-009 把呼叫次數印出來。Gemini 的預算記在 `docs/external-services.md`（Tier 1，上限 NT$300／月）。

## D1 寫入怎麼擋

**Decision**（已定 2026-11-15）：程式裡一個執行模式，寫入函式自己檢查；不發布時不呼叫資料庫、印一行略過了什麼、回傳 0。`auto_kb.py` 的兩處寫入同樣處理。
另加一條測試：列出 `src/storage.py` 所有寫入函式，逐一斷言不發布模式下資料庫 client 被呼叫 0 次；新增寫入函式而沒有檢查，這條測試會紅。

**Rationale**：寫入點集中（5 個函式加 2 處），在出口擋比在每個呼叫端擋少漏；輸入照樣讀正式資料，保真度最高。

**Alternatives considered**：

| 做法 | Gate：正式寫入 0 筆 | 保證強度 ×0.4 | 輸入保真 ×0.25 | 成本 ×0.25 | 外部設定 ×0.1 | 加權 |
|---|---|---|---|---|---|---|
| 程式裡的執行模式（選這個） | 過（靠測試；SC-001 實測） | 3 | 5 | 4 | 5 | 3.95 |
| 不發布的執行只拿唯讀的資料庫金鑰 | 未知：唯讀金鑰下讀不讀得到 buffer、寫入會不會出聲，沒查 | 5 | 4 | 2 | 1 | 3.60 |
| 寫進另一個資料庫 | 過 | 4 | 2 | 1 | 1 | 2.45 |

證據等級：各格都是判斷，沒有實測。唯讀金鑰之後可以當加固再加，不在這個 spec。

## D2 入口放哪

**Decision**（已定 2026-11-15）：另開一個只能手動觸發的 workflow 檔，`weekly.yml` 不動。兩個檔共用的準備步驟（寫設定檔、裝 Python、裝相依）用一條測試比對，走樣就紅。

**Rationale**：`auto-kb.yml` 認的是週報 workflow 的名字，另一個檔不會連帶觸發它，FR-004 靠結構成立；正式排程的檔一行都不改，FR-010 靠 diff 就看得出來。
`weekly.yml` 有 `GNS-20261013-4g9`（週報拆成兩個 workflow）的編輯前提醒，這個做法不碰它；之後真的拆的時候，比對的測試會指出不發布的檔要跟著改。

**Alternatives considered**：

| 做法 | Gate：不連帶觸發會寫入的術語收錄 | Gate：正式排程不變 | 跟正式流程走樣 ×0.35 | 正式流程的改動風險 ×0.35 | 維護 ×0.2 | 跟 `4g9` 相容 ×0.1 | 加權 |
|---|---|---|---|---|---|---|---|
| 另一個 workflow 檔＋比對測試（選這個） | 過（結構上；SC-001 實測） | 過（不改檔） | 4 | 5 | 3 | 4 | 4.15 |
| `weekly.yml` 加手動觸發的輸入 | 未知：`auto-kb.yml` 要靠事件內容分辨，哪個欄位可靠沒查 | 要靠 SC-006 讀回 | 5 | 2 | 4 | 2 | 3.45 |
| 抽成可重用的 workflow，兩個入口都呼叫它 | 過（推論） | 改最多 | 5 | 1 | 4 | 3 | 3.20 |

證據等級：各格都是判斷。新的 workflow 檔要先進預設分支才觸發得了（GitHub 的行為，沒有在這個 repo 實測）；之後可以選任一個分支跑那個分支的版本。

## D3 兩級各停在哪、留下什麼

**Decision**（提案，未定；細節交給 tasks）：

- 第一級：`main.py` 跑到過濾與充實完、不呼叫 FFXIV 的分析；交通分析那一步跑到選出熱點 bucket 與彙整池為止。留下：FFXIV 候選池（沿用現有的 `ffxiv-pool` 產物）、交通這次收集過濾後的清單、熱點與彙整池的組成。
- 第二級：全部跑完，含發布前檢查；留下第一級的全部，加每一份報告與 FFXIV 逐篇分析的全文、LLM 呼叫次數。

**Alternatives considered**：產物放別處（commit 到分支、資料庫的儲存空間）——不採用，執行紀錄與產物已定夠用（spec Clarifications）。

## D4 交通分析的輸入要不要帶上這次收集的文章

**Decision**（已定 2026-11-15）：要。`main.py` 把這次收集過濾後的交通文章寫成檔，分析那一步在不發布模式下讀 buffer 再疊上這個檔，讓輸入跟正式執行同一刻會讀到的一致。

**Rationale**：改動如果在收集或過濾（新來源、新的過濾條件），它對分析的影響只有疊上去才看得到。

**Alternatives considered**：不疊、只印少算了幾篇——省一段程式，但「必要的輸入」改動的輸出片就驗不到。過期的 buffer 在不發布模式下不清，分析讀 buffer 時本來就照週數篩，影響要在實作時量一次。

## D5 術語收錄怎麼涵蓋

**Decision**（已定 2026-11-15）：放在不發布 workflow 的最後一步，第二級才跑；輸入是這次 FFXIV 分析輸出裡的未知術語標記，呼叫 LLM、印出會寫入的條目，不寫 `knowledge_base`、不改 `articles`。

**Rationale**：一次觸發就驗完 `#218` 的四條呼叫路徑；用這次的輸出當輸入，才保證有標記可送（資料庫裡當下可能沒有待處理的標記，那樣 LLM 根本不會被呼叫）。

**Alternatives considered**：`auto-kb.yml` 自己加一個不寫入的手動入口——要觸發兩次，而且吃的是資料庫裡現有的標記。

## D6 專案規則與流程接點落在哪幾個檔（第二、三片）

**Decision**（提案，未定；憲章這一點已定 2026-11-15）：

- 憲章加一節「分層驗收」（新增一節，照修訂程序是 MINOR：2.1.1 → 2.2.0），寫原則、九類驗收範圍與各自夠用的驗法、觀測跟驗收分開、驗收條件先寫最早就夠用的驗法。
- 憲章 Operations & Deployment：補上不發布的入口，寫明它驗的是接線與輸出、不是預演週一。Governance 的 Compliance review：PR 內文交代這一片的驗收範圍、驗法與結果。
- tasks 的分組：靠 plan 的 Constitution Check 帶下去（每一片標驗收範圍與驗法），不改 user 層的範本。
- BACKLOG 列的移出時點與讀回另開一列：寫進憲章那一節；本機的在地設定裡「closeout 在完成它的那個 PR 做」那一段要跟著改（不進版控，維護者的機器上改）。
- 操作細節（怎麼觸發、產物叫什麼）寫在 `docs/`，憲章只指過去。`docs/external-services.md` 的 Gemini 那一列補一句：不發布的第二級算在同一個預算裡。

**Alternatives considered**：把 tasks 的分組寫成 repo 裡的範本副本——不採用，副本會蓋過 user 層的範本（`.github/cold-review-paths` 的註解記了這件事）。

## 還沒查的

- 不發布的執行跟正式排程同時跑會不會互相影響：兩個 workflow 沒有共用的 concurrency 設定（`weekly.yml` 沒有 `concurrency`，2026-11-15 `grep`）；資料面只有讀，推論不影響，沒有實測。
- 第二級一次的實際用量與費用：等第一次實跑的紀錄。
