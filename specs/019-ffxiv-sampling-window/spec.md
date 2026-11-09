# Feature Specification: FFXIV 週報取樣修正（Reddit 收窄、英文官方論壇、移除論壇列表頁）

**Feature Branch**: `019-ffxiv-sampling-window`  
**Created**: 2026-11-09  
**Status**: Draft  
**Input**: BACKLOG `GNS-20261019-3cq`。Luke 2026-11-09 裁示「問題在取樣，開 spec」：對象是 Reddit 只取到最新約 8 小時、論壇列表頁只有標題這兩件事，
不是被擠掉的那幾篇；patch-triggered 與聚合 digest 兩半的處置不變。同日排序：本 spec 排在 `GNS-20261108-2zc`、`GNS-007` 之前。
開 spec 當天的討論把範圍改成 Reddit 收窄、加收英文官方論壇、移除論壇列表頁（見 Clarifications）。

## 背景

**週報的 Reddit 部分只代表收集前幾小時。** 11-09 週報的候選池 artifact（run `42556081408`，`ffxiv-pool`，44 篇、入選 20 篇）：

- 論壇版 9 篇（權重 80）全部入選，排在最前面。
- Reddit 25 篇（權重 20）的發布時間在 11-08 19:22Z～11-09 03:23Z，約 8 小時。同權重依發布時間排，入選的 11 篇就是最新的 11 篇。
- 論壇列表頁 10 篇（權重 10）全部被擠掉：沒有發布時間，摘要是「`[JP Forum] `」加標題本身（23～44 字）；內容是營運公告 5 篇、玩家回報 5 篇。
  10-26、11-02、11-09 三週都是 0 篇入選。
- agent 依標題與摘要判斷（沒有回原串）：被擠掉的 14 篇 Reddit 是提問 7、作品分享 3、心得或評論 4，跟入選的 11 篇組成相近。

成因：Reddit 來源讀的是「最新 25 篇」的 feed，r/ffxiv 一天的貼文遠多於 25 篇；篩選照權重排、同權重由新到舊（spec 015 FR-004），
所以進得了分析的 Reddit 永遠是收集前最後幾小時。論壇列表頁沒有時間、權重最低，名額永遠輪不到它。逐週數字在 `specs/BACKLOG.md` 的 `GNS-20261019-3cq` 節。

**把取樣窗修成整週，Reddit 的內容也不見得變好。** 2026-11-09 兩項量測：

| 來源 | W44–W46 進分析的篇數 | 重要度「高」 | 「中」 | 「低」 |
|---|---|---|---|---|
| Reddit | 39 | 0 | 0 | 39 |
| 論壇版 | 20 | 1 | 1 | 18 |
| Lodestone | 1 | 0 | 0 | 1 |

（公開 Worker API `/api/weeks/<週>?content_type=ffxiv` 每篇 `analysis.importance`，模型標的。）這張表本身分不出「Reddit 沒料」與「只抽到 8 小時」。
所以同日從本機讀 r/ffxiv 的本週熱門 feed（`top`，`t=week`，40 篇，發布時間平均分布在 11-02～11-09 的 8 天）：agent 只看標題判斷，
多半是同人圖、cosplay、截圖、迷因與個人成就，新聞或討論約 5 篇（NA／EU 資料中心同區配對上線、競速作弊者被取消資格、一則 PSA、對裝備外觀的抱怨、副本結構的比較）。
同一次從本機打 Reddit 的 JSON 端點回 403，所以分數、留言數、flair 都沒拿到。

## Clarifications

### Session 2026-11-09

- Q: 論壇列表頁（只有標題、沒有時間、權重 10，三週 0 篇入選）怎麼處置？ → A: 整個移除。
- Q: Reddit 改成涵蓋整週後，名額內依什麼挑？ → A: Luke：「先考慮是不是要繼續留 reddit」。看過上面兩項量測後：「先把範圍縮小到只收新聞討論，官方論壇多收英文語系」。
- Q: 「新聞與討論」含不含提問／求助類？ → A: 不含提問。
- Q: 英文官方論壇各版的權重？ → A: 跟日文版同級；Luke：「可以考慮加大池子容量了」（指分析篇數上限 20）。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reddit 只進新聞與討論，而且涵蓋整週 (Priority: P1)

使用者（Luke）讀 FFXIV 週報，想從英文社群看到這一週的新聞與討論。現在進分析的十來篇 Reddit 全來自收集前約 8 小時，三週 39 篇的重要度全是「低」；
整週最熱門的又多半是作品分享。使用者要：Reddit 只收新聞、官方消息轉貼、討論類的貼文，而且從整個收集窗口收，不只收集前幾小時。

**Why this priority**: 每週都發生，FFXIV 週報約一半的篇數來自 Reddit（11-09：20 篇裡 11 篇）。這是 Luke 11-09 點名的第一件事。

**Independent Test**: 讀上線後週報的 `ffxiv-pool` artifact，逐篇判讀 Reddit 候選與入選的類別，並看發布時間分布；對照 11-09。

**Acceptance Scenarios**:

1. **Given** 收集窗口 7 天，**When** 週報執行，**Then** Reddit 候選來自整個窗口，不只收集前幾小時。
2. **Given** 窗口內有同人圖、cosplay、截圖、迷因、個人成就、提問／求助類的貼文，**When** 收集，**Then** 它們不進候選池，log 印出各類排除的篇數。
3. **Given** 窗口內有官方消息轉貼（例：資料中心同區配對上線）與討論串，**When** 收集，**Then** 它們進候選池。
4. **Given** 整週的 Reddit 抓不到，或分不出貼文的類別，**When** 收集，**Then** log 印出原因；未分類的貼文不進候選池，週報照常產生。

---

### User Story 2 - 官方論壇加收英文語系的版 (Priority: P1)

Reddit 收窄之後，英文社群的視角改由官方論壇的英文版補上。使用者要：英文官方論壇裡對應日文五個版（プロデューサーレターLIVE、TANK、DPS、HEALER、
戰鬥系統）的版，照 015 對日文版的做法收集（依最後回覆排序、這週窗口內的回覆合成一篇），跟日文版同級競爭名額；名額不夠時加大分析篇數上限。

**Why this priority**: 跟 US1 一起決定英文社群在週報裡的樣子；只做 US1 的話，英文內容會比現在少。

**Independent Test**: 讀上線後週報 log 的逐來源篇數與 `ffxiv-pool` artifact，數英文版的候選與入選；對照同一週各版 RSS 裡窗口內的串數。

**Acceptance Scenarios**:

1. **Given** 英文某版這週有 3 串有新回覆，**When** 週報執行，**Then** 那 3 串都進候選池，每串的內容是這週窗口內的回覆（上限內）。
2. **Given** 日文版與英文版窗口內的串加起來超過分析篇數上限，**When** 篩選，**Then** log 印出被擠掉的論壇串數，讓上限的調整有依據。
3. **Given** 英文 PLL 對應的版有窗口內的串，**When** 篩選，**Then** 它跟日文 PLL 同樣排最前。

---

### User Story 3 - 移除論壇列表頁 (Priority: P2)

論壇列表頁每週約 10 篇候選，只有標題、沒有時間，三週 0 篇入選，等於每週收了也不用。使用者要：不再收這個來源。

**Why this priority**: 不改變入選的內容（反正進不來），但候選池的數字因此虛胖。

**Independent Test**: 讀上線後週報的 log 與 `ffxiv-pool` artifact，論壇列表頁的候選是 0 篇。

**Acceptance Scenarios**:

1. **Given** 上線後的週報，**When** 讀候選池，**Then** 沒有論壇列表頁的候選，`來源失敗` 那一行也不出現它。

---

### Edge Cases

- **大 patch 週**：Reddit 與論壇的量都會暴增。Reddit 候選仍要涵蓋整個窗口；論壇各版照 015 的上限與截斷警告。
- **Actions 的 IP 打不到需要的 Reddit 端點**：本機打 JSON 端點已經 403。打不到時照 US1 第 4 條處理，不能靜靜地只拿 8 小時、也不能把未分類的貼文放進來。
- **Reddit 新聞貼文只有外部連結、沒有內文**：照收（標題＋連結），跟現在的 Reddit 連結貼文一樣。
- **英文版某週 0 串**：不出聲、不算失敗（015 的規則）。
- **重複**：同一篇 Reddit 貼文從兩條路徑進來時只留一篇；跨語言的同一則消息（英文 Reddit 轉貼與日文 Lodestone）不去重。
- **刪文**：收集時已被刪除或移除的 Reddit 貼文不進候選。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Reddit 的候選 MUST 來自整個收集窗口（7 天），不是收集前最新的固定篇數。
- **FR-002**: Reddit 的候選 MUST 只收新聞、官方消息轉貼、討論類的貼文；同人圖等作品、cosplay、截圖、迷因、個人成就、提問／求助類 MUST NOT 進候選池。
  分類依據在 plan 決定；log MUST 印出保留與各類排除的篇數。
- **FR-003**: Reddit 抓不到、或分不出類別時，MUST 印原因；未分類的貼文 MUST NOT 進候選池，週報照常產生。
- **FR-004**: MUST 加收英文官方論壇裡對應日文五個版的版，收集方式同 015 的日文版（依最後回覆排序、窗口內回覆合成一篇、截斷警告、0 串不算失敗）；
  權重跟對應的日文版相同（PLL 100、其他 80）。
- **FR-005**: 分析篇數上限 MUST 改由設定決定；plan 依量到的每週供給（日文版、英文版、Lodestone、收窄後的 Reddit）提出新值，由 Luke 核定，可以維持 20。
  上限截掉論壇串時，log MUST 印被擠掉的論壇串數。
- **FR-006**: MUST 移除論壇列表頁（`html_forum`，`512-Japanese-Forums`）這個來源。
- **FR-007**: 每週一份的節奏、015 的排序規則（權重降冪、同權重新到舊、沒有時間的排最後）MUST NOT 改變；patch-triggered 與聚合 digest 不在範圍。
- **FR-008**: `ffxiv-pool` artifact 與 log 的逐來源篇數（015 FR-010）MUST 照常輸出，英文各版各自一列；SC 都從它們讀。
- **FR-009**: 三項變更（Reddit 收窄、英文版、移除列表頁）與上限調整 MUST 各自可單獨回復，回復後行為回到變更前。

### Key Entities

- **Reddit 候選**：一篇 r/ffxiv 貼文，帶發布時間、標題、內文摘要與它的類別（新聞、官方消息轉貼、討論；或被排除的類別）。
- **英文論壇版**：英文官方論壇裡對應日文五個版之一；一串＝這週窗口內的回覆合成一篇，跟日文版同一個形狀。
- **候選池 artifact（`ffxiv-pool`）**：每週週報在入選當下存下的整個候選池，含排序、是否入選與摘要全文；保留 90 天。

## Success Criteria *(mandatory)*

**量測前提**：讀自上線後每週週報的 `ffxiv-pool` artifact 與 log；Reddit 類別由人工逐篇判讀（判讀標準寫進驗收紀錄）。硬門檻只收實測。
錨定值都是 11-09（run `42556081408`）或上面背景的兩項量測。

### SC-001 Reddit 只進新聞與討論（本 spec 的主要目標之一）

- **SC-001 Gate**：上線後連兩週，入選的 Reddit 逐篇判讀，排除類別（作品、cosplay、截圖、迷因、個人成就、提問）0 篇。錨定：11-09 入選 11 篇裡作品 5、提問 4。
- **SC-001 L1**：連兩週，候選池裡的 Reddit 排除類別 ≤ 2 篇（分類漏網）。
- **SC-001 L2 / 理想**：連兩週，Reddit 候選的發布時間跨度 ≥ 6 天，或窗口內符合類別的貼文少於 6 天份時全部進了候選。錨定：11-09 是 8 小時。

### SC-002 英文官方論壇

- **SC-002 Gate**：上線後連兩週，英文版至少 1 串進分析。
- **SC-002 L1**：連兩週，日文版與英文版窗口內的串全部入選（入選數等於可用數）。
- **SC-002 L2 / 理想**：連兩週，英文版的分析至少一半人工判讀為「講得出這週在討論什麼」。

### SC-003 論壇列表頁移除

- **SC-003 Gate**：上線後第一週，候選池裡論壇列表頁 0 篇。錨定：11-09 有 10 篇。

### SC-004 不退步

- **SC-004 Gate**：連兩週，日文五個版與 Lodestone 窗口內的項目照舊全部入選。錨定：11-09 論壇版 9／9。
- **SC-004 測試**：015 的「PLL 優先」unit test 照舊綠；FR-003 的退路（抓不到、分不出類別時不收、log 印原因）由 unit test 鎖住。

### SC-005 runtime 與成本

- **SC-005 Gate**：週報照常完成，不碰 30 分鐘逾時。錨定：史上最長 15.2 分鐘（`weekly.yml` 註解，09-07）。
- **SC-005 L1**：週報耗時 ≤ 20 分鐘。錨定：11-09 是 10m31s；FFXIV 每篇分析約 15～18 秒（10-12、10-19 量）；「20 分鐘」是判斷。
- **SC-005 記錄**：上限提高時，每週多出的分析篇數（Gemini 呼叫數）寫進驗收紀錄。

## Assumptions

- 收集窗口是 7 天。Checked: `src/collector.py:48` `DAYS_BACK = 7`。
- 入選是候選池依權重降冪、同權重新到舊、沒有時間的排最後，取前 20 篇。Checked: `src/filter.py:474` `ffxiv_rank_key` 與 `game_deduplicate` 的 docstring「依同一個鍵取前 20」。
- prod 的 Reddit 來源讀 `https://www.reddit.com/r/ffxiv/new/.rss`、權重 20；論壇列表頁是 `html_forum`、`512-Japanese-Forums`、權重 10、`max_items` 15；
  日文 PLL 權重 100、四個版 80。Checked: 2026-11-09 `gh variable get SOURCES_FFXIV_YML --env production` 解析出的欄位，與 `config/sources_ffxiv.example.yml` 一致。
- Reddit 那一路每週只有收集前約 8 小時。Checked: `GNS-20261019-3cq` 節 11-09 artifact（25 篇在 11-08 19:22Z～11-09 03:23Z）；只量了 11-09 這一週。
- 從本機讀得到 r/ffxiv 的本週熱門 feed，涵蓋整週。Checked: 2026-11-09 `top/.rss?t=week&limit=40` 回 200、40 篇、發布日 11-02～11-09。
- 從 Actions 拿得到分辨 Reddit 貼文類別的訊號（例如 flair）。Unchecked: 本機打 JSON 端點 403（2026-11-09），RSS 帶不帶 flair 沒查；
  拿不到時 FR-003 會讓 Reddit 一篇都不收，等於移除 Reddit，要回頭請 Luke 裁示。
- 英文官方論壇有對應日文五個版的版，而且有依最後回覆排序的 RSS、串頁面不必登入讀得到。Unchecked: 015 只驗過日文五個版（10-20 實測，PR `#173`）；
  英文版的 forum id 沒查；沒有對應的版時 US2 的範圍要改。
- 英文版每週窗口內的串數。Unchecked: 沒量；它決定 FR-005 的上限與 SC-005 的 runtime，plan 先量一週再定。
- FFXIV 每篇分析約 15～18 秒。Checked: `GAR-33` 10-20 那則 handoff 留言（相鄰兩個「分析完成」的間隔平均，10-12 15.0 秒、10-19 17.6 秒）；換模型或輸入變長會變。
- 論壇列表頁移除後，營運公告與玩家回報沒有管道進分析，接受。Checked: Luke 2026-11-09 選「整個移除」；這兩類現在也 0 篇入選。
- Reddit 貼文內文在收集時截到 500 字（`src/collector.py:123` 的 `_clean_summary`）不在範圍。Checked: Luke 11-09 的裁示沒點到它（`3cq` 節）。
