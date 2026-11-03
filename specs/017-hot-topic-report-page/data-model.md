# Data Model: 熱點報告與新文章拆成兩條流

資料庫結構、Worker 的回應形狀都不改。下面是前端讀到的欄位，以及前端自己推導、自己存的東西。

## 讀進來的（不改）

### 熱點報告（`/api/hot-topics` 的 `reports[]`）

| 欄位 | 本 spec 怎麼用 |
|---|---|
| `week_start_date` | 分批的鍵（那次週報的週一，`YYYY-MM-DD`；手動 dispatch 也是那週的週一）；卡片上的所屬週報；新分享連結的 `batch` |
| `topic_label` | 卡片標題；`slugify()` 之後是卡片錨點與新分享連結的 slug |
| `created_at` | 「有新報告」的判斷 |
| `source_article_links[]` | 焦點事件；項目是 `{link, title, summary}`，舊格式是只有連結的字串 |
| `report_text`、`source_article_count`、`distinct_sources` | 照現在顯示 |

### 文章（`/api/weeks/<週>` 的 `articles[]`）

| 欄位 | 本 spec 怎麼用 |
|---|---|
| `created_at` | 「新文章」的判斷（第一次收進來的時間，見 research R4） |
| `week_id` | 新文章那一條的週次（照舊） |
| `hot_topic_analyzed` | 不再使用（拿掉 ★） |

## 前端推導的

### 報告批次

- 由報告依 `week_start_date` 分組而來，新的在前；一批 1～3 份（2026-11-03：25 批）。
- 測試殘留從 prod 刪除之後，所有批次都是真報告；前端不過濾。

### 新分享連結

- 形狀：`<頁面網址>?batch=<week_start_date>#report-<slug>`。
- 解析成 `{ batch, slug }`；兩者都要對到一份報告才算有效（同名報告每週都有，只看 slug 會混淆）。

## 前端存的（讀者這台裝置的 `localStorage`）

鍵與值見 `contracts/local-state.md`。四項：齒輪設定、上次離開時在哪一條、熱點上次看過的時間、新文章上次看過的時間。

### 狀態轉換

```text
第一次打開（兩條都沒有「上次看過」）
  → 兩條的「上次看過」寫成現在；不顯示 badge；落在熱點

之後每次打開
  → 讀兩條的「上次看過」當這次的基準
  → 依 landingStream 落地；窄螢幕時把落地的那一條寫進「上次離開時在哪一條」
  → 被顯示的那一條（寬螢幕是兩條）：「上次看過」寫成這次打開的時間
  → badge：基準之後的報告份數／文章篇數

窄螢幕切換
  → 新的那一條被顯示：「上次看過」寫成這次打開的時間；「上次離開時在哪一條」改成它
  → 切走的那一條：這次造訪裡的 badge 清掉
```
