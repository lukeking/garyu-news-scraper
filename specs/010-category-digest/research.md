# Research — 低頻類別聚合式深度分析（010）

Phase 0 產出。每項含 Decision / Rationale / Alternatives considered。
背景數據來源：2026-07-13 本地 read-only 重放（與 run 29217421005 log 分數完全吻合）。

## D1 — 觸發度量：有效篇數，而非分數總和

**Decision**: 觸發條件 = 池內 `initial_quality_score ≥ quality_floor` 的文章數 ≥ `trigger_count`。預設 `trigger_count: 10`、`quality_floor: 0.18`。

**Rationale**:
- 篇數可從 log 直接讀出、直接驗證（FR-009／SC-005）；分數是複合公式的輸出，07-06/07-13 兩次驗證都證明「分數 log 缺席時無法還原真相」。
- 分數的結構性天花板（singleton ≈ 0.48 × quality ≤ ~0.22）正是本 feature 要繞過的東西，再拿它當觸發依據等於把問題搬回門口。
- 預設值依據：實測政策池流入 15 篇/4 週（~3–4 篇/週）→ 門檻 10 約每 2–3 週觸發，接近「政策月報」節奏。quality_floor 0.18 落在已知垃圾（「友善列印」0.165）與已驗證實文最低值（0.193）之間。
- 兩值均為 config 可調（D4），不需精確最優。

**Alternatives considered**:
- Σ(quality)：可行但不透明，且與既有 bucket 分數語意混淆。
- Σ(bucket score)：繼承天花板問題，否決。
- 篇數＋最低天數跨度：多一個維度換極小的防抖收益（消耗語意已防重複），YAGNI。

## D2 — digest 與 novelty gate 的隔離：空簽章

**Decision**: digest 報告的 `topic_token_signature` 存 **空 list `[]`**；digest 本身不經 novelty gate。

**Rationale**:
- digest 的跨期不重複由**消耗語意**保證（FR-005／SC-002），不需要 novelty gate。
- 風險在反方向：digest 若存池的代表詞簽章，會被 `_match_prior_basis`（同類別 + 簽章 Jaccard ≥ 0.3，`src/analyzer.py:999`）匹配為未來真正政策 cluster 的 prior basis，套 `novelty_growth_pct` 成長門檻——digest 的 `cumulative_score` 語意與 bucket 分數不同（D6），這種比較無意義且會誤壓。
- `compute_jaccard` 對空集合回 0.0（`src/filter.py:334-337`，已讀碼確認）→ 空簽章**永遠**匹配不上，隔離乾淨、零 schema 變更、零新欄位。

**Alternatives considered**:
- 保留簽章＋在 `_match_prior_basis` 加「排除 digest label」特判：多一處耦合（label 樣式滲入 gate 邏輯），否決。
- 新增 `report_type` 欄位區分：違反 spec 的零 schema 承諾，已在 spec 階段否決。

## D3 — 消耗的兩段實作與失敗語意

**Decision**: 消耗 = 既有路徑＋一個新 helper，順序固定：

1. `upsert_hot_topic_report(report)` —— 既有函式，upsert 成功後標記 `source_article_links`（選材）為 analyzed（`src/storage.py:450-465`）。
2. `mark_articles_analyzed(links)` —— **新增** storage helper，標記池內**其餘**文章（未入選材者，含低品質文）。

失敗語意：
- Gemini 分析失敗或回空 → 跳過該 digest，**兩段都不執行**，池不消耗，下週重試（US2 場景 2）。
- upsert 失敗（raise）→ 同上，不消耗。
- 步驟 2 失敗 → log **ERROR**（非既有標記路徑的 warning）。後果：殘餘文章下次觸發時重進池——但選材 links 已標掉，重疊僅限殘餘低分文，且同週重跑因 upsert 鍵冪等不產生重複報告。可接受的 fail-soft，與管線既有慣例一致。

**Rationale**: 選材標記已有現成路徑，只補殘餘；順序保證「報告已持久化才清池」。把殘餘標記失敗升級為 ERROR 是因為消耗是 digest 的核心語意（bucket 路徑的標記只是衛生），需要驗證時一眼看到。

**Alternatives considered**:
- 全池 links 塞進 `source_article_links` 一次標完：污染報告的對外來源清單（前端會渲染），否決。
- 先清池再 upsert：報告失敗時內容憑空消失，違反 FR-005，否決。
- 步驟 2 失敗改 raise 使整週跑 fail：懲罰過重（其他熱點已發布），否決。

## D4 — `category_digest` 設定形狀、載入與驗證

**Decision**: `PIPELINE_CONFIG_YML` 新增頂層鍵：

```yaml
category_digest:
  道安政策:
    trigger_count: 10      # 有效篇數觸發門檻（正整數）
    quality_floor: 0.18    # 有效文章品質下限（[0,1]）
    max_articles: 15       # 選材上限 K（正整數）
```

`pipeline_config._DEFAULTS` 加 `"category_digest": {}`（空 = feature off）；`_validate_pipeline_config` 加逐類別驗證（trigger_count/max_articles 為正整數、quality_floor ∈ [0,1]），錯誤即 raise（沿用既有 fail-fast 慣例）。每類別的三個子鍵皆可省略，省略時套用上述預設值。

**Rationale**: 與 `category_min_threshold` 同一份設定檔、同一種 per-category 形狀、同一個載入/驗證入口——維運心智模型不變（憲章 II）。頂層鍵（而非塞進 `topic_scoring`）是因為它控制的是一條平行路徑，不是 scoring 參數。

**Alternatives considered**:
- 放 `topic_scoring.category_digest`：語意錯位（不是 scoring），否決。
- 放 `CATEGORIES_TRAFFIC_YML`：那份檔管分類定義與路由，不管選取層行為，否決。

## D5 — 席次保留與同週同類 bucket 的文章排除

**Decision**: runner 串接順序（`scripts/traffic_weekly_analysis.py`）：

1. 照舊：cluster → score → `select_hot_topics_with_novelty`（一般 bucket 完整跑閘）。
2. digest 觸發統計（每個啟用類別；FR-009 log 無論觸發與否都記）。
3. 席次分配：`hot_topic_ids = 一般入選[:max_hot_topics - len(觸發的 digests)]`——digest 先佔格，一般 bucket 取剩餘。多 digest 同週觸發且超過上限：依有效篇數多者優先，其餘**不消耗**、留待下週（edge case 已列 spec）。
4. digest 池組成時排除「本週已入選一般 bucket」的同類文章（FR-006）：以步驟 3 定案的 `hot_topic_ids` 之 bucket 成員 link 集合作排除名單。
5. 發布迴圈照舊（digest 與一般熱點同迴圈，維持 2.5s delay）。

**Rationale**: 觸發統計放在一般選取**之後**才能拿到定案的排除名單；席次先扣 digest 是 spec FR-007 的直接要求（反餓死目的）。novelty gate 對一般 bucket 的行為完全不變——digest 只影響 cap 名額。

**Alternatives considered**:
- digest 在 cap 後競爭（比分數）：digest 無可比分數且必被高頻類別擠掉，違反 FR-007，否決。
- 擴格（max_hot_topics+1）：改變既有輸出量承諾與 Gemini 呼叫上限，否決。

## D6 — digest 選材、prompt 與報告欄位語意

**Decision**:
- 選材：池內（排除名單後）quality 由高至低取至多 `max_articles`（預設 15）篇。**不沿用** `analyze_hot_topic`（其 top-10 截取與單事件 prompt 皆不合用）；新增 `analyze_category_digest(pool_articles, topic_label, week_start_date, max_articles)`，沿用 `_call_gemini` 與相同回傳契約 `(report_text, ordered_links)`。
- Prompt：新模板 `DIGEST_PROMPT_TEMPLATE`——「一段期間的<類別>動態總覽」：逐事件短段（各事件互相獨立，不得硬湊因果）、期間跨度明示（文章日期範圍）、引用編號 `[n]` 對應 ordered_links（沿用既有渲染慣例）。
- 報告欄位（`hot_topic_reports` 列，零 schema 變更）：
  - `topic_label` = `"<類別> · 彙整"`（常數詞「彙整」；(week, label) 鍵保證每類每週至多一筆）。
  - `cumulative_score` = 選材文章 quality 總和（記錄用；因 D2 空簽章，永不參與 novelty 比較）。
  - `distinct_sources`／`distinct_days`／`latest_source_date`／`source_article_count` = 按選材計算，沿用既有欄位語意。
  - `topic_token_signature` = `[]`（D2）。

**Rationale**: 回傳契約與欄位語意對齊既有管線，publisher／前端零改動；prompt 分離是因為彙整與深挖的敘事結構不同（單事件 prompt 硬套多事件會產生虛構關聯）。

**Alternatives considered**:
- 參數化 `analyze_hot_topic`（加 mode flag）：兩種敘事的模板與截取邏輯差異大，flag 分支比兩個小函式難讀，否決（YAGNI 反向：這裡「兩個相似函式」比「一個雙模函式」簡單）。
- `cumulative_score` 存有效篇數：欄位型別是 float 且前端可能顯示為分數，語意錯位，否決。

## 風險與已接受的損耗（誠實記錄）

- **label 碰撞（理論）**：一般 bucket 的 `signature[0]` 恰為「彙整」時 label 與 digest 相同 → upsert 互蓋。機率趨近零（需同週同類且代表詞為「彙整」）；不加防護，出現時 log 可見。
- **殘餘標記失敗的重疊窗**（D3）：接受，ERROR 可見。
- **池不觸發則 8 週到期損耗**：spec 已列 Assumptions，v1 接受。
- **prod 部署依賴**：`PIPELINE_CONFIG_YML` env var 需在 merge 後手動補 `category_digest` 區塊（憲章 II 慣例，quickstart 列步驟）。
