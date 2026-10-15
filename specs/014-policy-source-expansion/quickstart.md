# Quickstart: 補政策 digest 的來源

本機操作。`python` 不在 PATH，一律用 `.venv/bin/python`。

## 1. 評估一份提案的來源清單（上線前，唯讀）

```bash
cp config/sources_traffic.yml /tmp/<scratch>/proposal.yml     # 從現行清單開始
# 編輯 proposal.yml：加候選、改既有來源的 query、設 relevance_exempt／lookback_days
# 需要新的來源預設類別時，在檔尾加 source_defaults:（只放新增或覆寫的那幾條）
.venv/bin/python scripts/evaluate_sources.py /tmp/<scratch>/proposal.yml
```

讀輸出：

- 漏斗行：候選掉在哪一關（過濾那關掉光＝相關性檢查擋掉；匯流四類為 0 但寫入上限 > 0＝分到別類）。
- 每個來源的匯流四類標題：逐篇判讀正題與否，寫進驗收紀錄（SC-004）。**正題進池 > 0 才算過 Gate（SC-001 L0）。**
- embedding 呼叫篇數：本機 key 與 prod 同一把，評估本身也計費（FR-008）。
- 收集耗時：加總進 runtime 估算（research R5）。

評估是當期樣本。Google News RSS 不能回溯，量少的來源要隔幾天再評一次，不要因為一次 0 篇就下結論。

## 2. 上線（同一個 PR）

1. 把採用的變更寫進本機 `config/sources_traffic.yml`（與 `config/categories_traffic.yml`，若有新的 `source_defaults`）。
2. 同步鏡像：`config/sources_traffic.example.yml`（與 `config/categories_traffic.example.yml`）改成同樣的值，註解可保留。
3. 本機跑 `.venv/bin/python scripts/check_config_drift.py`，要綠。
4. 改 prod 變數，用重導向（不要 `--body`，多行 YAML 有 CRLF 與尾端空行陷阱）：

   ```bash
   gh variable set SOURCES_TRAFFIC_YML --env production < config/sources_traffic.yml
   ```

5. 讀回來用 YAML 解析比對，物件相同才算完成（逐字比對會被 EOL 騙）。
6. PR merge 後隔天看 daily log：新來源有漏斗行、漂移檢查綠。

回復：還原變數（從鏡像的 git 歷史取上一版），鏡像跟著 revert，同一個 PR。

## 3. 上線後每週（週驗收 routine）

- 週報 log 的 `digest[道安政策] 最大來源：… 抽掉最大剩 N`：SC-001 L1（≥ 10）。
- 同一段的 `digest[道安政策] 池來源：…`：FOCUS 列出的每個新增或調整的來源有沒有出現（SC-002；沒出現＝0 篇）。
- runtime：被 timeout 砍掉才 FAIL（憲章 IV 1.3.0）。

## 4. closeout（Gate 與 SC-003 過了就收）

- BACKLOG：移出 `GNS-008` 與 `GNS-20261005-crb`（`backlog.py remove`），新增一列追 L1／L2 與 SC-002，
  `GNS-008` 的常設重開條件搬進新列。
- `routines/weekly-verify/PROMPT.md` 的常設檢查 (A) 改指新列；`FOCUS.md` 寫入要追的來源名單。
- PR 內文寫實際做了什麼（採用與放棄的候選、各自的評估數字）。
