# Quickstart: 驗這個 spec 的每一片

名字（workflow 檔名、輸入的值）照 `contracts/dry-run.md` 的提案寫，tasks 定案後跟著改。指令是片 1 做完之後才跑得動的。

## 片 1：單元測試

```bash
.venv/bin/python -m pytest tests/unit -q
```

看三件事：全套的摘要行沒有 failed；`test_storage_dry_run.py` 列到的寫入函式數等於 `src/storage.py` 裡的寫入函式數；`test_workflow_parity.py` 有跑到。

## 片 1 的實跑：兩級各一次（片 1 進預設分支之後）

1. 觸發前取五個計數（報告數、buffer 筆數、彙整池未分析筆數、兩個站的最後部署時間、術語庫的條目數），記下來。
2. 觸發第一級：

   ```bash
   gh workflow run weekly-dry-run.yml --ref <要驗的分支> -f level=input
   ```

3. 等它跑完，讀執行紀錄：開頭那一行是第一級；每一種寫入各有一行 `[不發布] 略過 …`；LLM 呼叫 0 次。下載產物，看收集數、過濾後數與入選清單。
4. 再取一次五個計數，跟第 1 步相同。
5. 第二級重複第 2～4 步（`-f level=full`），另外讀分析輸出的全文與術語收錄的結果。
6. 結果（run id、計數的前後、讀到什麼）寫進片 1 實跑的紀錄。

## `#218` 的接線（片 1 進預設分支之後）

`#218` 的分支先 merge `main` 拿到不發布的 workflow，再對那個分支觸發第二級。
紀錄裡找四條呼叫路徑各自印的模型設定那一行（三軸、彙整、FFXIV 逐篇、術語收錄）。結果寫在 `#218` 上。

## 片 2＋3：憲章與流程接點

一輪 cold review。另外做 spec User Story 2 的 Independent Test：拿盤點表的一列，只讀憲章寫出它的分片與驗法，跟盤點表對照。

## 片 4：盤點表的項目

逐列對照 `specs/BACKLOG.md` 盤點表與改寫後的驗收條件（SC-004）。

## 讀回

片 1 之後第一次排程的週報：紀錄裡沒有任何 `[不發布]` 開頭的行，寫入與發布的項目跟前一週同類（SC-006）。
