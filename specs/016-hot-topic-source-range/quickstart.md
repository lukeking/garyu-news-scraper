# Quickstart: 驗證熱點報告的涵蓋區間與 ★

本機 `python` 不在 PATH，用 `.venv/bin/python`。

## 1. 測試

```bash
.venv/bin/python -m pytest tests/unit -q     # analyzer 的焦點事件帶 published、回填的純函式
npm test                                     # app.js：區間計算與格式、★ 對照（jsdom 跑真正出貨的 app.js）
```

## 2. 簽核用的畫面（實作前，FR-008／SC-004）

spike 不進 repo，放在 scratch：

1. 從 prod 公開 API 抓 `/api/hot-topics`、`/api/weeks/2026-W45?content_type=traffic`、`/api/weeks/2026-W44?content_type=traffic`，
   焦點事件補上 DB 唯讀查到的 `published`，存成 stub JSON。
2. 本機開一個靜態 server：`pages/traffic/index.html`（`__API_BASE__` 改指本機 stub）＋ spike 版 `app.js` ＋ `shared.css`。
3. 用 `~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome` headless 截圖：412 px 寬 × 亮、暗（`localStorage.theme`）
   各一張，W45 頁（報告卡片）與 W44 頁（★）都要；再加一張桌面寬度。
4. 截圖給 Luke；簽核的字樣、位置寫回 `contracts/hot-topic-card-ui.md`，再寫正式實作。

## 3. 回填既有報告（FR-005）

```bash
.venv/bin/python scripts/backfill_hot_topic_source_dates.py            # dry-run：每份要補幾項、找不到幾項、目標 host
.venv/bin/python scripts/backfill_hot_topic_source_dates.py --apply    # 寫入並逐份讀回，不一致 exit 非 0
```

回填前後各存一份 `(id, week_start_date, topic_label)`，兩份要逐列相同（SC-002 的資料面）。重跑 `--apply` 應該是 0 項要補（冪等）。

## 4. 上線與驗收

- merge 之後 `deploy-pages-traffic.yml` 會因 `pages/shared/**` 改動自動部署；Worker 不改、不部署。
- **SC-001**：所有有報告的週次頁面，卡片的區間與「焦點事件發布日期的最早／最晚」逐份比對，55 份真報告全對（另一份是 2025-W02 的測試殘留，沒有週次頁面顯示它）。
- **SC-002**：每份報告的分享連結 `?week=<ISO 週>#topic-<slug>` 打開後停在同一週、找得到同一張卡片。
- **SC-003**：上線後第一個週一的週報，新報告的每一項焦點事件都有 `published`，卡片顯示區間。
- **SC-005**：抽 W44、W45 兩頁，每個 ★ 都對得到一份報告的焦點事件，提示的週次正確；只被彙整消耗的文章沒有 ★。
