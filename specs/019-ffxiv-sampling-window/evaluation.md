# Evaluation: FFXIV 取樣窗口（spec 019）

上線後的讀回。兩次上線——`#211`（拿掉 Reddit 與論壇列表頁，11-10）與 `#210`（加收英文官方論壇五個版、上限改成 30，11-11）——
之後的第一份週報是同一份：11-16（run `43798739037`）。SC-001、SC-004 的 Gate 要連兩週，第二週是 11-23 那一份
（run `45124546806`），記在下面「11-23 週報的讀回（第二週）」。

## 11-16 週報的讀回（T017、T014）

**讀回時間**：2026-11-16（+0800）。**來源**：

- `gh run view 43798739037 --log`（比對前剝掉全部 CSI 控制碼）。
- `gh run download 43798739037 -n ffxiv-pool`：`ffxiv_pool.json`，10 篇、入選 10 篇。
- 公開 Worker API `/api/weeks/2026-W47?content_type=ffxiv`：10 篇的分析。
- 2026-11-16T12:52Z 另外重抓十個論壇版的 RSS（`curl`，不經 `src/collector.py`），重算窗口 11-09 00:00Z～11-16 00:00Z 內的串數。

沒有另外標明的都是實測。

log 的關鍵行：

```text
載入 11 個啟用 FFXIV 來源
收集完成，共 10 筆（去重前）
來源失敗：0/11
FFXIV 候選池 10 篇：FFXIV JP Forum - DPS 3、FFXIV EN Forum - Other Battle Systems 2、FFXIV JP Forum - TANK 2、FFXIV EN Forum - Healer Roles 1、FFXIV JP Forum - HEALER 1、FFXIV Lodestone JP 更新資訊 1
FFXIV 入選 10 篇：（各來源的篇數與候選池那一行相同）
FFXIV 候選池內容：寫入 ffxiv_pool.json（10 篇，入選 10 篇）
FFXIV Lodestone JP 更新資訊: 解析 20 則、收進 1 則（窗口外 11、排除 8）
```

0 行的有：`[ffxiv] 處理失敗`、`截掉論壇`、`429 Client Error`、`退回 RSS 最後一則`、`翻到上限`、`回滿`、`詳細頁抓不到`。

### 各階的結果

| SC | 階 | 11-16 | 依據 |
|---|---|---|---|
| SC-001 | Gate：連兩週，英文版至少 1 串進分析 | 第一週 ✅，3 串 | 入選那一行：Healer Roles 1、Other Battle Systems 2 |
| SC-001 | L1：連兩週，窗口內的串全部入選，或印出被截掉的串數 | 第一週 ✅，9／9 | 下面「窗口內的串數」 |
| SC-001 | L2：連兩週，英文版的分析至少一半講得出這週在討論什麼 | 第一週 3／3（agent 判讀，是判斷，不是人工判讀） | 下面「英文版逐篇判讀」 |
| SC-002 | Gate：上線後第一週，候選池的 Reddit 與論壇列表頁都是 0 篇，log 沒有對 reddit.com 的請求 | ✅ | `ffxiv_pool.json` 10 篇的 `source` 沒有這兩個；log 不分大小寫找 `reddit` 是 0 行 |
| SC-003 | Gate：英文版串頁面的時間解析有 unit test | 測試在、綠 | `tests/unit/test_vb_forum_parse.py` 的 `test_english_reply_time_matches_rss_pubdate`；改錯時區會轉紅是實作時驗的，這次沒有重做 |
| SC-004 | Gate：連兩週，日文五個版與 Lodestone 窗口內的項目全部入選 | 第一週 ✅，論壇 6／6、Lodestone 1／1 | 候選池與入選兩行；下面「窗口內的串數」 |
| SC-004 | 測試：015 的排序測試照舊綠 | ✅ | `tests/unit/test_ffxiv_ranking.py` |
| SC-005 | Gate：週報照常完成，不碰 30 分鐘 | ✅，6m09s | job `started_at` 03:32:01Z → `completed_at` 03:38:10Z |
| SC-005 | L1：≤ 20 分鐘 | ✅ | 同上 |
| SC-005 | 記錄：分析篇數與 11-09 的 20 篇並列 | 10 篇 | `✓ 分析完成：` 10 行；第一行到最後一行 172.9 秒，間隔平均 19.2 秒（11-09 是 373.0 秒、19.6 秒） |

兩個測試檔 2026-11-16 在 `ef36fa5` 跑：`.venv/bin/python -m pytest tests/unit/test_ffxiv_ranking.py tests/unit/test_vb_forum_parse.py -q` → `36 passed, 7 warnings in 1.20s`。

### 窗口內的串數（SC-001 L1、SC-004）

| 版 | RSS 則數（12:52Z） | 最後回覆在窗口內 | 週報收到（log 的 `<版>: N 筆`） |
|---|---|---|---|
| JP プロデューサーレターLIVE（537） | 0 | 0 | 0 |
| JP TANK（550） | 2 | 2 | 2 |
| JP DPS（551） | 10 | 3 | 3 |
| JP HEALER（552） | 4 | 1 | 1 |
| JP その他バトルシステム（553） | 9 | 0 | 0 |
| EN Letter from the Producer LIVE（644） | 0 | 0 | 0 |
| EN Tank Roles（657） | 2 | 0 | 0 |
| EN DPS Roles（658） | 7 | 0 | 0 |
| EN Healer Roles（659） | 3 | 1 | 1 |
| EN Other Battle Systems（660） | 3 | 2 | 2 |
| 合計 | 40 | 9 | 9 |

- 九串的標題與最後回覆時間，RSS 與 `ffxiv_pool.json` 的 `title`、`published` 逐串相同。沒有一版回滿 15 則。
- 重抓時有三串的最後回覆落在窗口之後（都是 11-16 週報跑完之後才有的回覆）：`賢者スレ`（05:12Z）、`種族ステータス補正を廃止してほしい`（06:46Z）、
  英文 DPS 版的一串（10:22Z）。RSS 只給每串最後一則回覆的時間，這三串在窗口內有沒有回覆，重抓的 RSS 看不出來。
  週報當下（03:33Z）的 log 沒有這三串的 `窗口內 N 則` 行；程式對最後回覆不早於窗口起點的串都會進去讀，所以當時它們的最後回覆早於 11-09（推論）。

### 英文版逐篇判讀（SC-001 L2）

判讀的人是 agent：拿分析（Worker API 的 `summary` 與 `analysis`）對照輸入（`ffxiv_pool.json` 的 `summary`）。三篇都讀了輸入的前 1500 字；
另外第一、三篇看了每則貼文的開頭，第二篇看了四個段落標題的前後文。都沒有逐字讀完。

| 串（版；窗口內則數；輸入字數） | 分析講了什麼 | 原串 | 判讀 |
|---|---|---|---|
| Beastmaster/Crucible of the Unbroken : Great Content, but Several Adjustments needed（Other Battle Systems；2 則；2505 字） | 拿到全部傳奇評級的玩家回饋：最高難度 Third Degree 接近單人的零式或絕；微操太多、寵物走位與仇恨不直觀、裝備數值有沒有算到寵物身上不清楚、太靠 RNG；提議給寵物不佔 GCD 的即時挑釁 | 貼文逐項列的就是這幾點（micromanagement、pet management、enmity system 與 off-GCD Provoke） | 講得出 |
| Top 100 NA Beastmaster Design Opinions（Other Battle Systems；1 則；6000 字） | 循環晦澀又單調、技能說明難懂；高難度關卡太難；roguelike 的部分靠運氣不靠決策；寵物指令有延遲；希望下一批內容放棄不成熟的機制 | 四段：1) The rotation、2) Borgny and Lauda（第三級的兩個頭目）、3) The crucible is a bad roguelike（希望下一批內容改成固定的戰鬥）、4) 小問題（講到 Trick 與寵物站位時被截斷） | 講得出 |
| What Would You Have Wanted From "Evolved" Healers（Healer Roles；5 則；4147 字） | 補師的輸出循環太單一、MP 不再是要管的資源；有人說每個資料片都講會改、結果沒變 | 貼文有「111112111112 spam」「mana to be a relevant resource again」「They tell this every single expansion」 | 講得出 |

沒查的：第三篇的分析把原串的 EC（Evercold）寫成「白銀資料片」，這個譯名對不對沒有查。

### 讀回時看到、SC 沒有問的

- 候選池只有 10 篇，上限 30 沒有用到。11-09（還有 Reddit 與論壇列表頁）是候選池 44、入選 20；Reddit 那時佔入選的 11 篇。
- 英文版這一週窗口內 3 串；上線前量的那一週（11-02～11-09，research R5）是 9 串，其中 DPS Roles 6 串，這一週是 0 串。只有兩週的數字。
- 兩篇的輸入在收集時被截短：英文的 Top 100 那一串是 6000 字（截在句子中間），日文的 `先釣りについて` 是 5978 字（log：`窗口內 26 則、收 10 則、翻 3 頁`）。

## 11-23 週報的讀回（第二週）

**讀回時間**：2026-11-23（+0800）。**來源**：

- `gh run view 45124546806 --log`：`weekly-ffxiv.yml` 的排程 run（週報拆成兩支之後 FFXIV 那一支第一次排程），job 06:30:28Z → 06:36:46Z。
- `gh run download 45124546806 -n ffxiv-pool`：`ffxiv_pool.json`，12 篇、入選 12 篇。
- 公開 Worker API `/api/weeks/2026-W48?content_type=ffxiv`：12 篇的分析，標題與 `ffxiv_pool.json` 逐篇相同。
- 2026-11-23T11:06Z 另外重抓十個論壇版的 RSS（不經 `src/collector.py`），重算窗口 11-16 00:00Z～11-23 00:00Z 內的串數。
- 週驗收報告（Linear「News Scraper Weekly Verification」11-23 那一份）在 (7) 引的行，逐行對過上面的 log，都對得上。

沒有另外標明的都是實測。

log 的關鍵行：

```text
載入 11 個啟用 FFXIV 來源
收集完成，共 13 筆（去重前）
來源失敗：0/11
過濾後剩 13 筆（原 13 筆）
FFXIV 候選池 12 篇：FFXIV JP Forum - DPS 4、FFXIV JP Forum - TANK 2、FFXIV JP Forum - その他バトルシステム 2、FFXIV EN Forum - Healer Roles 1、FFXIV EN Forum - Other Battle Systems 1、FFXIV EN Forum - Tank Roles 1、FFXIV JP Forum - HEALER 1
FFXIV 入選 12 篇：（各來源的篇數與候選池那一行相同）
FFXIV 候選池內容：寫入 ffxiv_pool.json（12 篇，入選 12 篇）
FFXIV Lodestone JP 更新資訊: 解析 20 則、收進 0 則（窗口外 12、排除 8）
```

0 行的有：`[ffxiv] 處理失敗`、`FFXIV 上限`、`429 Client Error`、`退回 RSS 最後一則`、`翻到上限`、`回滿 15 串`、`詳細頁抓不到`；不分大小寫找 `reddit` 也是 0 行。

### 各階的結果（第二週與連兩週）

| SC | 階 | 11-23 | 連兩週 | 依據 |
|---|---|---|---|---|
| SC-001 | Gate：連兩週，英文版至少 1 串進分析 | ✅，3 串 | 11-16、11-23 都 ✅，Gate 過 | 入選那一行：Healer Roles 1、Other Battle Systems 1、Tank Roles 1 |
| SC-001 | L1：連兩週，窗口內的串全部入選，或印出被截掉的串數 | ❌，12／13 | 11-16 ✅、11-23 ❌，沒有爬到 | 下面「沒進候選池的一串」 |
| SC-001 | L2：連兩週，英文版的分析至少一半講得出這週在討論什麼 | 3／3（agent 判讀，是判斷，不是人工判讀） | 兩週都是 3／3，都不是人工判讀 | 下面「英文版逐篇判讀（11-23）」 |
| SC-004 | Gate：連兩週，日文五個版與 Lodestone 窗口內的項目全部入選 | ✅，論壇 9／9、Lodestone 0／0 | 11-16、11-23 都 ✅，Gate 過 | 候選池與入選兩行；下面「窗口內的串數（11-23）」 |
| SC-005 | Gate：週報照常完成，不碰 30 分鐘 | ✅，6m18s | — | job `started_at` 06:30:28Z → `completed_at` 06:36:46Z |
| SC-005 | L1：≤ 20 分鐘 | ✅ | — | 同上 |
| SC-005 | 記錄：分析篇數 | 12 篇 | — | `✓ 分析完成：` 12 行；第一行到最後一行 269.5 秒，間隔平均 24.5 秒（11-16 是 172.9 秒、19.2 秒；11-09 是 373.0 秒、19.6 秒） |

SC-002、SC-003 的 Gate 是上線後第一週，11-16 已記；這一週 `ffxiv_pool.json` 12 篇的 `source` 仍然沒有 Reddit 與論壇列表頁。

### 窗口內的串數（11-23）

| 版 | RSS 則數（11:06Z） | 最後回覆在窗口內 | 週報收到（log 的 `<版>: N 筆`） | 入選 |
|---|---|---|---|---|
| JP プロデューサーレターLIVE（537） | 0 | 0 | 0 | 0 |
| JP TANK（550） | 2 | 2 | 2 | 2 |
| JP DPS（551） | 10 | 4 | 4 | 4 |
| JP HEALER（552） | 4 | 1 | 1 | 1 |
| JP その他バトルシステム（553） | 7 | 2 | 2 | 2 |
| EN Letter from the Producer LIVE（644） | 0 | 0 | 0 | 0 |
| EN Tank Roles（657） | 2 | 1 | 1 | 1 |
| EN DPS Roles（658） | 7 | 1 | 1 | 0 |
| EN Healer Roles（659） | 3 | 1 | 1 | 1 |
| EN Other Battle Systems（660） | 4 | 1 | 1 | 1 |
| 合計 | 39 | 13 | 13 | 12 |

- 入選的十二串，標題與 RSS 逐串相同，最後回覆時間到分鐘相同（`ffxiv_pool.json` 的 `published` 沒有秒）。沒有一版回滿 15 則。
- 重抓時沒有任何一串的最後回覆落在窗口之後，所以這一週沒有 11-16 那種「窗口內有沒有回覆看不出來」的串。

### 沒進候選池的一串（SC-001 L1）

英文 DPS 版的 `What Would You Have Wanted From "Evolved" DPS?`（thread 532142，最後回覆 11-16 10:22Z；log：`窗口內 2 則、收 2 則、翻 1 頁`）
收到了，也過了過濾，卻不在候選池裡。11-16 讀回時記過一串最後回覆落在窗口之後的英文 DPS 版，時間同樣是 10:22Z，應該是同一串（推論：那次沒有記標題）。

- 成因（實測，`9e0caa9`）：`src/filter.py` 的 `game_deduplicate` 拿標題的 token 集合判重複，包含關係或 Jaccard 大於 `jaccard.game_threshold`
  （`config/pipeline_config.example.yml` 是 0.50）就拿掉後出現的那一篇。它跟補師版的 `What Would You Have Wanted From "Evolved" Healers`
  （thread 531628）是兩個版的兩串，標題只差最後一個字：用同一支 `normalise_title` 與 `compute_jaccard` 算，兩邊各 8 個 token、交集 7 個，Jaccard 0.778。
  排序在前的補師版那一串留下，DPS 版那一串被當成重複。
- 被去重拿掉的篇 log 不印：`FFXIV 候選池` 那一行是去重之後的篇數，從 log 只看得出「收集 13、候選池 12」。
- L1 的字面是全部入選，或被上限截掉時印出被擠掉的串數。這一串不是被上限截掉的（入選 12，上限 30，沒有 `FFXIV 上限` 行），既沒有入選、也沒有被印出來，所以這一週 L1 是 ❌。
- 處置（已定 2026-11-23）：開 BACKLOG `GNS-20261123-033`，11-23 週報那批做完之後、`GNS-20261110-sjc` 之前修；做法（論壇串的去重怎麼改、被拿掉的篇印哪一行）在那一列的 PR 定。

### 英文版逐篇判讀（11-23，SC-001 L2）

判讀的人是 agent：拿分析（Worker API 的 `analysis`）對照輸入（`ffxiv_pool.json` 的 `summary`）。第一、三篇的輸入全部讀了，第二篇讀了前 1500 字。

| 串（版；窗口內則數；輸入字數） | 分析講了什麼 | 原串 | 判讀 |
|---|---|---|---|
| Bastion- Discussions and thoughts（Tank Roles；18 則、收 5 則；3531 字） | 職能的劃分與坦克技能太像；有人提議把職業併起來、拿掉職能；雙盾加槍的坦克可以做成遠程、把盾讓給隊友、把盾架成屏障牆 | 五則貼文：物理與魔法遠程該不該算同一個職能、拿掉職能並把職業併起來、雙盾是不是抄來的梗、雙盾加槍可以做成遠程坦克或把盾給別人或架成屏障牆 | 講得出 |
| Request for Blue Mage change（Other Battle Systems；1 則；1871 字） | 青魔道士換技能配置的限制：副本裡 Aetherial Mimicry 啟動時不能換、出副本後長冷卻的技能沒轉完也不能換；建議共用的技能不擋、出副本重置冷卻 | 貼文逐點列的就是這幾項，前 1500 字的結尾開始列同樣的建議 | 講得出 |
| What Would You Have Wanted From "Evolved" Healers（Healer Roles；1 則；150 字） | 有人反諷地說以後 Freecure 要 MP 是質數才觸發、信仰要算到小數；其餘是補師玩法單調的背景 | 窗口內只有一則、一句話，就是那句反諷 | 講得出（分析後半的背景不在這一週的貼文裡） |

沒查的：

- 第一篇的分析把 Bastion 寫成玩家的構想，原串的口氣（`At least they did it`）像是已經公布的職業；Bastion 是不是官方公布的職業沒有查。
- 第三篇的 `tags` 有 `7.x`，輸入裡沒有版本號。
- 英文 DPS 版那一串因為上面的去重沒有分析，不在這張表裡。

### 讀回時看到、SC 沒有問的（11-23）

- 候選池 12 篇，上限 30 仍然沒有用到。
- 窗口內的串數：日文版 9 串（11-16 是 6 串），英文版 4 串、入選 3 串（11-16 是 3 串）。只有兩週的數字。
- 英文 Tank 版那一串窗口內 18 則、只收 5 則（3531 字）。為什麼是 5 則沒有查。
- 分析的間隔平均 24.5 秒，比前兩週（19.2、19.6 秒）長；成因沒有查。
