# Quickstart: Buffer List 雜訊分流呈現層

**Feature**: 011-buffer-noise-triage | **Date**: 2026-07-21

三段流程：量測 → 設定 → 驗證。

## 1. 跑量測，產生設定值

```bash
python scripts/measure_source_uptake.py            # 表格輸出，人工檢視
python scripts/measure_source_uptake.py --json     # 直接產出設定用的 JSON
```

腳本自行以 `python-dotenv` 讀取專案根目錄的 `.env`（**注意**：`load_dotenv()` 不帶參數時從呼叫端檔案位置往上找；腳本置於 `scripts/` 之下時須給絕對路徑或明確的專案根路徑）。

**腳本必須自動界定窗口，不得寫死週次清單**（FR-005c）。排除規則：

- **排除已遭清除的舊週**——`expire_buffer_articles()` 只刪「已過期且未分析」的列，已分析者永久保留，導致舊週採用率趨近 100%。判定法：該週未分析數為 0 即視為已清除。
- **排除週報尚未執行的當週**——該週採用率結構性為 0，意義是「還沒輪到」而非「雜訊」。

**不可使用 `get_traffic_buffer()`**——它內建 `hot_topic_analyzed=False` 過濾，只會回傳沒進報告的那半邊，分子恆為 0。請直接查 `articles` 表並分頁（單次回應上限 1000 列）。

## 2. 套用設定

把 `--json` 的輸出設為 GitHub production environment variable `SOURCE_UPTAKE_JSON`：

```bash
# 此指令由使用者本人執行——助理端跑 gh variable set 會被權限擋
gh variable set SOURCE_UPTAKE_JSON --env production --body "$(python scripts/measure_source_uptake.py --json)"
```

注意既有的 CRLF 與尾端空行陷阱（同 `PIPELINE_CONFIG_YML` 的既有處理方式）。

設定完成後，`deploy-worker.yml` 的 `vars:` 與 `env:` 區塊需各加一行 `SOURCE_UPTAKE_JSON`，然後重跑 Deploy Cloudflare Worker API workflow。**改評級或門檻都需要重跑此部署**，這是採用 Worker 變數方案的已知代價。

讀回確認（唯讀，助理可執行）：

```bash
gh api repos/lukeking/garyu-news-scraper/environments/production/variables/SOURCE_UPTAKE_JSON --jq '.value'
```

## 3. 驗證

### API 契約（4 項，見 contracts/week-detail-api.md）

```bash
# 近期週：應同時出現 true 與 false
curl -s "$API/api/weeks/2026-W30" | jq '[.articles[].noise_downgrade] | group_by(.) | map({v:.[0], n:length})'

# 最早週（遠早於量測窗口）：欄位仍須存在
curl -s "$API/api/weeks/2026-W20" | jq '.articles[0] | {source, noise_downgrade, source_multiple}'

# FFXIV 路徑：應全為 false
curl -s "$API/api/weeks/2026-W30?content_type=ffxiv" | jq '[.articles[].noise_downgrade] | unique'
```

設定損毀的退化行為需手動測一次：把變數暫設為無效字串、部署、確認端點仍回 200 且全部 `false`，再改回來。

### 前端驗收（SC-005 要求雙週次）

**兩個週次都要跑一遍**，其中一個 MUST 為圖片覆蓋率 0% 的舊週：

| 檢查 | 對應 |
|---|---|
| 降級列預設收合為單一提示行，標示篇數 | FR-008 |
| 點擊提示行就地展開為淡化樣式，可再收合 | FR-008a |
| 切換週次再切回，降級列回到收合狀態 | FR-008b |
| 展開後標題／摘要／原文連結／分享皆正常 | FR-009 |
| 分組標頭同時顯示總篇數與降級篇數 | FR-011 |
| 分組收合時降級提示行一併隱藏 | FR-011a |
| 單一動作收起整個收集來源，且不隨篇數增加 | FR-012 / SC-004 |
| 重新載入後收起狀態保留，可還原 | FR-013 |
| 全部收起時顯示空狀態與一鍵還原 | FR-014 |
| 與既有「標記過時」並存不互相覆寫 | FR-015 |
| 已進熱點報告者帶可辨識標記 | FR-016 |
| **零圖片舊週版面不破損** | FR-017 |

### 成效階數

SC-003（掃描成本）與 SC-004（操作成本）可即時量測。

**SC-001／SC-002 在人工標註基準集產出前一律記為「未量測」**——不得以主觀印象填寫，也不得改用 `initial_quality_score` 近似（該分數已實測無鑑別力，FR-003 明文禁用）。基準集不阻擋交付（FR-018a）。

## 需要人工決定的一筆

`火花羅` 量測倍率 0.31 落在雜訊側，但它是手動挑選的 YouTube 頻道而非自動搜尋查詢，低採用率可能反映影片不易聚成熱點群集而非價值低落。量僅 17 篇。**建議初版把它排除在設定之外**（走預設非雜訊），待基準集產出後再依真值決定。

## 撤除方式

移除 Worker 變數並重新部署，即回到現況行為——無資料需要清理、無遷移需要回滾。這是「推導而非儲存」設計的直接好處。
