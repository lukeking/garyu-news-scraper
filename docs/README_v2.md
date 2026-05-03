# Garyu News Scraper (v2.0) - 整合修正版

## 1. 專案願景 (Project Vision)
本專案為 **《零號協議 (Protocol Zero)》** 的外部資訊感知層。透過自動化爬蟲與 AI 摘要，過濾「台灣交通路權」與「FFXIV 8.0 戰鬥情報」等資訊流。

## 2. 既有生產環境 (As-Is Assets)
本專案基於原本的 `traffic-issue-scraper` 進行擴展，應確保以下既有功能不被破壞：
- **數據來源 (Traffic)**: 透過 Google News RSS 抓取關鍵字新聞。
- **基礎設施**:
    - **Cloudflare Workers**: 處理抓取邏輯。
    - **Supabase (PostgreSQL)**: 存儲新聞數據（標題、連結、摘要、情緒分析）。
    - **GitHub Actions**: 每週自動執行 (請 Agent 檢查正確檔名並修復排程)。
    - **部署**: Cloudflare Pages 自動化前端部署。

## 3. Agent 知識擴展協定 (Knowledge Expansion Protocol)
Agent 在處理 FFXIV (Reddit/JP Forum) 資訊時，必須遵循以下邏輯：

### A. 外部知識參考 (Knowledge Base)
- 所有 FFXIV 專有名詞（職業、技能、系統名稱）請對照 `knowledge-base.md`。
- **禁止通靈**：若術語不存在於模板中，嚴禁自行翻譯。

### B. 主動擴展規則
當 Agent 發現新名詞或對照缺漏時：
1. **多向檢索**: 同時檢索該名詞的英/日文原文與官方 Wiki 定義。
2. **更新 Knowledge Base**: 優先將檢索結果按照 **`knowledge-base-template.md`** 的格式更新至 `knowledge-base.md`，並在 PR 中註明。
3. **數據定錨**: 確保「Bard -> 吟遊詩人 (BRD)」與「Potency -> 威力」等數值嚴禁隨意詮釋。

## 4. 數據處理原則
- **交通議題**: 持續監控路權政策，濾除口水，保留系統失靈的工程記錄。
- **FFXIV 8.0**: 優先追蹤職業改動，剔除日文論壇客套話。

## 5. 開發任務清單
- [ ] **Workflow Repair**: 修復現有 GitHub Actions 的報錯紀錄。
- [ ] **Structure Refactor**: 在 `src/scrapers/` 下建立 `traffic/` 與 `ffxiv/` 路徑。
- [ ] **KB Initialization**: 根據模板產出初始知識庫並實作主動檢索邏輯。
