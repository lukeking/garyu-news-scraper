# 實驗：`gemini-3.8-flash`（現行）與 `gemini-4-carbon`

**日期：** 2026-11-12（TW）  **分支：** `docs/model-quality-3p8-carbon`  **BACKLOG：** `GNS-20261019-1vk`
**問題：** `gemini-4-carbon` 11-10 GA。它值不值得換掉 prod 的 `gemini-3.8-flash`（熱點、彙整、FFXIV、auto-KB 共用 `GEMINI_MODEL_NAME`）。

這是 PR `#74`、`#90`、10-19 那輪（`../model-quality-3p8flash-vs-argon/`）之後的第四輪，但素材與判準換了，數字不跟前幾輪比（見「為什麼不沿用 08-10 快照」）。

---

## 比較對象（11-12 查證）

| | id | 狀態 | 定價 in/out（/1M，output 含 thinking） |
|---|---|---|---|
| 現行 | `gemini-3.8-flash` | GA，prod 在跑 | $0.75 / $3.75 到 2026-12-31，之後 $1.50 / $7.50 |
| 挑戰者 | `gemini-4-carbon` | GA（官方 changelog 2026-11-10，「our most capable reasoning model」，沒有標 flash／pro） | $2 / $10 到 2026-11-30，之後 $4 / $20 |
| 裁判 | `gemini-2.5-pro` | 官方 changelog 2026-11-02 公告 deprecated，**2026-12-01 起轉給 `gemini-3.8-flash`** | $1.25 / $10（prompt ≤ 200k） |

出處：`aistudio.google.com/docs/changelog` 與 `aistudio.google.com/docs/pricing`（`ai.google.dev` 的兩頁 301 轉到這裡），11-12 抓取。
carbon 的單價與 argon 相同，兩個時段都是 3.8 的 2.67 倍。

## 為什麼不沿用 08-10 快照（Luke 11-12 裁示）

- spec 018 在 10-19 之後改寫了三軸指令（`e611bd7`、`e66db8b`、`10b994f`）：10-19 那輪 3.8 的存檔是舊指令的輸出，不能當對照組，3.8 也要重生成。
- 08-10 快照的三桶全是政策類（機車左轉政策、路權政策、道安政策）送進三軸指令；照現行指令 A 軸會寫「本批無事故報導，不適用」（推論），
  018 改最多的六類判定量不到，prod 每週跑的彙整範本也量不到。
- 舊的評分準則是照 018 之前的指令寫的（例：「觸發制紀律：政經(§二)」）。

## 方法

- **素材**：018 重播 fixture 用過的 9 份已發布報告，`scripts/replay_report_review.py` 的 `load_inputs` 從 prod 唯讀重建輸入
  （9 份都是 `reconstructed`），凍結在 `data/inputs.json`：
  - 彙整 3 份：10-19、10-26、11-02「道安政策 · 彙整」（各 25 篇）。
  - 三軸 6 份：08-03「機車事故 · 中時」、09-07「機車事故 · TVBS」、09-21「行人事故 · 行人」、10-26「機車事故 · 機車」、
    09-14「道安政策 · 交通安全」、10-19「科技執法 · 新聞」。
- **生成**：走重播腳本的 `regenerate`（真的 `analyze_hot_topic`／`analyze_category_digest`，現行指令），每模型每份 2 次。
  每次記 `modelVersion`（開頭對不上就停）、`usageMetadata`、`finishReason`。
- **Gate**：每次輸出跑 `check_report()`，逐次照實列出各類計數。`date_unlabeled` 已知誤判多（018 `evaluation.md` SC-001 節），
  命中由 main 逐條判（Luke 2026-11-08 對 018 的裁示）。
- **品質**：`gemini-2.5-pro` 盲評、位置對調，9 份 × 2 run × 2 位置 = 36 次。裁判看到的來源清單就是生成時的 `input_text`，逐字相同
  （上一輪裁判只看到 200 字、生成拿 600 字，見 BACKLOG `1vk` 節）。評分準則照現行三軸與彙整指令改寫（三軸 5 軸、彙整 4 軸，
  全文在 `scripts/quality_ab.py` 的 `RUBRIC`），開跑前 Luke 11-12 核過。carbon 比裁判強、又同屬 Gemini，所以照 argon 那輪的做法，
  由 Claude 在 session 裡做跨家族抽查。
- **兩批 carbon**（11-12 跑的時候改的）：第一批照 prod 的呼叫設定（`GEMINI_MAX_OUTPUT_TOKENS` 沒設＝8192、`_call_gemini` 的 timeout 120 秒），
  18 次有 4 次 thinking 用完 8192、輸出是空的。Luke 指出 carbon 的同步輸出上限是 65,536，於是 carbon 用 `QAB_CARBON_MAX_OUT=65536`
  全部 18 次重跑（只補失敗的 4 次會混到兩種設定），timeout 放寬到 600 秒——**這兩個值與 prod 呼叫路徑不同**，每筆記錄的 `sent` 是實際送出的值。
  盲評與成本用 65536 那批；8192 那批只當「照 prod 現行設定過不了 Gate」的證據（`q_report.md`、`q_run_gemini-4-carbon.json`）。
- **裁判的設定**：前 3 次裁決照 prod 的 8192／120 秒；第 4 次起改成 65536／600 秒——第 4 次的 sentinel 遇到 2.5-pro 自己想到 8192 用完、
  回應沒有 parts，`_call_gemini` 丟 `KeyError`。前 3 次都是 `STOP`、沒撞上限，所以保留。
- **成本**：算全部呼叫端。熱點＋彙整每週 3 次（近週上界；11-09 是熱點 1、彙整 1），FFXIV 每週 30 次（`ffxiv.max_selected`，11-11 起；11-09 是 20 次）。
  FFXIV 的單次成本用真的 `FFXIVCategory().collect()` 與 `.filter()` 即時取 5 篇，兩個模型各跑一次 `analyze_article`（只量成本）。auto-KB 沒量。

## 決策閘門（沿用前幾輪的階梯）

| 階 | 判準 | 意義 |
|---|---|---|
| **Gate** | 生成可用、`modelVersion` 相符、沒有 `MAX_TOKENS` 截斷、`check_report()` 判定後的錯型不比 3.8 多 | 不過就不換 |
| **L1 非劣** | 盲評勝率 40–60%，且沒有任何一軸落後超過 0.3 | 只在有營運理由時才換 |
| **L2 明確勝出** | 勝率 ≥ 65%，或逐軸平均領先 ≥ +0.3 | 以品質為由換 |
| **成本** | 每份報告與每月的實測成本 | carbon 比較貴，要到 L2，且月成本在 NT$300 上限內 |

不論結果，prod 在 11-23 那份週報之前不換：11-16、11-23 是 019 SC-001、SC-004 連兩週 Gate 的樣本（agent 的提案，Luke 11-12 照這個做法核准評比）。

**證據等級**：可用性、`modelVersion`、`finishReason`、`check_report()` 計數、成本、token 量是實測；品質分數是判斷（模型裁判只答相對差距）。

## 讀寫範圍與費用

- 讀：prod `hot_topic_reports`、`articles`（重建輸入）、FFXIV 來源（HTTP）、跨週指紋與 `knowledge_base`（select）。
- 寫：只寫本目錄的 `data/`。
- 計費：本機 key 就是 prod key，吃同一個 NT$300 月上限。開跑前估計 US$3–5（推論）；腳本記到的約 US$4.7
  （生成三批約 $2.7、裁判 $1.79、FFXIV $0.21、兩次探針），是下限——逾時被放棄的嘗試沒記到，總額以後台為準。

## 重現

```bash
.venv/bin/python experiments/model-quality-3p8flash-vs-carbon/scripts/quality_ab.py all
# 或分段：inputs | run | judge | ffxiv_freeze | ffxiv_cost | report（run 與 judge 中斷後重跑會接著做）
```

開跑前在 scratchpad 乾跑過：換掉 Gemini 的 HTTP 回應、輸出寫到別處，跑真入口。生成 36 次、裁判 36 次全部可解析；每份 `input_text` 都在實際送出的生成與裁判 prompt 裡；
假裁判照已知答案只判帶 carbon 標記的那份勝，結果 carbon 36 勝、兩種位置各 18、每軸差 +2.00（對調後換回模型的對應是對的）；
carbon 回錯的 `modelVersion` 時印 `STOP` 結束、carbon 那一筆沒有寫入。

## 結果（2026-11-12 跑；全部數字在 `data/q_report_max65536.md`，prod 設定那批在 `data/q_report.md`）

**決策交給 Luke**：carbon 的三軸品質到 L2，但換它要改 prod 的輸出上限與 timeout（`_call_gemini` 寫死 120 秒），成本約 4 倍、週報變慢；
彙整只到 L1。prod 在 11-23 那份週報之前不換（見閘門那節）。下面是讀數與 agent 的提案。

### Gate

| | 生成 | 空輸出（`MAX_TOKENS`） | 超過 120 秒 | `check_report()` 判定後的真錯 |
|---|---|---|---|---|
| 3.8（prod 設定） | 18 | 0 | 0 | 2（都在 10-19 彙整 run2，見 `data/date_unlabeled_adjudication.md`） |
| carbon@8192（prod 設定） | 18 | **4** | 2 | 沒判（這批只量截斷） |
| carbon@65536 | 18 | 0 | **5**（2 次超過 600 秒，中間有重試） | 0 |

- `check_report()` 其他五類兩個模型都是 0；`date_unlabeled` 原始命中 3.8 31 條、carbon@65536 28 條，逐條判完分別是 2 條、0 條真錯。
- carbon 單次的 output＋thinking 最多 19,253（09-07 TVBS run1，thinking 18,471），8192 的上限擋不住。
- **照 prod 現行設定，carbon 過不了 Gate**；放寬到 65536 才過，但延遲也過不了 prod 的 120 秒 timeout。

### 盲評（3.8 對 carbon@65536，36 次全部可解析）

| | carbon 勝 | 3.8 勝 | 平手 | 位置一致 | 逐軸差（carbon − 3.8） | 階 |
|---|---|---|---|---|---|---|
| 三軸（24 次） | 21（88%） | 2 | 1 | 9／12 對 | +0.33～+1.29（分類與因果解構 +1.29、文本依據 +1.00） | **L2** |
| 彙整（12 次） | 6（50%） | 5 | 1 | 2／6 對 | −0.08～+0.08 | **L1**（位置偏誤重：排在 A 的勝 8 次、B 3 次） |

- 彙整的格式遵循兩個模型都只有 2.3 分左右，同一個方向、不影響比較；推論是 rubric 寫「概覽不寫篇數」而程式會另外寫入篇數，沒查證。
- **跨家族抽查**（`data/spot_claude.md`，揭盲前寫定；`data/spot_key.json`）：事故類三軸 3 份 run1，carbon 3 勝。與裁判一致的地方：
  3.8 三份的人因變數都沒標 Article ID、09-07 把寫到道路條件的事故全歸 [工程資料未載]。抽查看到而裁判沒有扣分的：carbon 第三段兩次推論過頭
  （09-07 寫成機關動機、09-21 加了沒有依據的「時間窗口操縱」），篇幅也長得多。盲的程度有限（字數洩漏身分），抽查記錄裡寫明了。

### 成本與延遲（腳本記到的是下限）

| | 三軸 $/份 | 彙整 $/份 | FFXIV $/篇 | FFXIV 均秒數 | 月成本上界 now／12-01 之後 |
|---|---|---|---|---|---|
| 3.8 | $0.0145 | $0.0197 | $0.0090 | 15.9 | $1.40／$2.81 |
| carbon@65536 | $0.0751 | $0.0553 | $0.0338 | 36.7 | $5.26／$10.52 |

- 月成本照每週熱點＋彙整 3 次、FFXIV 30 次算（上界）；FFXIV 照 11-09 的 20 次算，carbon 12-01 之後約 $7.6。
- **下限的意思**：client 端逾時放棄的嘗試伺服器照樣算完、照樣計費，usage 卻回不到腳本。carbon@8192 那批 08-03 run2 花 491.6 秒，
  Luke 在後台看到 21:01（+0800）一個點 17.51K output，對得上那一筆結束的時間；單次上限 8192，所以那是不只一次嘗試的合計（推論）。
  總花費以後台為準。另有一次 carbon 原始回應的探針：`parts[0]` 同時帶 `text` 與 `thoughtSignature`（5,868 字），`_call_gemini` 只讀 `text`；
  thinking 的計費量在 `thoughtsTokenCount`，腳本有算。
- FFXIV 每週 30 次 × 36.7 秒約 18 分鐘，019 FOCUS 的「總耗時 ≤ 20 分」會吃緊（推論，沒跑整份週報）。

### agent 的提案（Luke 未裁示）

- **熱點分開換**：三軸差距大、每週只 1–2 次；FFXIV 是呼叫量的大頭、這輪沒評品質；彙整只到 L1。讓三軸讀自己的模型設定、
  只把它換成 carbon，月成本約多 $1，其餘留在 3.8。要改 code（`GEMINI_MODEL_NAME` 現在是全部呼叫端共用）並放寬那一條路徑的輸出上限與 timeout。
- **`_call_gemini` 遇到沒有 parts 的回應會丟 `KeyError`**（`src/analyzer.py:538`）：thinking 用完上限、一個字都沒輸出時，不是回空字串而是例外。
  這輪是裁判撞到的；prod 的模型只要想到撞上限就會走到這條路。要不要開一列由 Luke 決定。
- 這套 framework 的裁判 `gemini-2.5-pro` 12-01 起被轉給 3.8-flash，下一輪要換裁判。
