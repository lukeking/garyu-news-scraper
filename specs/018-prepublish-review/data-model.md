# Data Model: 018 週報發布前審核

## 新表 `hot_topic_report_reviews`（`supabase_migrations/006_report_reviews.sql`）

一份報告一列，跟 `hot_topic_reports` 用同一把鍵。同一週重跑時 upsert 覆寫（憲章 III）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | UUID PK | `gen_random_uuid()` |
| `week_start_date` | DATE NOT NULL | 同 `hot_topic_reports` |
| `topic_label` | TEXT NOT NULL | 同 `hot_topic_reports` |
| `template` | TEXT NOT NULL | `digest`／`hot_topic` |
| `generation_model` | TEXT NOT NULL | 生成用的模型（`GEMINI_MODEL_NAME`） |
| `review_model` | TEXT | 審稿模型；沒跑審稿時為 NULL |
| `input_snapshot` | TEXT NOT NULL | 送給生成模型的報導清單全文（編號、報導日、標題、截斷後的摘要），重播時原樣使用 |
| `input_counts` | JSONB NOT NULL | `{"articles": N, "title_only": M}` |
| `original_text` | TEXT NOT NULL | 生成的原稿 |
| `findings` | JSONB NOT NULL DEFAULT `[]` | 審稿發現陣列，形狀見 `contracts/review-output.md`，每條另加 `applied`（bool）與 `apply_note`（沒套用的原因） |
| `checks` | JSONB NOT NULL DEFAULT `{}` | 機械檢查結果：`{"original": {...}, "published": {...}}`，每項的命中數與命中句（research R5；FR-003 的三類加總驗算在這裡） |
| `status` | TEXT NOT NULL | 見下方狀態 |
| `status_reason` | TEXT | `not_reviewed`、`revision_rejected`、`partially_applied` 時必填 |
| `published_text` | TEXT NOT NULL | 實際發布的版本（等於 `hot_topic_reports.report_text`） |
| `usage` | JSONB | 審稿呼叫的 token 數與秒數 |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

- `UNIQUE (week_start_date, topic_label)`；`GRANT … TO service_role`；開 RLS、不建 anon policy（不經 Worker API 公開）。
- 寫入：`src/storage.py` 的 `upsert_report_review(record)`，在 `upsert_hot_topic_report` 之後呼叫。寫入失敗時 log error、不擋發布，
  而且週報 log 的 `[審稿]` 摘要照印（FR-014a 的訊號不依賴這張表）。

## 狀態

一份報告結束時只會是其中一種：

| `status` | 意思 | `published_text` |
|---|---|---|
| `no_findings` | 審了，沒有發現 | 原稿 |
| `low_only` | 審了，只有低嚴重度，照規則不修 | 原稿 |
| `revised` | 中、高的發現全部套用，整份檢查通過 | 修稿 |
| `partially_applied` | 中、高的發現有些沒套（原句不唯一、沒給替換、單條檢查沒過），其餘套用、整份通過 | 修稿 |
| `revision_rejected` | 套完之後整份檢查沒過 | 原稿 |
| `not_reviewed` | 沒有審：沒設審稿模型、審稿模型等於生成模型、呼叫失敗、回應不是合法 JSON | 原稿 |

`not_reviewed` 與 `revision_rejected` 的 `status_reason` 用固定代碼開頭，後面接細節：
`model_unset`、`model_same_as_generator`、`call_failed`、`invalid_response`、`whole_report_check_failed:<哪一項>`。

## 錨點（`src/report_review.py` 內的資料，不進資料庫）

| 欄位 | 說明 |
|---|---|
| `id` | 短名，例 `drug-driving-7-deaths`（留一測試用它排除） |
| `category` | `wrong`（寫錯）／`bias`（觀點偏頗） |
| `severity` | `high`／`medium`／`low` |
| `templates` | 適用的模板：`digest`、`hot_topic` |
| `report` | 出處（週次與主題） |
| `quote` | 原句 |
| `problem` | 錯在哪、讀者會怎麼誤讀 |

## 生成輸入（程式組裝，不是新的資料表）

- 彙整：有摘要的報導編號 `[1]..[K]`，每篇 `報導日／標題／摘要（前 400 字）`；只有標題的報導編號接在 `[K+1]..[N]`，
  不進給模型的清單，由程式在報告最後加 `### 僅標題`。`ordered_links` 仍是 `[1]..[N]` 依序，`[i]` 對到第 i 篇。
- 三軸：清單照舊（最多 10 篇、摘要前 600 字），只有標題的那幾篇摘要欄寫「（僅標題）」。
- 這份清單全文就是 `input_snapshot`，審稿呼叫拿到的是同一份字串（FR-008）。
