# 實驗：`gemini-2.5-pro` vs `gemini-3.6-flash`（熱點深度分析品質）

**日期：** 2026-07-24／25（TW）  **分支：** `docs/model-quality-experiment`
**問題：** 把週報熱點分析的 LLM 從 prod 現用的 `gemini-2.5-pro` 換成 `gemini-3.6-flash`，
**產出的內容品質會不會有顯著不同？**（成本／速度為次要參考。）

## TL;DR

在**厚政策桶**上做 3-run 盲評（position-swapped，非參賽第三方模型評判）：**品質有可偵測、
方向一致的差距，但幅度 modest——而且是 flash 略勝，不是 pro。** flash 拿下 **11/18 勝**
（pro 7），逐軸平均 **4.72 vs 4.43**。主因是 pro 傾向 **over-reach**（把國外原則張冠李戴、
混淆縣市數據、在嚴格觸發段臆測），而這條 prompt 的 rubric 正好獎勵 flash 的**克制**。
flash 同時在厚政策內容上**便宜 ~35%**。

→ **這推翻了 Stage 1 的初步印象**（薄 blotter + 肉眼以為 pro 稍深）。**換 flash 品質不會退、
可能小升，成本再降**——但這是單週 3 桶、單一 Gemini-family judge 的 spike 結論，rubric 偏好克制；
換個重視「全面性」的 rubric 或跨家族 judge 可能翻盤。

---

## 方法（route A — 隔離模型為唯一變因）

- **同一份輸入**：從 live buffer（唯讀正式站）取真實 bucket，**凍結成快照**後才跑，
  避免 live buffer 在跑的期間漂移。兩個模型吃**位元組完全相同**的 prompt。
- **同一份 prompt**：直接呼叫 `src/analyzer.py::analyze_hot_topic`（`HOT_TOPIC_PROMPT_TEMPLATE`
  ＋`HOT_TOPIC_SYSTEM_PROMPT`），與 prod 週報同一條 code path。
- **只換模型**：`analyzer.GEMINI_MODEL` 在 process 內明寫切換（不靠 env，避免漂移）。
- **端點相同**：兩者都走 `generativelanguage.googleapis.com` key-based 端點、同金鑰、同 project。
- **零 DB 寫入**：只讀 buffer、呼叫 Gemini、寫本地檔。

### 為什麼 route A 才乾淨（本地跑 vs prod 跑的變因）
要比較的是「模型」，就必須把其他變因全部按住。實測列出的變因與處置：

| 變因 | 說明 | route A 如何消除 |
|---|---|---|
| 模型 id | prod 由 GH env var 決定 | 兩模型都當場明寫 |
| 輸入文章 | prod 報告來自過去某週的 buffer，且只存 links 不存正文 | 凍結當前 buffer 快照，兩模型共用 |
| Prompt 版本 | 歷史報告用當時的 prompt | 兩邊都用現在的 code |
| Pipeline 版本 | 分群/計分邏輯會變 | 同一次 process |
| 生成參數 | `GEMINI_MAX_OUTPUT_TOKENS` 等 | 同 process、同設定 |
| 端點/金鑰 | — | 相同 |
| 取樣非決定性 | `temperature=0.2`（非 0）+ 浮動 alias | **無法完全消除** → Stage 2 用每桶多次取樣 + 盲評壓噪 |

---

## 關鍵操作發現（值得記錄）

1. **prod 跑的確實是 `gemini-2.5-pro`。** `gh variable get GEMINI_MODEL_NAME --env production`
   ＝ `gemini-2.5-pro`；`GEMINI_MAX_OUTPUT_TOKENS=8192`（＝程式碼 default）。
2. **本地 `.env` 的 `GEMINI_API_KEY` 是 free tier（刻意，避免誤噴）。** 因此本地跑
   `gemini-2.5-pro` 會 429（quota metric＝`generate_content_free_tier_input_tokens`）；
   `gemini-3.6-flash` free tier 可跑。實驗期間**暫時換成 paid key**、跑完換回。
   → prod 用的是另一把 paid key（GH secret），**不受影響**。
3. **模型 id 已用 ListModels 端點證實**：`gemini-3.6-flash` 確存在於此 key-based 端點
   （exact id，非 preview 尾綴），支援 `generateContent`。（見 `scripts/list_models.py`）
4. **兩個模型都是 thinking model，且程式碼沒設 `thinkingConfig`** → 都用**預設 dynamic thinking**。
   這與 prod 一致（prod 也沒設）。thinking token 以 output 費率計費，是成本主因（見下）。

---

## 定價（2026-07-24，取自 ai.google.dev/gemini-api/docs/pricing）

| 模型 | input /1M | output /1M | 備註 |
|---|---|---|---|
| `gemini-2.5-pro` | $1.25（≤200k）/ $2.50（>200k） | $10.00 / $15.00 | 無 free tier |
| `gemini-3.6-flash` | **$1.50** | **$7.50** | 有 free tier |

**反直覺點：** flash 的 **input 比 pro 貴**（$1.50 > $1.25），只有 output 便宜（$7.50 < $10）。
Batch tier 兩者對半（pro out $5 / flash out $3.75）——週報不在乎延遲，這是比換模型更大的省錢槓桿。

---

## Stage 1 — Spike（blotter top-3，快速探路）

輸入＝當前 buffer 分數最高的 3 桶（**全是 機車事故 blotter**，見 `01-spike-blotter-top3.md`）。
每模型每桶 1 次。目的是打通流程 + 拿真實 token/成本，**不足以下品質定論**。

**成本（實測 usageMetadata × 定價）**

| | in tok(均) | out tok(均) | **think tok(均)** | $/報告 |
|---|---|---|---|---|
| `gemini-2.5-pro` | 1867 | 543 | 2886 | **$0.0366** |
| `gemini-3.6-flash` | 1867 | 448 | **3262** | **$0.0306** |

- **thinking token 佔計費 output 的 ~80–85%**，是成本主體。
- **flash 不是「便宜很多」**：input 較貴 + thinking 甚至比 pro 多 → 全程只**便宜 ~16%**，
  在政策桶只便宜 ~11%。
- **量級校正：** 使用者實測**約 $3 USD/月**（週跑一次）。本 spike 推估偏低，因為
  spike 的 blotter 桶特別薄（input 才 1600–2100 tok）且沒算 digest 呼叫（digest 吃到 15 篇）。
  → **成本不是換模型的理由**；真要省先看 batch tier / 限制 thinking budget。

**品質（弱證據）：** 格式遵循兩者皆 3/3、7/7 完美；pro 因果稍深、較 verbose；flash 較精簡、
偶爾較保守。差異不明顯，但 n=1 + blotter 太薄，**不能當結論**——催生了 Stage 2。

---

## Stage 2 — 政策桶品質實驗（含 blind judge）

**動機：** 使用者在意的是**品質是否顯著不同**，而 Stage 1 的 blotter 太薄、n=1 無法回答。

**設計：**
- **輸入 = 3 個 rich policy 桶**（見 `data/policy_snapshot.json`）：
  - `B1_機車左轉政策`：自然 cluster（直接左轉/免待轉政策辯論，會觸發官方論述偏誤）。
  - `B2_路權政策`：category pool（禁行機車/兩段左轉/路權鬆綁，top-10）。
  - `B3_道安政策`：category pool（報導者/天下 深度 Vision-Zero，top-10）。
  - （buffer 政策內容真實但零散成 singleton，故 B2/B3 用 digest-sized pool 湊出richness。）
- **每模型每桶跑 `N=3` 次**（分離模型訊號與 temp-0.2 取樣噪音）。
- **盲評第三方模型 `gemini-3.1-pro-preview`**（非參賽者，降低自我偏好）：
  對 (pro run_k, flash run_k) 成對評分，**位置對調**（A/B 兩序各一次）消除位置偏誤，
  逐軸 0-5 分（格式遵循／文本依據／因果解構深度／觸發制紀律／轉譯紀律）＋勝方。
  → 3 桶 × 3 run × 2 序 = **18 次裁決**。

**結果（18 次盲評，位置對調後；詳細並排見 `02-policy-quality-judged.md`）**

勝負：**flash 11 / pro 7 / tie 0**（flash 61%）。逐軸平均（0-5）：

| 軸 | `gemini-2.5-pro` | `gemini-3.6-flash` | 差 |
|---|---|---|---|
| 格式遵循 | **4.94** | 4.83 | +0.11 |
| 文本依據 | 4.33 | **4.56** | −0.22 |
| 因果解構深度 | 4.17 | **4.72** | −0.56 |
| 觸發制紀律 | 4.17 | **4.56** | −0.39 |
| 轉譯紀律 | 4.56 | **4.94** | −0.39 |
| **總平均** | 4.43 | **4.72** | **−0.29** |

成本（厚政策桶，9 生成/模型）：pro **$0.3924**（$0.0436/報告，均 744 字）；
flash **$0.2546**（$0.0283/報告，均 546 字）→ flash **便宜 ~35%**（比 Stage 1 blotter 的 16% 更大，
因為 pro 在厚內容上更 verbose）。

**判讀**
- **flash 略勝的主因是 pro over-reach**：judge 反覆點名 pro「把國外原則張冠李戴到在地新聞、
  混淆台中/台南數據、在 §三 過度觸發無文本依據的偏誤」。flash 在**觸發制紀律**與**轉譯紀律**
  逐軸領先，且 judge 常評 flash「更深且更聚焦」。
- **非壓倒性**：pro 在 B1 run2 兩序皆勝（多來源綜合、深度）。存在真實 run-to-run 變異——
  pro 的 verbose 有時被讀作深度、有時被讀作 over-reach。**格式**上 pro 略優（flash 偶有合併換行瑕疵）。
- **位置偏誤**：swap 在個別 run 揭露「先出現者佔優」（如 B2 run1/run2 同一對、不同序 → 不同勝方）；
  但 pro-first／flash-first 各半，**在總計中相互抵消**——故 11-7 與 +0.29 是**位置無關**的真實訊號。

**顯著性判定**
- 差距**可偵測、方向一致（favor flash）**，但**幅度 modest**（61/39、mean 差 0.29 ≈ 6%），非決定性；
  兩模型各軸皆 4.1–4.9，皆強。
- **方向出乎意料**：更貴的 pro 沒有比較好。關鍵在於**這條 prompt 的 rubric 獎勵「克制/嚴格觸發」**，
  正好是 flash 的長處——若換一條重視「全面涵蓋」的 rubric，可能翻向 pro。

---

## 誠實邊界（證據等級）

- **E1（實測）：** 所有 token/成本、格式機械檢核、模型可用性、prod 設定值。
- **E3（判斷）：** 品質評分——即使用盲評第三方模型，仍是模型判斷，非客觀真值；
  只用來回答「**相對**上是否有顯著差距」，不宣稱絕對品質。
- 全實驗仍是 **spike 等級**：單週 buffer、政策內容偏少（buffer 本身的結構限制）。
  結論可推翻預期即為有用，不作為長期採購決策的唯一依據。

---

## 重現

```bash
# 需 .env 內 GEMINI_API_KEY（paid tier 才能跑 2.5-pro）、SUPABASE_* 唯讀
.venv/bin/python scripts/list_models.py      # 確認模型 id 在此端點可用
.venv/bin/python scripts/scout_buckets.py    # 看 buffer 的政策桶分佈
.venv/bin/python scripts/quality_ab.py all   # freeze→run→judge→report
```

> 註：`scripts/*.py` 的 `OUT`/路徑為當時 session 的 scratchpad 絕對路徑（存證用，非可攜）。
> `model_ab.py`＝Stage 1 harness；`quality_ab.py`＝Stage 2 harness（含 judge）。
