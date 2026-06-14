# Phase 0 Research: 節奏觸發式深度分析 + 深度來源分類補進

研究範圍以 spec 的 FR 與既有程式碼為界。每項：Decision / Rationale / Alternatives。

---

## D1 — novelty 比對語意（受 `hot_topic_analyzed` 影響）

**現況事實（已驗證）**：
- `upsert_hot_topic_report`（`storage.py:404-417`）在寫入報告後，把 `source_article_links` 對應文章標 `hot_topic_analyzed=TRUE`。
- `get_traffic_buffer`（`storage.py:316-342`）只回 `hot_topic_analyzed=FALSE` 且未過期的文章。
- 故**已被報告的文章離開 buffer**；下一週同話題的 bucket 只由「尚未分析」的新文章組成 → 上次與本次報告的來源文章集**互斥**。
- 真正的疲乏來源：高量常青類別（機車事故、行人事故）每週都有足量新鮮文章重新組 bucket、重新過門檻 → 每週重發近似報告。`hot_topic_analyzed` 防止「重用舊文章」，但防不了「靠穩定新鮮量重發」。

**Decision**：novelty 比對的語意定為「**本週新累積相對上次報告基準的突增 + 時間延伸**」，而非同一文章集成長。據此精確化 FR-007：
- (a) `current_bucket_score ≥ last_report.cumulative_score × (1 + p)` —— 本週新鮮量/品質須顯著超過上次報告當時的基準（突增）。
- (b) 本週 bucket 至少有 1 篇 `published` 嚴格晚於上次報告的 `latest_source_date` —— 確保話題在「上次看過之後」確有新事件延伸，而非僅是同期未入選的殘留文章。

**Rationale**：在互斥文章集下，單純「distinct_days 數量比大小」會因兩集不可比而失義；且「本週任一新文章」幾乎恆真（新文章本就都是新的），作為閘門過弱。以「上次報告基準分數的突增」+「時間軸延伸到上次報告之後」兩者並行，才真正攔住常青類別的同質重發，同時讓真有後續發展的話題通過。

**Alternatives considered**：
- 直接照字面 `current_distinct_days > last_reported_distinct_days`：互斥集下語意不清、過弱 → 改為「晚於 latest_source_date」的時間延伸判定（保留 spec「至少 1 個新 distinct day」的精神）。
- 取消 `hot_topic_analyzed` 標記、改真累積：改動大、衝擊既有 idempotency 與 buffer 過期邏輯，超出本 feature 範圍 → 否決。

> ⚠️ 此項對 FR-007(b) 的字面做了**語意精確化**（「新增 distinct day」→「published 晚於上次報告 latest_source_date」）。已於報告中向使用者標示，待確認。

---

## D2 — 跨週 topic 身分（hybrid，對應 Q1=C）

**現況事實**：`traffic_weekly_analysis.py:84` 取 `topic_label = bucket_articles[0].major_category`。`hot_topic_reports` 唯一鍵為 `(week_start_date, topic_label)`。故**topic_label 實際上等於 major_category**，且同類別在同週只能有一筆報告（兩個同類別 bucket 入選會 upsert 互蓋）。

**Decision**：
- 以 **hybrid 鍵**做跨週同話題判定：先比 `major_category`，再比本週 bucket 代表詞集合與候選 prior report 的 `topic_token_signature` 的 Jaccard 是否 ≥ `topic_identity.similarity_threshold`。
- bucket「代表詞集合」定義為：該 bucket 內各文章 `normalise_title` token 的聯集，取出現次數最高的前 K 個（K 預設 8）。沿用既有 `normalise_title` / `compute_jaccard`（`filter.py:304,331`），不引入新相似度法。
- 修正 topic_label 碰撞：報告的 `topic_label` 改為「`major_category` + 代表詞」可辨識字串（如 `機車事故 · 區間測速`），使同類別不同 bucket 不再互蓋；唯一鍵維持 `(week_start_date, topic_label)`。

**Rationale**：使用者選 hybrid（Q1=C）即要求比 major_category 更細、又比純詞集更穩。沿用既有 tokeniser 與 Jaccard 最省、與 cluster 階段一致。修 topic_label 碰撞是支援 hybrid 的前置必要條件。

**Alternatives considered**：
- 純 major_category（Q1=A）：使用者未選；且同類別多 bucket 無法區分。
- 純代表詞集合（Q1=B）：跨週漂移；使用者未選。
- embedding 相似度：已有 `003_embedding_dedup` 設施，但對標題短文 overkill 且增成本 → 否決，沿用 Jaccard。

---

## D3 — novelty delta 定值

**Decision**：
- 成長百分比門檻 `p` 置於 `pipeline_config.yml` → `topic_scoring.novelty_growth_pct`，**預設 0.5**（本週分數須 ≥ 上次 ×1.5）。
- 相似度門檻 `topic_identity.similarity_threshold`，**預設 0.3**。
- 結構條件固定：本週至少 1 篇 `published` 晚於上次報告 `latest_source_date`（不另設參數）。

**Rationale**：`p=0.5` 對常青類別足以擋掉「量持平」的重發，又不至於把真正升溫的話題擋掉；屬可調旋鈕，正式環境可依實跑微調。`0.3` Jaccard 與 cluster 階段 `cluster_lower=0.20`/`merge_threshold=0.45` 同量級、落在「同話題但非近重複」區間。

**Alternatives considered**：絕對分數差（量綱隨話題大小漂移，不公平）；純百分比無時間條件（互斥集下過鬆）。皆於 spec clarify 已排除或本研究補強。

---

## D4 — source-default map 設定位置與載入

**Decision**：
- map 置於 `categories_traffic.yml`（即 GitHub Variable `CATEGORIES_TRAFFIC_YML`）新增頂層鍵 `source_defaults:`，形如 `{ 來源名子字串: major_category }`。
- 在 `pipeline_config.py` 新增 `load_source_default_categories()`（與 `load_category_taxonomy` 同檔、同快取風格）讀取該鍵；缺鍵回 `{}`（功能優雅關閉）。
- 比對方式：以 article `source` 對 map 鍵做**子字串**比對（來源實際名為「Google News 報導者交通」等，map 鍵用「報導者」即可命中），第一個命中者勝。

**Rationale**：分類相關設定與既有 taxonomy 同住一個 GitHub Variable，維運一致（憲章 II，新增來源免改碼）。子字串比對對應實際 Google News 來源命名。

**Alternatives considered**：放 `pipeline_config.yml`（與 taxonomy 分家、較不內聚）；放 `sources_traffic.yml` 每來源加 `default_category` 欄（需 collector 透傳欄位到 article dict，改動面更大）→ 皆否決。

**初始 map（spec FR-013 已確認）**：
```yaml
source_defaults:
  報導者: 道安政策
  天下: 道安政策
  道安統計: 道安政策
  行人地獄: 行人事故
  區間測速: 科技執法
```

---

## D5 — idempotency / 重跑 與 fail-open

**Decision**：
- **基準讀取**：`get_recent_hot_topic_reports` 取最近 N 週（預設 = `buffer.max_age_weeks`=8）報告，**排除當週 `week_start_date`**，避免同週重跑時拿自己當基準而誤判抑制（憲章 III idempotency）。
- **Fail-open（對應 clarify Q3=A）**：基準讀取失敗時 → 視所有候選為 novel、照常分析（仍受 `max_hot_topics` 上限保護），記 `warning`。
- **Selection order（clarify Q1）**：gate-then-cap —— 對所有 `score ≥ min_threshold` 的 bucket 先套 novelty gate，存活者再依分數取 top `max_hot_topics`。
- **Observability（spec 延後項）**：每個候選 bucket 記一行 INFO：category、score、matched prior（有/無）、growth 比、是否有晚於基準的新日、pass/suppress，供調 `p`。

**Rationale**：排除當週自身是 idempotency 的必要條件；fail-open 因有 ≤3 上限故成本有界、且不讓頁面變空；gate-then-cap 把預算花在有新進展者；決策日誌是調參前提。

**Alternatives considered**：fail-closed（可能整週空頁）；cap-then-gate（常青高分擠掉低分但新鮮的話題）→ 均於 clarify 已排除。

---

## 既有資產沿用清單（避免重造）

| 既有 | 位置 | 本 feature 用途 |
|---|---|---|
| `normalise_title` / `compute_jaccard` | `filter.py:304,331` | 代表詞簽章與 hybrid 相似度 |
| `assign_category` | `filter.py:340` | source-default 為其呼叫端 fallback，函式本身不改 |
| `score_topic_buckets` | `analyzer.py:922` | 分數來源，不改公式 |
| `select_hot_topics` | `analyzer.py:952` | 與 novelty gate 整合為 gate-then-cap |
| `upsert_hot_topic_report` | `storage.py:373` | 增寫 token_signature / latest_source_date |
| `load_*` + `_deep_merge` 快取 | `pipeline_config.py` | 新增 source-default / novelty 參數讀取 |
