# Quickstart: FFXIV 週報取樣修正

## 本機驗證（不寫庫、不呼叫 Gemini）

```bash
.venv/bin/python -m pytest tests/unit -q                      # CI 的 unit 同一組
cp config/sources_ffxiv.example.yml config/sources_ffxiv.yml   # 本機設定＝鏡像（gitignored）
.venv/bin/python - <<'EOF'
from src.pipeline.ffxiv import FFXIVCategory
c = FFXIVCategory()
raw = c.collect()          # 真實入口：會打論壇、Lodestone、Reddit
picked = c.filter(raw)     # 真實入口：讀 Supabase 的標題指紋（唯讀），印候選池與入選
for a in picked:
    print(a.get("source_weight"), a["source"], a["title"][:40])
EOF
```

看 log：候選池與入選的逐來源篇數、每串「窗口內 N 則、收 M 則、翻 P 頁」、Lodestone「解析 N 則、收進 M 則」、`來源失敗` 那一行。

`filter()` 會讀 Supabase（`get_existing_title_fingerprints`，唯讀）；`.env` 指向 prod。不要呼叫 `analyze()`／`store()`／`publish()`。

## SC-004 實測（程式 merge 後、prod 變數改之前）

用 prod 現行的設定（Lodestone 仍是 `category/2` 與 `li.news__list--topics`）跑一次收集：

```bash
gh variable get SOURCES_FFXIV_YML --env production > <scratchpad>/sources_ffxiv.prod.yml   # 不放 repo 內
SOURCES_FFXIV_YML="$(cat <scratchpad>/sources_ffxiv.prod.yml)" \
  .venv/bin/python -c "from src.pipeline.ffxiv import FFXIVCategory; FFXIVCategory().collect()"
```

`來源失敗` 名單要有 `FFXIV Lodestone JP 更新資訊`，而且有一行「回 200 但解析出 0 項」。

## 上線

1. PR merge（程式＋測試＋鏡像 example 可以晚一步，見 2）。
2. 改 prod 變數，逐位元組比對：
   ```bash
   gh variable set SOURCES_FFXIV_YML --env production < config/sources_ffxiv.yml
   gh variable get SOURCES_FFXIV_YML --env production | diff - config/sources_ffxiv.yml && echo identical
   ```
   同一天讓鏡像 example 與它一致（漂移檢查每天跑）。避開週一 00:00 UTC 前後。
3. 第一次週報後讀 log（見上），寫進驗收紀錄；SC-001 的兩週判定交給 `FOCUS.md`。

## 回復（FR-012）

- 論壇：五個版改回 `type: rss`、去掉 `lastpost=1`。
- 權重：拿掉所有 `weight`（全部當 0 → 依時間排序）。
- Lodestone：拿掉 `date_pattern`／`exclude_title_prefixes`／`detail_selector`。
- 都只改 `SOURCES_FFXIV_YML` 與鏡像，不必改程式。
