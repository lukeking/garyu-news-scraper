# Quickstart: 019 驗證

## 上線前（本機）

```bash
.venv/bin/python -m pytest tests/unit -q --ignore=tests/unit/test_comment_budget.py
.venv/bin/python -m pytest tests/unit/test_comment_budget.py -q
```

- spike（research R3–R5）：對英文 642、656 的 RSS 各打一次讀子版 id；每個子版取一串比對 RSS `pubDate` 與頁面 `span.date`；
  數各子版 `lastpost=1` RSS 裡窗口內的串數。請求間隔至少 30 秒，429 就停。結果寫回 research。
- 本機有 `config/sources_ffxiv.yml` 時不讀環境變數（project memory `reference_local_ffxiv_config_patch.md`）；本機試跑換設定用 `patch.object`。

## 上線後（每週，連兩週）

- 讀週報 log：`FFXIV 候選池`、`FFXIV 入選`、截掉論壇串那一行、`來源失敗`。
- `gh run download <run id> -n ffxiv-pool`：數英文版、Reddit（應為 0）、論壇列表頁（應為 0）；英文版逐篇判讀「講得出這週在討論什麼」。
- 對照同一週各版 RSS 的窗口內串數（SC-001 L1）。
- 週報耗時、FFXIV 分析篇數（SC-005）。
- 結果寫進 `specs/019-ffxiv-sampling-window/evaluation.md`。
