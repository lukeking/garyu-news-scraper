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

## 本地預覽（T002）

部署會把三處檔案攤平成一個目錄（見 `deploy-pages-traffic.yml`）。本地必須複製同樣的佈局，
否則 `index.html` 的 `src="app.js"` 找不到檔案。用 **symlink** 而非 `cp`，改動才會即時反映，
不會測到過期副本：

```bash
P=/tmp/preview-traffic
rm -rf "$P" && mkdir -p "$P" && cp -r pages/traffic/. "$P"/
ln -sf "$PWD/pages/shared/app.js"     "$P/app.js"
ln -sf "$PWD/pages/shared/shared.css" "$P/shared.css"
python -m http.server -d "$P" 8788   # → http://localhost:8788/
```

`index.html` 內建 `window.__API_BASE__` 指向正式 Worker，因此預覽讀的是**線上資料**——
前端改動可即時驗證，無須本地後端。

## 基線（T001）

驗收週次固定為以下兩週，涵蓋 SC-005 要求的兩種極端：

| 週次 | 篇數 | 圖片覆蓋率 | 分組數 | 角色 |
|---|---|---|---|---|
| **2026-W28** | 119 | **0%** | 10 | 零圖片舊週；篇數最多，版面壓力最大 |
| **2026-W29** | 87 | **33%** | 9 | 圖片覆蓋率最高的一週 |

**注意**：STATE.md 舊記「圖覆蓋率逐週 0%→74%」與實測不符。2026-07-21 全表實測結果為
W20–W28 皆 0%、W29 = 33%、W30 = 23%，**最高值是 33% 而非 74%**。以此處實測為準。

分組篇數基線（T004 改寫渲染分派後必須完全一致）：

```
W28 (n=119): 機車事故 66 / 路權政策 7 / 道安政策 7 / 路口安全 6 / 行人事故 3 /
             道路施工 1 / 科技執法 1 / 酒駕 1 / 大型車安全 1 / uncategorised 26
W29 (n=87):  機車事故 50 / 道安政策 10 / 路權政策 6 / 大型車安全 3 / 路口安全 3 /
             行人事故 2 / 道路施工 2 / 酒駕 1 / uncategorised 10
```

**SC-003 的人工計時基線待補**——「從載入到指出第一篇想讀的文章」需由使用者本人實測，
無法由助理代測。在該數字取得前，SC-003 的階數比照 SC-001／SC-002 記為「未量測」。

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
