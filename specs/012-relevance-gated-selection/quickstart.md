# Quickstart: 相關性選材閘（feature 012）

驗收敘事＝**爬到 SC 階梯第幾階**，不是單一 pass/fail。核心邏輯是純函數，全程零 AI、零憑證、可離線跑。

## 前置：環境

```bash
# 單元測試（純函數，零外部依賴）——CI 上跑的就是這個
python -m pytest tests/unit -q
```
規則改在本機 config 檔（`config/categories_traffic.yml`、`config/pipeline_config.yml`）；
正式環境真身在 GitHub env var（`CATEGORIES_TRAFFIC_YML`／`PIPELINE_CONFIG_YML`），
上線流程見 `CLAUDE.local.md`（改本機檔 → `gh variable set --env production` → `gh variable get` 比對）。
**改 config 一律同步 `*.example.yml`**（憲章 II：example 是唯一進 git 的副本）。

## 步驟 1 — 建人工標記基準集（一次性，可增量）

`scripts/measure_relevance.py` 需要一份 ground truth 才能量。做法：

1. 從 buffer 匯出取樣週的候選（title／source／major_category），至少涵蓋 08-03 兩錨案
   （`機車事故·中時` 刑案混雜、`機車事故·金線` 行銷整席）＋另外 2–3 週。
2. **人工**逐篇標 `on`/`off`（見 `data-model.md` §4 欄位）。邊界案（肇事逃逸＝刑案∩事故）標 `on` 並註記。
3. 存成版控檔（去識別化，只留 title／source／label）。
4. ⚠️ 禁止用閘的輸出回填 label（自己改自己的考卷）。

## 步驟 2 — 填 seed 規則

- `categories_traffic.yml` 加 `relevance_rules.機車事故`（`require_any` 事故 token／`exclude_any` 刑案·市場 token，見 data-model §1）。
- `pipeline_config.yml` 的 `blocked_content_keywords` 補市場詞（油耗／市佔／銷量／戰報…，Tier 1）。

## 步驟 3 — 重播、讀 SC 階梯

```bash
# 唯讀診斷：對基準集重播「套閘前 vs 套閘後」的發布名單
python scripts/measure_relevance.py --baseline <基準集檔>
```
輸出應回答：

| 指標 | 判準 | 對應 |
|---|---|---|
| 任一發布熱點是否仍「多數（>50%）離題」 | 否 = 過 | **SC-001（Gate）** |
| 各發布熱點的離題比例 | ≤ 20% | SC-002 |
| 取樣週發布熱點內離題數 | → 0 | SC-003（理想） |
| 真正 on-topic 文章的發布數 | 不下降 | **SC-004（不回歸）** |

- 只過 SC-001＝Gate 達標（金線整席不再發布），可交付。
- 卡在 SC-002＝回步驟 2 調 token 表**對著基準集**調（decision-style：對後果調，不對印象調）。
- 若調到底仍撞 SC-002 且殘餘皆語意型離題 → 觸發 research D2 的「LLM 僅對殘餘」重開條件，另議。

## 步驟 4 — 單元測試（行為鎖）

`tests/unit/test_relevance_gate.py` 至少涵蓋：
- 白名單：真事故（撞／送醫）通過。
- 黑名單：純竊盜／毒駕羈押 被擋。
- **AND-NOT 邊界**：肇事逃逸（刑案∩事故）**保留**——這條是回歸重災區，務必有測。
- **整桶清空 → 不發布**（FR-003）：某桶候選全 off → 不成桶、不 select。
- fail-open：規則缺鍵／格式錯 → 該類別不套閘、不誤殺整類，且有 log。
- 純度：閘不呼叫外部服務、不改 `major_category`、不寫 DB（FR-006 / data-model 不變式）。

## 驗收邊界（誠實標註）

- SC-001/002/003/004 的量測**依賴人工基準集**；沒有基準集就只有主觀印象，不算達標（承 011 之戒）。
- 每日 buffer 列表的離題清理**不在本功能範圍**（那是 BACKLOG #5，且會動每日路徑）。本功能只清**發布的週報**。
- 政策 digest 的 #7 離題**不在本 spec**（08-05 範圍決定）；若本閘機制通用，日後可沿用。
