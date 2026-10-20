# Evaluation: FFXIV 週報取樣修正

merge 前的驗證紀錄。週報上的判定（SC-001、SC-002、SC-005、SC-006）在 BACKLOG `GNS-20261020-sbe`。

## T026 SC-004 實測：舊的 Lodestone 設定在新程式下會出聲

**時間**：2026-10-20 20:59（+0800），本機（家用 IP），程式 `b5e4cd6`（S3 已審過）。
**設定**：prod 現行的設定值（9 個來源；Lodestone 仍是 `category/2` 與 `li.news__list--topics`）。只跑
`FFXIVCategory().collect()`，不篩選、不分析、不寫庫。
**更正（同日）**：當時以環境變數 `SOURCES_FFXIV_YML` 餵 `gh variable get` 拿到的 prod 值，但 `load_ffxiv_sources`
在本機有 `config/sources_ffxiv.yml` 時不讀環境變數——實際讀的是本機檔。事後比對：本機檔與 prod 變數解析後的
`sources` 完全相同（9 對 9），所以結論不變；做法已在 quickstart 改成直接換 loader 的檔案路徑。

```text
[WARNING] FFXIV Lodestone JP 更新資訊: 回 200 但解析出 0 項（selector 可能失效）
[INFO] FFXIV Lodestone JP 更新資訊: 0 筆
[INFO] 收集完成，共 51 筆（去重前）
[INFO] 來源失敗：1/9（FFXIV Lodestone JP 更新資訊）
```

各來源：Reddit 25、Lodestone 0、論壇列表頁 15、TW 修正說明 5、論壇 RSS（舊網址、沒有 `lastpost=1`）PLL 0／TANK 0／DPS 1／
HEALER 0／その他 5。

**結論**：通過。09-21～10-19 五週記成 INFO、沒人發現的 `0 筆`，在新程式下是 WARNING，而且列進 `來源失敗`。

## T021 真實入口：新設定跑 collect() 與 filter()

**時間**：2026-10-20 21:2x（+0800），本機（家用 IP），程式 `aef3800`（S1–S4 都已審過）。窗口＝［10-12 00:00Z, 10-19 00:00Z）。
**設定**：`config/sources_ffxiv.example.yml`（T020），以 `patch.object(collector, "FFXIV_SOURCES_FILE", …)` 換掉 loader 讀的檔。
`filter()` 唯讀查 Supabase 的標題指紋；不分析、不寫庫。腳本：每次 `requests.get` 計數、計時。

**第一次跑抓到一個壞來源**：`FFXIV TW 修正說明`（權重 50，高過 Reddit 的 20）入選 5 筆，標題是 `home`、`å®æ¹æå ±ç«`
之類、內容 0 字——selector `li` 對到導覽列，中文被當成 Latin-1 解碼。以前它沒有發布時間、永遠排最後，從沒進過 20 篇。
Luke 10-20 裁示先停用（`enabled: false`），開 BACKLOG `GNS-20261020-rhd`。以下是停用後的結果。

```text
載入 8 個啟用 FFXIV 來源
FFXIV Lodestone JP 更新資訊: 解析 20 則、收進 1 則（窗口外 12、排除 7）
FFXIV JP Forum - DPS: 獣使いスレ 窗口內 20 則、收 18 則、翻 3 頁
FFXIV JP Forum - DPS: 弓術士・吟遊詩人　スレッド 窗口內 1 則、收 1 則、翻 1 頁
FFXIV JP Forum - HEALER: 占星術師スレ その２ 窗口內 2 則、收 2 則、翻 1 頁
FFXIV JP Forum - その他バトルシステム: 魔獣使いの魔獣ランク育成について 窗口內 0 則、收 0 則、翻 1 頁
FFXIV JP Forum - その他バトルシステム: リミットジョブについて 窗口內 3 則、收 3 則、翻 1 頁
FFXIV JP Forum - その他バトルシステム: 種族ステータス補正を廃止してほしい 窗口內 2 則、收 2 則、翻 1 頁
FFXIV JP Forum - その他バトルシステム: 操作タイプ(リボーンモード、エヴォルヴモード)総合スレ 窗口內 1 則、收 1 則、翻 1 頁
來源失敗：0/8
FFXIV 候選池 45 篇：Reddit r/ffxiv 25、FFXIV JP Forum 13、FFXIV JP Forum - その他バトルシステム 3、FFXIV JP Forum - DPS 2、FFXIV JP Forum - HEALER 1、FFXIV Lodestone JP 更新資訊 1
FFXIV 入選 20 篇：Reddit r/ffxiv 13、FFXIV JP Forum - その他バトルシステム 3、FFXIV JP Forum - DPS 2、FFXIV JP Forum - HEALER 1、FFXIV Lodestone JP 更新資訊 1
collect 26.8s, filter 0.7s, requests.get 18 次（含 6 個 RSS）
```

| 入選 | 權重 | 篇數 | 內容長度（字） |
|---|---|---|---|
| 論壇版（DPS、HEALER、その他） | 80 | 6 | 196～5,779（「獣使いスレ」5,779，字數上限下收 18／20 則） |
| Lodestone（10/20 hotfix） | 60 | 1 | 414 |
| Reddit | 20 | 13 | ≤ 500 |

**通過條件**（tasks T021）：論壇版產出 6 篇 ✅、Lodestone 解析 20 ✅、退回 0 次 ✅、截斷警告 0 次（只有その他バトルシステム回滿 15 串，第 15 串在窗口外）。
「魔獣使いの魔獣ランク育成について」最後回覆在窗口終點之後、窗口內 0 則，照設計不產出。

**與現況比**：10-19 週報入選 Reddit 20／20；這裡 Reddit 13、論壇＋官方 7。新增的請求是討論串分頁 9 頁與 Lodestone 詳細頁 1 頁（舊設定沒有在同一環境計時，耗時差不報）。
**供應（SC-006 的錨點）**：候選池 45 篇，其中 13 篇是只有標題的論壇列表頁、25 篇是 Reddit；論壇版＋Lodestone 7 篇。

## T025 咬合實驗：五個承重的地方改壞，對的測試轉紅

**時間**：2026-10-20，worktree pin 在 `aef3800`（S1–S4 都已審過），一次改一處、跑 CI 那組 unit（492 條），改完 `git checkout` 還原，
最後 `git status` 乾淨。

| 改壞的地方 | 結果 | 轉紅的測試 |
|---|---|---|
| PLL 權重 100 → 10（T015 的字面值） | 1 failed | `test_pll_priority.py::test_pll_enters_alongside_newer_reddit` |
| 排序鍵拿掉權重項 | 5 failed | `test_ffxiv_ranking.py` 的排序鍵 2 條、取前 20、兩行 log；`test_pll_enters_alongside_newer_reddit` |
| 拿掉去重前排序 | 2 failed | `test_ffxiv_filter_order.py::test_higher_weight_duplicate_survives_dedupe`（同標題、包含關係兩組） |
| 拿掉 `dedup_key` 略過標題指紋 | 2 failed | `test_forum_dedup_key.py` 的保留與 log 兩條 |
| 窗口改回「現在往前 7 天」 | 12 failed | `test_vb_forum_window.py` 6 條、`test_vb_forum_collect.py` 6 條（邊界、真實頁面） |

每一項紅的都是守那件事的測試，沒有無關的測試跟著紅。

## T027 prod 變數換上新設定（merge 之後）

**時間**：2026-10-20 約 13:35Z（台灣 21:35，週二），`#174` merge 後（`e91af28`）。Luke 同意由 main 執行。

- 寫入前重讀 prod 的 `SOURCES_FFXIV_YML`：與 12:59Z 讀到的逐位元組相同（期間沒人改）；改前的值備份在 session scratchpad。
- `gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.example.yml`，再
  `gh variable get … | diff - config/sources_ffxiv.example.yml`：無差異（逐位元組相同）。
- 本機 `config/sources_ffxiv.yml` 換成同一份；`scripts/check_config_drift.py` 四組都是「相符」。
- 下一次 daily 漂移檢查是 10-21 00:00Z；第一個用到新設定的週報是 10-26（週驗收 routine 照 `FOCUS.md` (7)）。
