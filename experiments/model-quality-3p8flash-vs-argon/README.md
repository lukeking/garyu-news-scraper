# 實驗：`gemini-3.8-flash`（現行，已被自動換上）與 `gemini-4-argon`

**日期：** 2026-10-19（TW）  **分支：** `docs/model-quality-3p8-argon`  **BACKLOG：** `GNS-20261015-8pg`
**問題：** prod 的 `GEMINI_MODEL_NAME` 寫 `gemini-3.7-flash`，但 2026-10-08 起 API 把 3.7 自動轉給 3.8，
所以之後的週報是 3.8 產生的，沒有評比過。要回答兩件事：3.8 比 3.7 有沒有退步；argon 值不值得它的價錢。
據此決定 prod 的值：留在 3.8、釘回 `gemini-3.6-flash`，或換 argon。

這是 PR `#74`、`#90` 那套 framework 的第三輪。

---

## 比較對象（10-19 查證）

| | id | 狀態 | 定價 in/out（/1M，output 含 thinking） |
|---|---|---|---|
| 舊現行 | `gemini-3.7-flash` | 叫不到（自動轉給 3.8）；用 PR `#90` 的存檔 | $1.50 / $7.50（PR `#90` 當時） |
| 現行 | `gemini-3.8-flash` | GA，prod 實際在跑 | $0.75 / $3.75 到 2026-12-31，之後 $1.50 / $7.50 |
| 挑戰者 | `gemini-4-argon` | GA（官方 changelog 2026-10-13） | $2 / $10 到 2026-11-30，之後 $4 / $20 |
| 裁判 | `gemini-2.5-pro` | models.get 200 | $1.25 / $10（prompt ≤ 200k） |

定價出處：`ai.google.dev/gemini-api/docs/pricing`（10-19 抓取）。兩個優惠期之內與之後，argon 的單價都是 3.8 的 2.67 倍。

## 方法（route A，與 PR `#90` 相同；差別如下）

- **不重新凍結**：沿用 PR `#90` 的快照（`../model-quality-3p6flash-vs-3p7flash/data/q_snapshot.json`，
  週次 2026-08-10），3.7 的輸出也讀那裡的存檔。10-19 實測：`analyze_hot_topic` 在 `770ed2a` 與現在送出的
  prompt（含 system prompt）三桶逐位元組相同；生成參數只差 API key 從網址移到 header。
- **兩組比較**：3.7（存檔）對 3.8、3.8 對 argon。每模型每桶 3 次，盲評＋位置對調，每組 18 次裁決。
- **`modelVersion`**：每次回應都記下來，開頭對不上要求的模型就停下（fail closed）。3.8 就是這樣無聲換掉 3.7 的。
- **裁判**：與 PR `#90` 相同（`gemini-2.5-pro`），3.8 對 3.7 那組才能跟 PR `#90` 比。argon 比裁判強、又同屬
  Gemini 家族，所以 argon 那組不論結果，都由 Claude 在 session 裡做跨家族抽查（Luke 10-19 裁示）。

## 成本：算全部呼叫端（Luke 10-19 裁示）

`GEMINI_MODEL_NAME` 同時給熱點／彙整、FFXIV 的 `analyze_article`、auto-KB 用，換它等於三條一起換。
品質只量熱點；成本三條都算。

- **每週呼叫次數**（實測，09-21～10-19 五次週報與近 3 次 auto-KB 的 log）：熱點 1–2 次＋彙整 1 次、
  FFXIV 20 次、auto-KB 0 次（近 3 週都「沒有未知術語，跳過 Gemini」）。
- **FFXIV 的單次成本**：即時抓 FFXIV 來源，照週報的篩選取前 5 篇，兩個模型各跑一次 `analyze_article`（實測，
  只量成本、不評品質）。FFXIV 的 prompt 帶整份知識庫，所以要讀正式庫的 `knowledge_base` 表（只 select）。
- **彙整的單次成本**用熱點代替（推論：彙整的輸入較多，會低估）。

## 決策閘門（沿用 PR `#90` 的階梯，每組各判）

| 階 | 判準 | 意義 |
|---|---|---|
| **Gate** | generateContent 可用、`modelVersion` 相符、格式無退步、無杜撰引證退步 | 不過就不換，回報退步 |
| **L1 非劣** | 盲評勝率 40–60%，且沒有任何一軸落後超過 0.3 | 只在有營運理由（成本、支援期限）時才換 |
| **L2 明確勝出** | 勝率 ≥ 65%，或逐軸平均領先 ≥ +0.3 | 以品質為由換 |
| **成本** | 每份報告與每月的實測成本 | ≥ L1 且更便宜就換；更貴要到 L2 |

- 3.8 對 3.7：3.8 已經在 prod。過不了 Gate 或 L1 時，退路是釘回 `gemini-3.6-flash`（沒有 deprecated，PR `#90` 判定與 3.7 平手）。
- 3.8 對 argon：argon 比較貴，要到 L2，而且換完的月成本要在 NT$300 的上限內。
- 不論結果，prod 的變數都要改成明寫的值——現在寫的 3.7 已經不是實際在跑的模型。

**證據等級**：可用性、`modelVersion`、機械檢核、成本、token 量是實測；品質分數是判斷（模型裁判只答相對差距）。

## 讀寫範圍與費用

- 讀：PR `#90` 的快照與存檔、FFXIV 來源（HTTP）、正式庫 `knowledge_base` 表（只 select）。
- 寫：只寫本目錄的 `data/`。
- 計費：本機 key 就是 prod key，吃同一個 NT$300 月上限。開跑前估計 US$1.0–2.4（含裁判），依 PR `#90` 的 token 量推算。

## 重現

```bash
.venv/bin/python experiments/model-quality-3p8flash-vs-argon/scripts/quality_ab.py all
# 或分段：run | judge | ffxiv_freeze | ffxiv_cost | report
```

開跑前在 scratchpad 做過乾跑：換掉 Gemini 的 HTTP 回應與知識庫、輸出寫到別處，跑真入口；正常路徑走完五段並產出報告，
`modelVersion` 對不上時 exit 1、錯的那筆不寫入。

## 結果

（待跑）
