# Phase 0 Research: 交通頁可讀性重設計

無遺留 NEEDS CLARIFICATION（已於 spec 的 Clarifications／Session 2026-06-08 收斂）。以下記錄四項實作層級的設計決策。

## D1. 統一週導覽的「週鍵對齊」

**Decision**: 前端把每則熱點報告的 `week_start_date`（週一日期，如 `2026-06-01`）**換算成 ISO 週字串**（如 `2026-W23`），再與 `/api/weeks` 回傳的文章 `week_id` 比對；選定某 `week_id` 時，過濾出換算後相符的報告渲染。

**Rationale**:
- 兩套鍵是同一週的不同表示：`week_id` 來自 `dt.isocalendar()`（`src/publisher.py:32`）；`week_start_date` 來自該 ISO 週週一（`scripts/traffic_weekly_analysis.py:_week_start_date`）。
- `date → ISO 週` 在 JS 比 `ISO 週 → date` 好寫且不易出錯。
- `/api/hot-topics` 本就一次回全部報告，前端分組即可，**無需新增 API 查詢、零後端改動**，符合「API 改動最小化」與純前端取向。

**Alternatives considered**:
- 前端 `week_id → 週一日期` 後呼叫 `/api/hot-topics?week=`：需逐週 fetch、ISO 週解析較繁，且多打 API。
- 後端在 `hot_topic_reports` 增 `week_id` 欄或在 `/api/weeks` 併入 `week_start_date`：屬 schema/pipeline 改動，牴觸非目標與 Free Tier/Pipeline 原則，否決。

## D2. Deep-link 方案（深度分析分享定位）

**Decision**: 分享 URL = `<<origin+path>>?week=<week_id>#topic-<slug>`。
- `?week=<week_id>`：載入時讀取 → 選定該週（同時驅動兩區）。
- `#topic-<slug>`：`slug` 由 `topic_label` 正規化產生，對應熱點卡片的 `id`，載入後捲動定位。
- LINE 分享沿用既有機制（`social-plugins.line.me/lineit/share?url=`），只是 `url` 改為上述頁面 deep-link，而非單篇文章連結。

**Rationale**: `(week_start_date, topic_label)` 已是報告唯一鍵；用 `week` 做選週、`#topic` 做卡片定位，純前端可解析，無需後端。失效（週/主題不存在）時回退到最新一週（見 contract 的錯誤行為）。

**Alternatives considered**: 純 hash（`#week=...&topic=...`）亦可，但 `?week=` 與既有 `/api/hot-topics?week=` 語意一致、較直覺，採用 query+hash 混合。

## D3. traffic 渲染結構（共用 vs 拆分）

**Decision**: traffic-only 的渲染（熱點卡片、密集列、deep-link、分享）**維持在 `pages/shared/app.js` 內、以 `C.contentType === 'traffic'` 分流**，抽出具名函式（如 `renderHotTopics`、`renderTrafficList`）但不另立模組。

**Rationale**: 憲法原則 V（YAGNI、避免提早抽象）＋使用者已將「traffic/ffxiv 共用層整體重設計」框為 008 之後的獨立後續（見記憶 `project_traffic_ffxiv_shared_divergence`）。本次只做必要的具名拆函式，不做跨頁抽象重構。

**Alternatives considered**: 立即把 traffic 渲染拆成獨立檔/模組——屬提早的大重構，與延後決議衝突，否決。

## D4. 零後端／零 Gemini 改動的確認

**Decision**: 本功能不改 `workers/api`、不改 Supabase schema、不呼叫 Gemini。

**Rationale**: FR-014（純前端重排）、FR-015（既有欄位）、FR-016（歷史僅日後生效，不重生）共同保證無後端與無模型用量。`/api/hot-topics`、`/api/weeks`、`/api/weeks/{weekId}` 既有能力已足夠（D1）。若日後發現週鍵對齊在前端不可行，才回退到「Worker 端對齊」作為 fallback（目前不需要）。
