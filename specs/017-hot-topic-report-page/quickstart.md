# Quickstart: 驗證熱點報告與新文章拆成兩條流

本機 `python` 不在 PATH，用 `.venv/bin/python`。

## 1. 測試

```bash
npm test                                   # app.js：landingStream、新內容計數、批次、分享連結、焦點事件展開、文章列沒有 ★（jsdom 跑出貨的 app.js）
.venv/bin/python -m pytest tests/unit -q   # 不動 Python，跑一次確認沒被波及
```

## 2. 簽核畫面（實作前，FR-014／SC-005）

spike 不進 repo，放在 scratch（做法同 016 的 T001）：

1. 從 prod 公開 API 抓 `/api/hot-topics`、`/api/weeks`、`/api/tags`、`/api/weeks/2026-W45` 與 `2026-W44`（`content_type=traffic`），存成 stub JSON。
2. 本機開靜態 server：新結構的 `pages/traffic/index.html`（`__API_BASE__` 指 stub）＋ spike 版 `app.js` ＋ `shared.css`。
3. 用 `~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome` headless 截圖，主題用 `localStorage.theme`，badge 用預先寫好的
   `traffic_seen_*`（例：熱點 11-01、新文章 3 天前）：
   - 412 px 亮、暗：熱點在前（文章鈕上有 badge）、文章在前、齒輪面板展開、焦點事件展開。
   - 桌機 1024、1280、1440 px：看並排在哪個寬度成立，定 FR-002 的斷點。
4. 截圖給 Luke；簽核的字樣、位置與斷點寫回 `contracts/traffic-streams-ui.md` 與 spec FR-002，再寫正式實作。

## 3. 刪除測試殘留的報告（FR-009，要 Luke 同意才跑）

1. 唯讀：印出 `hot_topic_reports` 裡 `topic_label` 是 `酒駕-integration-test` 的列（id、`week_start_date`、`created_at`、來源數），
   以及目標 host（URL 不是憑證）。
2. Luke 同意後刪除那一列，讀回同條件 0 列、總數少 1。

## 4. 上線與驗收

- merge 之後 `deploy-pages-traffic.yml` 因 `pages/traffic/**`、`pages/shared/**` 改動自動部署；Worker 不改、不部署。
- **SC-001**：412 px 與桌機各打開一次 prod 交通頁，新文章那一條抽 W44、W45，熱點 0、★ 0；熱點那一條切到更早的批次；切一條的導覽另一條不動。
- **SC-002**：在瀏覽器的開發者工具把 `traffic_seen_articles` 改成 3 天前、`traffic_seen_reports` 改成上一個週一之前、清掉已收起的來源，重新整理；
  badge 的篇數、份數與**資料庫唯讀查詢**（scratch 腳本在執行時載入本機設定，數 `articles`／`hot_topic_reports` 裡 `created_at` 晚於基準的列）一致——
  不拿 Worker API 比，因為那是實作自己走的路徑；切走之後清掉。
- **SC-003**：清掉站上資料 → 熱點；切到文章、重開 → 文章；齒輪設成熱點／文章 → 一律那一條；打開一個舊格式連結 → 照規則、不報錯。
  另外，55 份報告各自的新分享連結都定位到同一份（merge 前用本分支的 `app.js` 對 prod 公開 API 逐份跑）。
- **SC-004**：熱點那一條能瀏覽到的報告數＝55，沒有 `酒駕-integration-test`。
- **SC-005**：上線後用簽核時的寬度與主題截 prod 頁面，與簽核截圖並排比對。
- **SC-006**：在熱點那一條讀一份報告、展開兩個焦點事件，全程沒有切到新文章那一條。
