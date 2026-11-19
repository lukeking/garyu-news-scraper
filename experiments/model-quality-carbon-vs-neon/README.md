# 實驗：三軸用 `gemini-4-carbon` 還是 `gemini-4-neon`

BACKLOG `GNS-20261019-1vk`。要回答的問題只有一個：11-23 週報之後，三軸（交通熱點）的 `GEMINI_MODEL_HOT_TOPIC` 設 carbon 還是 neon。
彙整、FFXIV、auto-KB 三條呼叫端留在 `gemini-3.8-flash`（已定 2026-11-13，見 `1vk` 那一節），這一輪不評。

## 比較對象（2026-11-19 查證）

| 角色 | 模型 | 狀態 | 定價（input / output，USD 每 1M tok） |
|---|---|---|---|
| 對照 | `gemini-4-carbon` | 上一輪對 3.8 到 L2，是三軸預定要換的模型；這一輪不重生成，用 11-12 的存檔 | $2 / $10 到 2026-11-30，之後 $4 / $20 |
| 挑戰者 | `gemini-4-neon` | GA（官方 changelog 2026-11-18） | $3 / $15，定價頁沒有列改價 |
| 裁判 | `gemini-2.5-pro` | deprecated，2026-12-01 起轉給 `gemini-3.8-flash` | $1.25 / $10（prompt ≤ 200k） |

changelog 與定價頁是 2026-11-19 經摘要工具讀的，不是逐字讀。changelog 另有 `gemini-4-hydrogen` 2026-11-12 GA，這一輪沒有納入。

## 範圍（已定 2026-11-19）

上一輪（`experiments/model-quality-3p8flash-vs-carbon/`）是 54 次生成、36 次裁決、10 次 FFXIV，記到約 US$4.7。這一輪縮成 24 次呼叫：

- **素材**：上一輪凍結的 9 份裡事故類三軸的 4 份——08-03「機車事故 · 中時」、09-07「機車事故 · TVBS」、09-21「行人事故 · 行人」、
  10-26「機車事故 · 機車」。`baseline` 子命令從上一輪的 `data/` 抄出這 4 份輸入與 carbon@65536 的存檔，不讀資料庫。
- **生成**：只生成 neon，每份 2 次，共 8 次。走重播腳本的 `regenerate`（真的 `analyze_hot_topic`），模型、輸出上限、timeout 經三軸路徑自己的
  環境變數送：`GEMINI_MODEL_HOT_TOPIC`、`GEMINI_HOT_TOPIC_MAX_OUTPUT_TOKENS=65536`、`GEMINI_HOT_TOPIC_TIMEOUT_SECONDS=600`，與 carbon 存檔那批送出的值相同。
- **裁判**：`gemini-2.5-pro` 盲評、位置對調，4 份 × 2 run × 2 位置 = 16 次。評分準則、裁判的 system prompt 與版型和上一輪逐字相同（用 `ast` 比對過兩支腳本的常數）。

**存檔的 carbon 為什麼能當對照**：`HOT_TOPIC_PROMPT_TEMPLATE`、`HOT_TOPIC_SYSTEM_PROMPT`、`HOT_SUMMARY_CHARS`、`build_hot_topic_input` 與整支
`scripts/replay_report_review.py`，在上一輪分支的 tip `2fd019f` 與這一輪的基準 `c592a87` 之間逐字相同；`analyze_hot_topic` 與 `_call_gemini` 只多了模型、
輸出上限、timeout 的參數與沒有 parts 時的處理。`run` 另外逐次比對 neon 看到的清單與存檔的 `input_text`，不同就停。

**沒有比的**：neon 對 3.8 沒有直接比（上一輪 carbon 對 3.8 是 L2）；彙整、FFXIV、auto-KB；政策類與科技執法的兩份三軸；neon 的 thinking level 只跑預設值。

## 決策閘門（階梯沿用前幾輪；結果怎麼用是提案）

| 階 | 判準 | 意義 |
|---|---|---|
| **Gate** | 8 次生成都可用、`modelVersion` 相符、沒有 `MAX_TOKENS` 截斷、`check_report()` 判定後的錯型不比 carbon 多 | 不過就照原訂換 carbon |
| **L1 非劣** | 盲評勝率 40–60%，且沒有任何一軸落後超過 0.3 | 品質分不出來，看成本與耗時 |
| **L2 明確勝出** | 勝率 ≥ 65%，或逐軸平均領先 ≥ +0.3 | 以品質為由選 neon |
| **成本與耗時** | 每份三軸的實測成本（12-01 起的價格）與單次秒數 | 耗時要對 `weekly-traffic.yml` 的 `timeout-minutes: 25` 算 |

16 次裁決來自 4 份輸入，樣本小；勝率落在 60–65% 之間照 L1 讀。**證據等級**：可用性、`modelVersion`、`finishReason`、`check_report()` 計數、成本、
token 量、秒數是實測；品質分數是判斷（模型裁判只答相對差距，而且兩個受測模型都比裁判新）。

## 讀寫範圍與費用

- 讀：上一輪的 `data/inputs.json` 與 `data/q_run_gemini-4-carbon_max65536.json`。不讀資料庫、不抓來源。
- 寫：只寫本目錄的 `data/`。
- 計費：本機 key 就是 prod key，吃同一個月上限（2026-11 的上限在上一輪中途調高過，預定 12 月調回）。開跑前估計約 US$1.7（推論：carbon 的三軸每份
  $0.0751 乘 1.5 倍價差，加上一輪每次裁決約 $0.05）。腳本記到的花費到 `QAB_USD_CAP`（預設 US$2.5）就不再呼叫；`GEMINI_MAX_RETRIES` 壓到 2
  （prod 預設 8），每筆記錄帶 `attempts` 與 `failed_attempts`——逾時被放棄的嘗試沒有 usage，照樣可能計費。

## 重現

```bash
Q=experiments/model-quality-carbon-vs-neon/scripts/quality_ab.py
.venv/bin/python $Q baseline   # 抄對照組，不呼叫 API
.venv/bin/python $Q run 1      # 先跑 1 次當 sentinel；不帶數字就跑到 8 次為止，中斷後重跑會接著做
.venv/bin/python $Q judge
.venv/bin/python $Q report     # 寫 data/q_report.md
```

開跑前在 scratchpad 乾跑過（把 `requests.post` 換成假回應、`QAB_OUT` 指到別處，跑真入口）：24 次呼叫裡 8 次送 `gemini-4-neon`、16 次送
`gemini-2.5-pro`，都是 maxOutputTokens 65536、timeout 600 秒；每份 `input_text` 都在送出的生成與裁判 prompt 裡；8 對報告各在兩個位置判一次。

## 結果（2026-11-19 跑；全部數字在 `data/q_report.md`）

24 次呼叫都一次成功，沒有失敗的嘗試。記到的花費 US$2.18（neon 生成 $1.40、裁判 $0.78），比開跑前估的 $1.7 高：生成是拿上一輪 6 份三軸的平均估的，
這 4 份事故類正好是 thinking 較重的幾份。

### Gate：過

| | 生成 | 空輸出或截斷 | 超過 120 秒 | 超過 600 秒 | `check_report()` 五項 |
|---|---|---|---|---|---|
| carbon@65536（11-12 存檔的這 4 份） | 8 | 0 | 3 | 1（09-07 第 2 次 746 秒，中間有重試） | 都是 0 |
| neon | 8 | 0 | 3 | 0（最長 172.5 秒） | 都是 0 |

- `modelVersion` 8 次都是 `gemini-4-neon`，`finishReason` 都是 `STOP`。
- 計數是兩邊都用現在的 `check_report()` 重算的。三軸的五項是 `missing_section`、`id_out_of_range`、`interweave_sum`、`replacement_new_number`、`deletion_over_cap`；
  上一輪的報告表欄名寫死成另外六項，後三項沒有列出來，這一輪改成照檢查實際回的名字列。

### 盲評：L1，裁判分不出來

| | neon 勝 | carbon 勝 | 平手 | 位置一致 | 逐軸差（neon − carbon） |
|---|---|---|---|---|---|
| 三軸 4 份（16 次，全部可解析） | 9（56%） | 7 | 0 | 3／8 對 | 格式遵循 −0.19、文本依據 +0.44、分類與因果解構 +0.06、觸發制紀律 +0.12、轉譯紀律 −0.06 |

- **位置偏誤重**：排在 A 的那份勝 13 次、排在 B 的勝 3 次。8 對裡 5 對的勝方跟著位置走；兩個位置判同一方的 3 對是 neon 2 對、carbon 1 對。
- 文本依據的 +0.44 全部來自 neon 排在 A 的 8 次（+0.88），carbon 排在 A 時是 0.00；分類與因果解構更明顯（−0.88 對 +1.00）。所以不拿單一軸的 +0.44 當 L2 的依據。
- 勝率在 40–60%、沒有一軸落後超過 0.3，照階梯是 L1。

### 跨家族抽查（`data/spot_claude.md`，揭盲前寫定；`data/spot_key.json`）

事故類 3 份的 run1（08-03 在 sentinel 時看過內文，沒有抽）：09-07 平手略偏 carbon、09-21 neon 小勝、10-26 neon 勝。兩邊都沒有對不回來源的句子。
neon 勝的那一份差在 carbon 的分布寫了 [工程未見放大] 1 篇卻沒說是哪一篇，另有一句斷言現場「僅靠紅綠燈號誌」。
盲的程度有限：抽查者事前看過兩邊的字數，事後兩個身分猜測都猜中，抽查記錄裡寫明了。

### 成本與耗時

| | $/份 到 11-30 | $/份 12-01 起 | thinking 最小～最大 | 輸出＋thinking 最大 | 均秒數 | 最長秒數 |
|---|---|---|---|---|---|---|
| carbon@65536 | $0.0979 | $0.1957 | 1,781～18,471 | 19,253（上限的 29%） | 186.9 | 746.1 |
| neon | $0.1753 | $0.1753 | 3,880～18,587 | 19,429（上限的 30%） | 99.8 | 172.5 |

- 12-01 起 neon 每份便宜約一成。三軸每週 1～2 次時，每月的生成成本是 carbon $0.85～$1.70、neon $0.76～$1.53。
- 兩個模型的輸出＋thinking 都有九成上下是 thinking；同一類輸入的 thinking 差到 10 倍，每份成本看範圍，不只看平均。
- 09-07 那一份是兩個模型都想最久的（carbon 18,471 與 10,808，neon 18,587 與 17,147），它的輸入只有 1,005 字。

### 這些數字的適用範圍

- **輸入規模**：這 4 份的生成輸入是 587～1,005 字（prompt 2,405～2,721 tokens）；三軸的理論上限約 6,600 字（10 篇 × 600 字摘要）。
  上一輪 carbon 的三軸 12 次裡，輸入字數對 thinking 的相關是 −0.19，輸入大小預測不了 thinking。
- **尾巴沒量到**：carbon 的三軸 12 次有 2 次是單次嘗試跑滿 600 秒才重試成功（746 秒、718 秒）；neon 8 次裡 0 次。如果 neon 的比例也是六分之一，
  8 次都沒遇到的機率約 23%，所以這一輪不能說 neon 沒有這個尾巴。跑滿 timeout 被放棄的嘗試照樣計費，usage 拿不到。
- **換工作量就不成立**：同一套設定（carbon、輸出上限 65536）用在另一個專案較重的工作量時，撞到 65536 的上限，放寬後單次超過 500K tokens、八九成是 thinking，
  一個階段跑了 20 分鐘沒有跑完（2026-11-19 得知的觀測，不是這個 repo 量的）。這裡量到的上限與 timeout 只對這裡的輸入成立。
- neon 對 3.8 沒有直接比；「neon 不輸 carbon、carbon 上一輪贏 3.8」是兩段接起來的推論。

### 對 prod 設定的含意（提案；定值在 `1vk` 剩下的那一步，11-23 週報之後）

- **模型**：傾向 neon（未定案，2026-11-19）——品質分不出來、12-01 起略便宜、這 8 次比較快。差距小，照原訂換 carbon 也說得通。
- **輸出上限留在 65536**：它同時是單次呼叫的費用上限，用滿時 neon 約 $0.98、carbon 12-01 起約 $1.31。量到的最大值是上限的三成。
- **timeout 與重試**：`weekly-traffic.yml` 沒有傳 `GEMINI_MAX_RETRIES`，prod 是預設的 8 次，單次呼叫最長是 timeout × 8——600 秒時 80 分鐘、300 秒時 40 分鐘，
  都超過那支 workflow 的 `timeout-minutes: 25`。觀測到成功的單次嘗試最長是 neon 172.5 秒、carbon 211.7 秒。提案：timeout 設 300 秒，不照評比用的 600 秒；
  三軸那條路徑的重試次數要不要另外設上限未定（要動 workflow 或程式）。

### 之後

- 裁判 `gemini-2.5-pro` 12-01 起被轉給 3.8-flash；這一輪它的位置偏誤也重到分不出勝負，下一輪要換裁判。
- `gemini-4-hydrogen`（2026-11-12 GA）沒有評，要不要評未定。
- 評比開跑前先提縮小的範圍與費用估計，核過才跑（已定 2026-11-19）。
