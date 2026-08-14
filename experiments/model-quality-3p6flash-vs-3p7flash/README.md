# 實驗：`gemini-3.6-flash`（現行）vs `gemini-3.7-flash`（挑戰者）

**日期：** 2026-08-14（TW）  **分支：** `docs/model-quality-3p7flash`
**問題：** `gemini-3.7-flash` 剛釋出。把週報/digest 的 LLM（＝「article 模型」，
`GEMINI_MODEL_NAME`，現行 prod＝`gemini-3.6-flash`）換成 `3.7-flash`，**產出品質會不會顯著改變？**
成本／速度為次要參考。

**這是 PR #74 框架的再跑一輪**（reopen trigger 泛化：原記「新 pro 釋出」，實際觸發者是新 flash；
現行既已是 flash，flash-vs-flash 是合理的一般化）。方法（route A）與 PR #74 逐字相同，只換
`MODELS` / `JUDGE` / `PRICING`。

---

## 比較對象（全部 E1，對 live 端點證實 2026-08-14）

| | id | 端點可用 | 本機 free-tier 可跑 | 定價 in/out（/1M） |
|---|---|---|---|---|
| 現行 | `gemini-3.6-flash` | ✓ generateContent | ✓ | $1.50 / $7.50 |
| 挑戰者 | `gemini-3.7-flash` | ✓ generateContent、GA（無 -preview） | ✓（實測） | $1.50 / $7.50 |

**關鍵前提：兩者定價逐字相同** → **成本軸退化為「每篇 token 量」（尤其 thinking token），
不是費率差**。兩者皆 free 至 2026-12-31，之後同價；Batch/Flex 皆 50%。
→ 決策實質由**品質**主導，$/報告 僅在 thinking 用量明顯不同時當次要 tiebreak。

同世代小改版，預期差距**遠小於** PR #74 的 pro-vs-flash（4.43 vs 4.72）；當時決定勝負的
「pro over-reach」動態不一定重現。

## 方法（route A — 模型為唯一變因，與 PR #74 相同）

- **凍結快照**：從 live buffer（唯讀正式站）取 3 個 rich policy 桶（B1 自然 cluster、
  B2 路權政策 pool、B3 道安政策 pool），凍結後才跑，避免 buffer 漂移。兩模型吃**位元組相同**的 prompt。
- **同一 code path**：直接呼叫 `src/analyzer.py::analyze_hot_topic`（prod 週報同一條）。
- **只換模型**：`analyzer.GEMINI_MODEL` 在 process 內明寫切換（不靠 env）。
- **每模型每桶 N=3**（分離模型訊號與 temp-0.2 取樣噪音）。
- **零 DB 寫入**：只讀 buffer、呼叫 Gemini、寫本地檔（`data/`）。

## 兩層評審（judge）

- **Tier-1（本 script）＝`gemini-2.5-pro`**：非參賽、**跨世代**（2.5 ≠ 兩位 3.x-flash 參賽者），
  比同為 3.x 的 judge 更少「偏袒較新的同家族手足」風險。盲評、位置對調、逐軸 0-5。
  → 3 桶 × 3 run × 2 序 = **18 次裁決**。**需 paid key**（free tier 對 pro 會 429，PR #74 實測）。
- **Tier-2（頻外，只在邊界時觸發）＝跨家族**：若總計落在下方「非劣」帶（L1），把邊界裁決子集
  升級給**跨家族** judge（Claude in-session，或另備 key 的腳本化 judge）覆核。
  這正是 PR #74 誠實邊界點名的弱點（single Gemini-family judge），對同家族比較更該補。
  刻意不寫進 script → 保持單金鑰、只在需要時才付跨家族成本（階梯式）。

## 決策閘門（階梯；預設＝**維持現行**，除非挑戰者跨過門檻）

PR #74 沒有明確閘門（只結論「modest」）。本輪補上，依 decision-style「門檻用階梯、硬門檻與
加權分開、標證據等級」：

| 階 | 判準 | 意義 |
|---|---|---|
| **Gate（L0，E1 機械）** | 3.7 支援 generateContent（✓ 已證）、**格式無退步**、**無杜撰引證退步** | 不過 → 不換，回報退步 |
| **L1 非劣** | 盲評勝率落在 40–60%、且無任一軸落後 >0.3 | 只在有**營運理由**（成本/支援壽命）時才換 |
| **L2 明確勝出** | 勝率 ≥65% **或** 逐軸平均領先 ≥+0.3（favor 3.7） | 以品質為由換 |
| **成本（另計，E1）** | 實測 $/報告（＝token 量） | ≥L1 且更便宜 → 換；更貴 → 需到 L2 |

**證據等級**：可用性／機械檢核／成本／token 量＝**E1**；品質分數＝**E3**（模型判斷，只答
「相對」有無顯著差距，不宣稱絕對品質）。

## 誠實邊界

- **rubric 依賴**：此 prompt 的 rubric 獎勵「克制/嚴格觸發」；換一條重視「全面涵蓋」的 rubric
  可能翻盤。同家族小改版下，PR #74 的 over-reach 動態未必出現。
- **spike 等級**：單週 buffer、政策內容偏少（buffer 結構限制）。結論答「換不換（相對）」，
  非長期採購定論。
- **thinking token**：兩模型皆 default dynamic thinking（code 未設 `thinkingConfig`），
  以 output 費率計費、為成本主體。trivial 探針（n=1）3.7 反而略少（474 vs 518）——**弱訊號**，
  真實用量看 run。

---

## 重現

```bash
# 需 .env：GEMINI_API_KEY（跑 2.5-pro judge 需 PAID tier）、SUPABASE_* 唯讀
.venv/bin/python experiments/model-quality-3p6flash-vs-3p7flash/scripts/quality_ab.py all
# 或分階段：freeze | run | judge | report
```

- `run`（兩位 flash 參賽者）本機 **free tier 可跑**（實測）。
- `judge`（2.5-pro）**需 paid key**——跑前暫換 paid、跑完換回；prod 的 paid GH secret 不受影響。

## 結果（2026-08-14，週次 2026-08-10 快照 · buffer 660 · 18 有效裁決）

**TL;DR：品質是穩健的平手（E3），決策由 E1 成本/延遲承載 → 建議換 `gemini-3.7-flash`
（不是因為「更好」，是因為「等品質但更便宜、更快」）。**

### 品質（E3，2.5-pro 盲評、位置對調、18 裁決）

- 勝負：**3.6-flash 8 / 3.7-flash 7 / tie 3**（挑戰者 39%，去平手 47%）。
- 逐軸平均全在 **±0.06** 內；總平均 **4.19 vs 4.18（−0.01）**；格式 5.00/5.00。
- 逐桶：B1（singleton）偏 3.7、B2（n=35，最厚）偏 3.6 5/6、B3（n=16）平。
  但讀 judge 理由，B2 的偏好是**撞詞切割「略優/險勝」等髮絲級差距且對位置敏感**（swap 會翻），
  **非實質品質差**。→ 平手是穩健的，不是被單桶訊號蓋掉。

### 成本與延遲（E1，實測，判分無關）

| | $/9 報告 | $/報告 | thinking tok（典型） | 延遲 |
|---|---|---|---|---|
| `gemini-3.6-flash` | $0.2225 | $0.0247 | ~2000–2900 | 14–22s |
| `gemini-3.7-flash` | $0.1379 | $0.0153 | ~900–1600 | 5–9s |

→ **3.7 便宜 ~38% 且快 ~2×**，源自 thinking token ~半（費率相同）。引證數略少（3.9 vs 5.1）
但 fidelity 等同（文本依據 3.11 vs 3.17）。

### 閘門判定

- **Gate（L0，E1）：通過** — generateContent ✓、格式無退步（5.00=5.00）、無杜撰引證退步。
- **L1 非劣：達成** — 平手，無任一軸落後 >0.3。
- **L2 明確勝出：未達** — 3.7 非更優，是等同。
- **成本軸：達成** — ≥L1 且更便宜/更快 → 依閘門「換」。

**決策：換 `gemini-3.7-flash`。** 理由是 E1（成本 −38%、延遲 −半、newer GA 支援壽命較長，
呼應 PR #74「pro 太舊」的原始動機），**不是** E3 品質——品質是刻意記錄下來的平手。
延遲減半可能連帶紓解 STATE.md Open Q#3（週報 run 10m21s 超憲章 IV 10 分上限）——待實測確認。

### 誠實邊界

- **spike 等級**：單週、3 桶（1 個 singleton、1 個雙方共同杜撰）、N=3、單一 Tier-1 judge。
  品質＝相對 E3，非絕對。
- **Tier-2（跨家族）已跑 spot-check（B2，唯一有傾向的桶）**：結論是 **B2 的現行傾向為真、
  非同家族 judge 假象，但極小且機制清楚**——3.6 更一致地做出 rubric 承重的**撞詞切割 guard**
  （run2「絕非台灣傳統按車種側分之車種分流」、run3「非車種側分」），3.7 的切割略軟。
  **機制＝PR #74 動態重現**：rubric 獎勵闡述/嚴格切割，3.6 用 **~2× thinking token** 買到這個微優勢，
  3.7 以半算力交換這一絲 轉譯 polish、其餘等同。
  ⚠️ **此 spot-check 為 label-visible（非盲、未位置對調）**，故為「引文錨定的佐證讀」而非嚴謹盲判，
  仍是 E3、單一 judge。決策仍由 E1 成本承載——此發現只把「平手」精修成「rich 內容上 3.6 有微優、
  代價是 2× 算力」，不改變建議方向。
- **B3 雙方共同杜撰**（[7] 不存在的「新生禁行機車/事故降三成」）＝**與模型無關的 grounding 缺陷**，
  是 pipeline/來源資料問題，非選型因素。獨立記錄（見 STATE.md）。

### 換法（使用者操作）

prod `GEMINI_MODEL_NAME` 是 **production environment variable**（非 repo 檔）：
`gh variable set GEMINI_MODEL_NAME --env production`（值＝`gemini-3.7-flash`）→ `gh variable get` 比對。
（`gh variable set` 我被權限擋，需使用者執行。）無 repo config 檔需同步（此值非 `config/*.yml`）。

> 對照組物證＝`data/` 下 snapshot/run/judge JSON，**勿事後重算覆蓋**。
