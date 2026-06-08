# Contracts: UI / API / URL — 交通頁可讀性重設計

本功能不新增/變更後端 API（唯讀消費既有端點）。以下記錄依賴的 API 契約、URL/deep-link 契約、以及各 UI 區塊的行為契約。

## A. 依賴的既有 API（唯讀，不變更）

| 端點 | 用途 | 關鍵欄位 |
|------|------|----------|
| `GET /api/weeks?content_type=traffic` | 週導覽清單（主軸） | `week_id`（`week_id.desc`） |
| `GET /api/weeks/{weekId}?content_type=traffic[&q=]` | 某週新聞列表 | `title,link,source,published,summary,created_at` |
| `GET /api/hot-topics` | 全部週的深度分析報告 | `week_start_date,topic_label,report_text,source_article_links,...` |

備註：`/api/hot-topics` 雖支援 `?week=`，但本功能採前端對齊（research D1），不使用該參數；保留為 fallback。

## B. URL / Deep-link 契約

- 規格：`<origin+path>?week=<week_id>#topic-<slug>`
  - `week=<week_id>`：ISO 週字串（如 `2026-W23`）。載入時若存在 → 選定該週（驅動兩區）。
  - `#topic-<slug>`：`slug = slugify(topic_label)`，對應熱點卡片 `id="topic-<slug>"`，載入後捲動定位。
- 產生：熱點卡片「分享」動作建構此 URL，交給 `https://social-plugins.line.me/lineit/share?url=<encoded>`。
- 解析（載入時）：
  - 有 `?week=` 且該週存在 → 選該週；否則 → 最新一週。
  - 有 `#topic-<slug>` 且該卡片存在 → 捲動定位；否則 → 不定位、不報錯。

## C. UI 行為契約

### C1. 週導覽（統一、上移）— FR-001/002/003/004
- 位置：DOM 上位於深度分析區之上。
- 行為：點某週 → 同時更新深度分析區與新聞列表區為該週。
- 預設：首次載入選最新一週（`/api/weeks` 第一筆）。
- 標示：頁面明確顯示目前檢視的週。

### C2. 深度分析卡片（純前端結構化）— FR-006/007/008/014
- 解析 `report_text` 的 `### 一/二/三` 三軸 → 視覺分區卡片。
- 凸顯關鍵指標（交織度分布、代表個案），與次要 `欄位：值` 細節分權重。
- 焦點事件 `source_article_links` 維持可點擊；報告內 `[1][2]` 引用維持對應。
- 穩健降級：`report_text` 出現非預期格式時，不破版（fallback 為純文字段落）。

### C3. 新聞密集列（時間序＋來源色標）— FR-009/015
- 一行一則：來源色標（`C.srcColor`）＋ 標題（連原文）＋ 相對時間。
- 來源層級 `summary` 收於展開（點標題或展開鈕）。
- 僅用既有可用欄位，不顯示/不依賴 importance/tags。

### C4. 空狀態 / 跨區不一致 — FR-005
- 某週只有兩區之一有資料 → 有資料區正常顯示，另一區顯示明確空狀態，不報錯。

### C5. 深度分析分享 — FR-011/012/013
- 每則深度分析提供分享動作 → 產生 B 的 deep-link → LINE 分享。
- 沿用 `C.shareToLine` 開關；ffxiv（`shareToLine:false`）不顯示、不受影響。

### C6. 既有功能維持 — FR-010/SC-006
- traffic 實際可用者：關鍵字搜尋、標記過時（dismiss）、焦點事件連結、LINE 分享 → 改版後維持可用。
- 不得假設 traffic 有重要度/標籤篩選（本就無）。

## D. 不回歸契約（ffxiv）
- 所有 traffic-only 行為以 `C.contentType === 'traffic'` 分流；ffxiv 頁渲染、分享、篩選行為不得改變。
