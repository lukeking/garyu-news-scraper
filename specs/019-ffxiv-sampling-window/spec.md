# Feature Specification: FFXIV 週報來源調整（拿掉 Reddit 與論壇列表頁、加收英文官方論壇）

**Feature Branch**: `019-ffxiv-sampling-window`  
**Created**: 2026-11-09  
**Status**: Draft  
**Input**: BACKLOG `GNS-20261019-3cq`。Luke 2026-11-09 裁示「問題在取樣，開 spec」：對象是 Reddit 只取到最新約 8 小時、論壇列表頁只有標題這兩件事；
patch-triggered 與聚合 digest 兩半的處置不變。同日排序：本 spec 排在 `GNS-20261108-2zc`、`GNS-007` 之前。同日的討論把範圍定成三件（見 Clarifications）。
分支名沿用開 spec 時的 `sampling-window`。

## 背景

**Reddit 只代表收集前幾小時，而且只有開串。** 11-09 週報的候選池 artifact（run `42556081408`，`ffxiv-pool`，44 篇、入選 20 篇）：

- 論壇版 9 篇（權重 80）全部入選。Reddit 25 篇（權重 20）的發布時間在 11-08 19:22Z～11-09 03:23Z，約 8 小時；入選的 11 篇就是最新的 11 篇。
- 論壇列表頁 10 篇（權重 10）全部被擠掉：沒有發布時間，摘要是「`[JP Forum] `」加標題（23～44 字）。10-26、11-02、11-09 三週都是 0 篇入選。
- W44–W46 進分析的 Reddit 39 篇，重要度（模型標的 `analysis.importance`，公開 Worker API）全是「低」；同期論壇版 20 篇有高 1、中 1。

**Reddit 的 robots.txt 不准抓。** 11-09 用 collector 正式的 UA 讀 `https://www.reddit.com/robots.txt`：`User-agent: *`、`Disallow: /`，並指向 Reddit 的 Public Content Policy。
現有的 `new/.rss` 也在 `Disallow: /` 的範圍內（既有狀況，本 spec 才看見）。同日其他查證：本週熱門 feed 涵蓋整週但多半是作品分享、每篇只有開串；
單篇留言 RSS 用正式 UA 拿得到回覆；官方 API 10-31 起不受理新申請、2027-03 結束（Reddit Help Center 的 Changelog - October 8, 2026，搜尋摘要）。
這些在 robots.txt 之前就查了，結論因 robots.txt 而不用，細節在 research R1。

## Clarifications

### Session 2026-11-09

- Q: 論壇列表頁怎麼處置？ → A: 整個移除。
- Q: Reddit 改成涵蓋整週後依什麼挑？ → A: Luke：「先考慮是不是要繼續留 reddit」；看過重要度與本週熱門之後：「先把範圍縮小到只收新聞討論，官方論壇多收英文語系」。不含提問。
- Q: 英文官方論壇各版的權重？ → A: 跟日文版同級；Luke：「可以考慮加大池子容量了」（指分析篇數上限 20）。
- Q: Reddit 的回覆拿得到嗎、走哪條路？ → A: Luke 問「熱門 feed 內容有比原本的完整嗎？原本只看得到開串內容，看不到回串的文」。過程：公開 feed 只有開串；
  官方 OAuth 不受理新申請；agent 一度誤稱 collector 靠瀏覽器 UA 讀 Reddit（讀錯常數，其實是 `GaryuNewsBot`），更正後用正式 UA 探到留言 RSS 拿得到，
  Luke 裁示「留 Reddit：新聞討論＋回覆」。
- Q: Reddit 的 robots.txt 是 `Disallow: /`，憲章 IV 要求加來源前檢查 robots.txt，怎麼處置？ → A: 拿掉 Reddit。

### Session 2026-11-10

- Q: 拿掉 Reddit 與論壇列表頁要不要等英文論壇一起上線？（`/speckit-analyze` 的 H1：只改設定、不依賴 spike，prod 每週仍照常抓 Reddit）
  → A: 不等。從 `main` 另開小 PR 先出貨（Luke 2026-11-10，tasks Unit 0）；本 spec 因此有兩個 PR，英文論壇與上限在 `#210`。
- Q: 分析篇數上限（`ffxiv.max_selected`）設多少？（T003；一週供給約 16～20 篇，research R5、R6，agent 建議 25）→ A: 30（Luke 2026-11-10）。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 英文社群的視角改由官方論壇英文版提供 (Priority: P1)

使用者（Luke）讀 FFXIV 週報，想同時看到日本與英文玩家這一週在職業平衡、戰鬥系統上討論什麼。使用者要：英文官方論壇裡對應日文五個版
（プロデューサーレターLIVE、TANK、DPS、HEALER、戰鬥系統）的版，照 015 對日文版的做法收集（依最後回覆排序、這週窗口內的回覆合成一篇），
跟日文版同級競爭名額；名額不夠時加大分析篇數上限。

**Why this priority**: 拿掉 Reddit 之後，這是英文視角唯一的來源；也是 Luke 11-09 的方向。

**Independent Test**: 讀上線後週報 log 的逐來源篇數與 `ffxiv-pool` artifact，數英文版的候選與入選；對照同一週各版 RSS 裡窗口內的串數。

**Acceptance Scenarios**:

1. **Given** 英文某版這週有 3 串有新回覆，**When** 週報執行，**Then** 那 3 串都進候選池，每串的內容是這週窗口內的回覆（上限內），不是開串摘要。
2. **Given** 論壇窗口內的串加起來超過分析篇數上限，**When** 篩選，**Then** log 印出被擠掉的論壇串數。
3. **Given** 英文 PLL 對應的版有窗口內的串，**When** 篩選，**Then** 它跟日文 PLL 同樣排最前。
4. **Given** 英文版串頁面的時間格式或時區跟日文版不同，**When** 收集，**Then** 回覆時間仍正確換算；解析不出的回覆照 015 當窗口外並印原因。

---

### User Story 2 - 拿掉 Reddit (Priority: P1)

Reddit 只拿得到收集前約 8 小時的開串，三週 39 篇的重要度全是「低」，而且 robots.txt 不准抓。使用者要：不再收 Reddit。

**Why this priority**: 讓週報的來源符合 robots.txt 與憲章 IV；也跟 US1 一起決定英文內容的樣子。

**Independent Test**: 讀上線後週報的 log 與 `ffxiv-pool` artifact，Reddit 的候選是 0 篇，`來源失敗` 那一行也不出現它。

**Acceptance Scenarios**:

1. **Given** 上線後的週報，**When** 讀候選池與 collector 送出的請求，**Then** 沒有任何對 reddit.com 的請求，也沒有 Reddit 的候選。

---

### User Story 3 - 拿掉論壇列表頁 (Priority: P2)

論壇列表頁每週約 10 篇候選，只有標題、沒有時間，三週 0 篇入選。使用者要：不再收這個來源。

**Why this priority**: 不改變入選的內容，但候選池的數字因此虛胖。

**Independent Test**: 讀上線後週報的 log 與 `ffxiv-pool` artifact，論壇列表頁的候選是 0 篇。

**Acceptance Scenarios**:

1. **Given** 上線後的週報，**When** 讀候選池，**Then** 沒有論壇列表頁的候選，`來源失敗` 那一行也不出現它。

---

### Edge Cases

- **候選少於上限**：拿掉 Reddit 後，日文版加 Lodestone 一週約 7～11 篇，英文版的量未知。少於上限時全部入選，週報篇數少於 20 是預期的，不補。
- **大 patch 週**：論壇各版照 015 的回覆上限、頁數上限與截斷警告；英文版量大時可能觸發上限，log 出聲（US1 第 2 條）。
- **英文版某週 0 串**：不出聲、不算失敗（015 的規則）。
- **論壇限速**：11-09 本機連打論壇 10 次就 429。英文版加入後每週請求數約翻倍，要看 `來源失敗` 那一行。
- **跨語言的同一件事**：英文串與日文串討論同一件事時不去重，各自進分析。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: MUST 加收英文官方論壇裡對應日文五個版的版，收集方式同 015 的日文版（依最後回覆排序、窗口內回覆合成一篇、回覆與頁數上限、截斷警告、0 串不算失敗）；
  權重跟對應的日文版相同（PLL 100、其他 80）。
- **FR-002**: 英文版串頁面的回覆時間 MUST 依頁面實際的時區換算成 UTC；時區與格式在 research 實測，不能沿用日文版的假設不查。
- **FR-003**: 分析篇數上限 MUST 改由設定決定；plan 依量到的每週供給（日文版、英文版、Lodestone）提出新值，由 Luke 核定，可以維持 20。
  上限截掉論壇串時，log MUST 印被擠掉的論壇串數。上限改變時 MUST 同步 `docs/external-services.md` 的 Gemini 那一列（憲章 IV）。
- **FR-004**: MUST 移除 Reddit 來源。
- **FR-005**: MUST 移除論壇列表頁（`html_forum`，`512-Japanese-Forums`）來源。
- **FR-006**: 每週一份的節奏、015 的排序規則（權重降冪、同權重新到舊、沒有時間的排最後）MUST NOT 改變；patch-triggered 與聚合 digest 不在範圍。
- **FR-007**: `ffxiv-pool` artifact 與 log 的逐來源篇數（015 FR-010）MUST 照常輸出，英文各版各自一列；SC 都從它們讀。
- **FR-008**: 每項變更（英文版、移除 Reddit、移除列表頁、上限）MUST 可單獨回復，回復後行為回到變更前。

### Key Entities

- **英文論壇版**：英文官方論壇裡對應日文五個版之一；一串＝這週窗口內的回覆合成一篇，跟日文版同一個形狀。
- **分析篇數上限**：每週 FFXIV 最多分析幾篇；決定 Gemini 呼叫數的上界（憲章 IV）。
- **候選池 artifact（`ffxiv-pool`）**：每週週報在入選當下存下的整個候選池，含排序、是否入選與摘要全文；保留 90 天。

## Success Criteria *(mandatory)*

**量測前提**：讀自上線後每週週報的 `ffxiv-pool` artifact 與 log；窗口內可用串數由同一週 RSS 重算。硬門檻只收實測。錨定值都是 11-09（run `42556081408`）。

### SC-001 英文官方論壇進分析（本 spec 的主要目標）

- **SC-001 Gate**：上線後連兩週，英文版至少 1 串進分析。
- **SC-001 L1**：連兩週，日文版與英文版窗口內的串全部入選，或被上限截掉時 log 印出被擠掉的串數。
- **SC-001 L2 / 理想**：連兩週，英文版的分析至少一半人工判讀為「講得出這週在討論什麼」（逐篇判讀，結果寫進驗收紀錄）。

### SC-002 Reddit 與論壇列表頁移除

- **SC-002 Gate**：拿掉 Reddit 與論壇列表頁的小 PR 上線後第一週（tasks Unit 0，比英文論壇早上線），候選池裡 Reddit 與論壇列表頁都是 0 篇，週報 log 沒有對 reddit.com 的請求。錨定：11-09 各 25、10 篇。

### SC-003 時間換算正確（硬門檻，測試）

- **SC-003 Gate**：英文版串頁面的時間解析有 unit test，用 research 實測到的格式與時區；故意改錯時區，測試轉紅。

### SC-004 不退步

- **SC-004 Gate**：連兩週，日文五個版與 Lodestone 窗口內的項目照舊全部入選。錨定：11-09 論壇版 9／9。
- **SC-004 測試**：015 的「PLL 優先」unit test 照舊綠。

### SC-005 runtime 與成本

- **SC-005 Gate**：週報照常完成，不碰 30 分鐘逾時。錨定：史上最長 15.2 分鐘（`weekly.yml` 註解，09-07）。
- **SC-005 L1**：週報耗時 ≤ 20 分鐘。錨定：11-09 是 10m31s；「20 分鐘」是判斷。
- **SC-005 記錄**：每週 FFXIV 的分析篇數（Gemini 呼叫數）與 11-09 的 20 篇並列，寫進驗收紀錄。

## Assumptions

- 收集窗口是 015 的固定週邊界（本週一 00:00 UTC 往前 7 天）。Checked: `src/collector.py` 的 `_forum_window`。
- 入選是候選池依權重降冪、同權重新到舊、沒有時間的排最後，取前 20 篇；20 寫死在程式裡。Checked: `src/filter.py:474` `ffxiv_rank_key`、`src/filter.py:557` `retained[:20]`。
- prod 的 FFXIV 來源：Reddit `new/.rss` 權重 20、論壇列表頁 `html_forum` 權重 10、日文 PLL 100、四個版 80、Lodestone 60。
  Checked: 2026-11-09 `gh variable get SOURCES_FFXIV_YML --env production` 解析出的欄位，與 `config/sources_ffxiv.example.yml` 一致。
- Reddit 的 robots.txt 不准任何爬蟲抓任何路徑。Checked: 2026-11-09 用 `GaryuNewsBot/1.0` 的 UA 讀 `https://www.reddit.com/robots.txt`，200，`User-agent: *`、`Disallow: /`。
- 英文官方論壇的上層版是 642 Letters from the Producer、656 Classes & Jobs。Checked: 2026-11-09 讀 `forum.php` 的版列表（200）；日文對應是 535、549。
- 英文的五個子版各有對應、id 是什麼；有依最後回覆排序的 RSS、串頁面不必登入讀得到、時間格式與時區可以解析。Checked: 2026-11-10 T001——644、657、658、659、660，
  RSS 與串頁面都 200、不必登入；串頁面跟日文版同格式、日本時間（research R3、R4）。
- 英文版每週窗口內的串數。Checked: 2026-11-10 T002——窗口 11-02～11-09 共 9 串（PLL 0、Tank 1、DPS 6、Healer 1、Other 1），只量了一週（research R5）。
- 日文版加 Lodestone 一週約 7～11 篇。Checked: `3cq` 節的三週候選池（論壇版 7、4、9 篇入選，Lodestone 0～1）。
- FFXIV 每篇分析約 15～18 秒。Checked: `GAR-33` 10-20 那則 handoff 留言（10-12 15.0 秒、10-19 17.6 秒）。
- 論壇列表頁移除後，營運公告與玩家回報沒有管道進分析，接受。Checked: Luke 2026-11-09 選「整個移除」；這兩類現在也 0 篇入選。
- 拿掉 Reddit 後，`3cq` 原設計裡 patch-triggered 用 Reddit 抓討論的那一半要另想。Checked: `3cq` 節「patch-triggered」那段寫的是 `r/ffxiv/hot.json`；處置留給 `3cq`，不在本 spec。
