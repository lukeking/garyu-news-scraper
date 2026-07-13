# Quickstart — 低頻類別聚合式深度分析（010）

本機驗證步驟。前提：`.env`（Supabase＋Gemini 金鑰）與 `config/pipeline_config.yml`、`config/categories_traffic.yml` 已就緒（gitignored 工作副本）。

## 1. 單元＋整合測試

```bash
.venv/bin/python -m pytest tests/ -q
```

重點案例（tasks 會逐一落實）：
- 觸發計數：quality_floor 邊界（0.165 排除／0.193 納入）、篇數門檻。
- 席次保留：1 digest 觸發 → 一般 bucket 只取 2 格；digest 超額不消耗。
- 空簽章：digest prior 永不匹配（`compute_jaccard` 空集合）。
- 消耗語意：upsert 成功才標記；失敗路徑零消耗。
- config 驗證：非法值 raise；空設定 = feature off（SC-004 回歸）。

## 2. Read-only 觸發統計重放（不打 Gemini、零寫入）

真實池就在 prod buffer（2026-07-13 實測：道安政策 15 篇 singleton）。用重放腳本驗證觸發統計與選材：

```bash
.venv/bin/python - <<'EOF'
import sys; sys.path.insert(0, ".")
from dotenv import load_dotenv; load_dotenv()
from src.pipeline_config import load_pipeline_config
from src.storage import get_traffic_buffer
from src.analyzer import select_digest_pool

config = load_pipeline_config()
articles = get_traffic_buffer(config["buffer"]["max_age_weeks"])
cfg = config.get("category_digest", {}).get("道安政策", {})
selected, pool, eff = select_digest_pool(articles, "道安政策", cfg, excluded_links=set())
print(f"pool={len(pool)} effective={eff} threshold={cfg.get('trigger_count', 10)}")
for a in selected:
    print(f"  q={a['initial_quality_score']:.3f} {a['title'][:50]}")
EOF
```

預期：`effective` 排除「友善列印」（0.165 < 0.18）；15 篇池 → 觸發成立。

## 3. 端到端 dry-run（一次 Gemini 呼叫，寫入本人可清理的測試週）

謹慎路徑——`traffic_weekly_analysis.py` 會真實 upsert 並**消耗池**。本機端到端驗證前先確認：

1. 願意消耗當前池（消耗後 prod 下次週跑不會再觸發同批文章）；或
2. 只驗證到步驟 2 的統計層，把端到端留給 merge 後第一次真實週跑（推薦：SC-001 本來就以真實週跑驗收，log 契約使其可直接從 Actions log 確認）。

## 4. Prod 部署（merge 後，憲章 II 慣例）

1. GitHub → Settings → Environments → production → `PIPELINE_CONFIG_YML`：加入

   ```yaml
   category_digest:
     道安政策:
       trigger_count: 10
       quality_floor: 0.18
       max_articles: 15
   ```

2. Read-back 驗證：抓下 env var 用 repo loader 解析（比照 #59 部署慣例）。
3. 下次週一跑後從 Actions log 找 `digest[道安政策] pool=... → TRIGGER` 與 `✓ hot_topic_report upserted: ... / 道安政策 · 彙整`。

## 驗收對照

| Spec SC | 驗證方式 |
|---|---|
| SC-001 | merge 後首次達門檻週跑：頁面出現「道安政策 · 彙整」報告 |
| SC-002 | 兩次 digest 的 `source_article_links` 交集 =∅（Supabase 查詢） |
| SC-003 | digest 來源清單無 quality < 0.18 者（同上） |
| SC-004 | pytest 回歸全綠＋空設定重放輸出不變 |
| SC-005 | 僅憑 Actions log 讀出 pool/effective/threshold/consumed |
