# Evaluation: FFXIV 取樣窗口（spec 019）

上線後的讀回。兩次上線——`#211`（拿掉 Reddit 與論壇列表頁，11-10）與 `#210`（加收英文官方論壇五個版、上限改成 30，11-11）——
之後的第一份週報是同一份：11-16（run `43798739037`）。SC-001、SC-004 的 Gate 要連兩週，第二週是 11-23 那一份，
由週驗收接著記（`routines/weekly-verify/FOCUS.md` (7)）。

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
