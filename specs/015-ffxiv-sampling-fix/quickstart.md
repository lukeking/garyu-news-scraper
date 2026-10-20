# Quickstart: FFXIV 週報取樣修正

## 本機驗證（不寫庫、不呼叫 Gemini）

```bash
.venv/bin/python -m pytest tests/unit -q --ignore=tests/unit/test_comment_budget.py   # CI 的 unit 同一組
.venv/bin/python - <<'EOF'
from unittest.mock import patch
from src import collector
from src.pipeline.ffxiv import FFXIVCategory
with patch.object(collector, "FFXIV_SOURCES_FILE", "config/sources_ffxiv.example.yml"):
    c = FFXIVCategory()
    raw = c.collect()          # 真實入口：會打論壇、Lodestone、Reddit
    picked = c.filter(raw)     # 真實入口：讀 Supabase 的標題指紋（唯讀），印候選池與入選
for a in picked:
    print(a.get("source_weight"), a["source"], a["title"][:40])
EOF
```

⚠️ 不要用環境變數 `SOURCES_FFXIV_YML` 換設定：`load_ffxiv_sources` 在本機有 `config/sources_ffxiv.yml` 時只讀那個檔，
環境變數被安靜地忽略（2026-10-20 T026 撞到）。也不要覆蓋本機那份——它是 prod 的副本。換 `FFXIV_SOURCES_FILE` 這個路徑。

看 log：候選池與入選的逐來源篇數、每串「窗口內 N 則、收 M 則、翻 P 頁」、Lodestone「解析 N 則、收進 M 則」、`來源失敗` 那一行。

`filter()` 會讀 Supabase（`get_existing_title_fingerprints`，唯讀）；`.env` 指向 prod。不要呼叫 `analyze()`／`store()`／`publish()`。

## SC-004 實測（程式 merge 後、prod 變數改之前）

用 prod 現行的設定（Lodestone 仍是 `category/2` 與 `li.news__list--topics`）跑一次收集：

```bash
gh variable get SOURCES_FFXIV_YML --env production > <scratchpad>/sources_ffxiv.prod.yml   # 不放 repo 內
.venv/bin/python -c "
from unittest.mock import patch
from src import collector
from src.pipeline.ffxiv import FFXIVCategory
with patch.object(collector, 'FFXIV_SOURCES_FILE', '<scratchpad>/sources_ffxiv.prod.yml'):
    FFXIVCategory().collect()"
```

`來源失敗` 名單要有 `FFXIV Lodestone JP 更新資訊`，而且有一行「回 200 但解析出 0 項」。

## 上線

1. PR merge（程式、測試、鏡像 example 都在裡面）。
2. 改 prod 變數，逐位元組比對：
   ```bash
   gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.example.yml
   gh variable get SOURCES_FFXIV_YML --env production | diff - config/sources_ffxiv.example.yml && echo identical
   cp config/sources_ffxiv.example.yml config/sources_ffxiv.yml   # 本機副本跟著 prod
   ```
   鏡像 example 已在 PR 裡改好，prod 變數 merge 後同一天改（漂移檢查每天 00:00 UTC 跑）。避開週一 00:00 UTC 前後。
3. 第一次週報後讀 log（見上）；SC-001 的兩週判定、SC-002、SC-005、SC-006 由 `FOCUS.md` 判讀、寫回 BACKLOG `GNS-20261020-sbe`。

## 回復（FR-012）

- 論壇：五個版改回 `type: rss`、去掉 `lastpost=1`。
- 權重：拿掉所有 `weight`（全部當 0 → 依時間排序）。
- Lodestone：拿掉 `date_pattern`／`exclude_title_prefixes`／`detail_selector`。
- 都只改 `SOURCES_FFXIV_YML` 與鏡像，不必改程式。
