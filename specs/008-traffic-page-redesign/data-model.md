# Phase 1 Data Model: 交通頁可讀性重設計

本功能為前端重設計，無 DB schema 變更。以下是前端消費的資料形狀與實體關係（欄位以既有 API 回傳為準）。

## Week（週）

統一週導覽的選擇單位，串連同一週的深度分析與新聞列表。

| 表示 | 來源 | 格式 | 範例 |
|------|------|------|------|
| `week_id` | `/api/weeks`、`/api/weeks/{weekId}` | ISO 週字串 | `2026-W23` |
| `week_start_date` | `/api/hot-topics` | 該 ISO 週週一日期 | `2026-06-01` |

- 兩者為同一週的不同表示，前端以 `week_start_date → ISO 週字串` 換算後對齊 `week_id`（research D1）。
- 導覽主軸 = `/api/weeks` 的 `week_id` 清單（已 `week_id.desc` 排序）；預設選第一個（最新）。

## Deep-Analysis Report（深度分析報告）

一週一主題的聚合分析，由 `/api/hot-topics` 提供（一次回全部週）。

| 欄位 | 用途 |
|------|------|
| `week_start_date` | 對齊週（換算成 `week_id`） |
| `topic_label` | 主題名稱；deep-link `#topic-<slug>` 的來源；卡片標頭 |
| `report_text` | 三軸分析全文（固定逐行格式，前端解析重組為卡片） |
| `source_article_links` | 焦點事件（物件含 `link`/`title`/`summary`，或純字串） |
| `source_article_count` / `distinct_sources` | 卡片 meta |
| `cumulative_score` / `distinct_days` | 既有排序/統計 |

- `report_text` 結構：`### 一/二/三` 三軸標頭；軸內為 `欄位：值` 行與 `□ ...` 勾選行。前端解析此結構 → 分區卡片、凸顯關鍵指標（如「交織度分布」）。
- 唯一性：`(week_start_date, topic_label)`。

## News Item（新聞項目）

交通新聞列表的單則，由 `/api/weeks/{weekId}` 提供。

| 欄位 | traffic 是否可用 |
|------|------------------|
| `title`、`link`、`source`、`published`、`created_at` | ✅ |
| `summary`（來源層級摘要） | ✅（展開時顯示） |
| `analysis.*`（importance / tags / summary / analysis / location） | ❌ 空（traffic buffer 未經 LLM 個別分析） |

- 密集列掃讀訊號：`source`（色標）＋`title`＋相對時間（`published`/`created_at`）。
- **不得**依賴 importance/tags/LLM summary（交通頁無此資料、無重要度篩選器）。
- 排序：時間序（最新在上）。

## Shareable Deep-Link（深度分析分享連結）

| 組成 | 值 |
|------|-----|
| base | 交通頁 origin + path |
| query | `?week=<week_id>` → 選定週 |
| hash | `#topic-<slug>`（`slug` 由 `topic_label` 正規化） → 卡片定位 |

- 由熱點卡片的分享動作即時建構；交給既有 LINE 分享端點。
- 解析：載入時讀 `?week=` 選週、`#topic-` 捲動定位；任一不存在則回退最新一週（見 contract）。

## 關係圖

```
Week (week_id) ─┬─ 1:N → News Item        （/api/weeks/{weekId}）
                └─ 1:N → Deep-Analysis Report（/api/hot-topics，經 week_start_date 換算對齊）
Deep-Analysis Report ─ 1:1 → Shareable Deep-Link（?week + #topic-slug）
```
