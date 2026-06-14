# Quickstart: 驗證 009 Novelty gate + Source-default 分類

目標：在本機驗證兩條行為與不回歸，無需打到 Gemini／正式 Supabase。以 pytest 為主、必要時用受控 fixtures。

## 前置

- Python 3.11、`pip install -r requirements.txt`。
- 本機 `.env`（含 `SUPABASE_*`，僅整合測試需要；單元測試不需）。
- 本機 `config/categories_traffic.yml`、`config/pipeline_config.yml`（由 `.example` 複製）。
- ⚠️ 已知環境阻礙：`.venv` 的 `charset_normalizer` C-ext segfault（exit 139）會使 `requests`/`bs4` 無法 import。若遇到，重建 venv 後再跑 collector 相關整合測試（純函式單元測試不受影響）。

## A. Source-default 分類（US2 / FR-009~014）

單元層（不需 DB）：
1. 設定 `categories_traffic.yml` 含 `source_defaults: { 報導者: 道安政策, 區間測速: 科技執法, ... }`。
2. 餵一篇 `source="Google News 報導者交通"`、標題不含任何分類 token 的文章 → 斷言 `major_category == "道安政策"`。
3. 餵一篇標題含「測速」（命中科技執法）但 `source="Google News 報導者交通"` → 斷言分類為 `科技執法`（**fallback 不覆蓋命中**，FR-010 / SC-005）。
4. 餵一篇 `source="Google News 機車事故"`（不在 map）、標題未命中 → 斷言維持 `uncategorised`（FR-012）。

對應 spec：US2 Acceptance 1–3。

## B. Novelty gate（US1 / FR-001~008）

單元層（以記憶體 buckets + 假 prior_reports）：
1. **首次觸發（FR-003）**：bucket 達 `min_threshold`、`prior_reports=[]` → `passes_novelty=True`、入選。
2. **抑制（SC-001）**：給一筆 prior basis（同 category、簽章相似度 ≥ 門檻、`cumulative_score=S`、`latest_source_date=D`）；本週同話題 bucket `score ≈ S`（< S×1.5）且最新日 ≤ D → 斷言被抑制、不入選。
3. **再觸發**：本週 bucket `score ≥ S×1.5` 且含一篇 `published > D` → 斷言入選（FR-008 re-surface）。
4. **gate-then-cap（clarify Q1）**：5 個過門檻 bucket，分數最高 3 個皆 stale、第 4/5 為 novel → 斷言入選的是第 4/5（而非空集）。
5. **fail-open（clarify Q3）**：模擬 `get_recent_hot_topic_reports` 拋例外 → 週分析串接處退化為「全部視為新」、仍受 `max_hot_topics` 上限（≤3）。

對應 spec：US1 Acceptance 1–4、Edge Cases。

## C. 端到端兩週序列（整合，需測試用 Supabase 或 mock）

1. 第 1 週：seed buffer（某高量類別 N 篇）→ 跑 `traffic_weekly_analysis`（Gemini 以 stub/mock）→ 產生報告、source 文章標 `hot_topic_analyzed=TRUE`、寫入 `topic_token_signature`/`latest_source_date`。
2. 第 2 週：seed 同類別少量新文章（量持平、無晚於上次的新日）→ 跑分析 → 斷言**該話題無新報告**（被 gate 抑制）。
3. 第 2 週變體：seed 同類別大量且含更晚日期新文章 → 斷言**再次產生報告**。

## D. 不回歸

1. `pytest`（`tests/unit` + `tests/integration`）全綠。
2. 既有 `tests/unit/test_category_assign.py`：標題命中案例分類不變（SC-005）。
3. daily buffer（`traffic_buffer.py`）路徑維持零 AI（不因本 feature 新增 Gemini 呼叫）。
4. Gemini 呼叫次數 ≤ `max_hot_topics`、保留 2.5s delay（憲章 IV）。

## 對照 Success Criteria

| SC | 由哪步驗證 |
|---|---|
| SC-001 抑制重複 | B2、C2 |
| SC-002 ≤ 上限且皆有新進展 | B4、C |
| SC-003 深度來源進政策 bucket | A2 |
| SC-004 零-AI buffer / ≤ 上限 | D3、D4 |
| SC-005 命中分類無回歸 | A3、D2 |
