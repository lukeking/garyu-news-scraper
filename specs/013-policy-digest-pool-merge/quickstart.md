# Quickstart — 驗收 013 政策 digest 池匯流

**Feature**: `013-policy-digest-pool-merge` | **Date**: 2026-08-10

⚠️ `python` 不在 PATH，一律用 `.venv/bin/python`。

---

## 1. 單元測試（CI 的 required check）

```bash
.venv/bin/python -m pytest tests/unit -q
```

**期待**：全部通過（本功能實作前基準為 148 個）。

**⚠️ 通過不等於咬得到。** 依 research R4，每條核心行為要**故意改壞一次**確認測試會紅：

```bash
# 例：把集合改回單一字串比對，預期「匯流生效」那條測試失敗
# 例：把 include_categories 預設從 [] 改成非空，預期 INV-1（預設關閉）失敗
```

改壞→看它失敗→改回來。**沒做這一步，就無法分辨「測試通過」與「測試根本不可能失敗」。**

## 2. 離線重播（SC-001／SC-002 的全部數字）

純函數可直接餵真實資料，唯讀查 prod、不寫入：

```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from dotenv import load_dotenv; load_dotenv('.env')
from src.storage import _get_client
from src.analyzer import select_digest_pool
from collections import Counter
c = _get_client()
SIB = ['路權政策','科技執法','交通工程']
rows = (c.table('articles')
        .select('link,title,source,major_category,initial_quality_score')
        .eq('content_type','traffic').in_('major_category',['道安政策']+SIB)
        .gte('buffered_at','2026-08-04').execute()).data or []
base = {'quality_floor':0.18,'max_articles':25}
cur,cur_all,cur_eff = select_digest_pool(rows,'道安政策',base,set())
mer,mer_all,mer_eff = select_digest_pool(rows,'道安政策',{**base,'include_categories':SIB},set())
for tag,(sel,allp,eff) in [('現行',(cur,cur_all,cur_eff)),('匯流',(mer,mer_all,mer_eff))]:
    sc = Counter(a['source'] for a in allp)
    top,topn = sc.most_common(1)[0]
    print(f'{tag}: pool={len(allp)} eff={eff} selected={len(sel)} distinct={len(sc)} '
          f'最大={topn}({topn/len(allp):.1%}) 抽掉最大剩={len(allp)-topn}')
cl={a[\"link\"] for a in cur}; ml={a[\"link\"] for a in mer}
print(f'擠出 {len(cl-ml)}／新進 {len(ml-cl)}')
"
```

**期待**（2026-08-10 錨定值；不同週的數字會不同，看的是**方向與門檻關係**）：

| 指標 | 現行 | 匯流後 | 判準 |
|---|---|---|---|
| `pool_all` | 37 | 46 | 變大 |
| `distinct_sources` | 3 | **9** | **SC-001 L0：嚴格變大** |
| 最大來源佔比 | 75.7% | 60.9% | 下降（SC-001 L2 需 ≤50%，**尚未達成**） |
| 抽掉最大來源剩 | 9 | **18** | **SC-001 L1：≥ `trigger_count`(10) ＝ 承重解除** |
| 擠出／新進 | — | 9／9 | **SC-002 L0：擠出 ≤ 新進，且全可歸因** |

## 3. SC-002 的可歸因性檢查

```bash
# 在上面的腳本尾端加：印出擠出者與新進者的分數區間
# 期待：擠出上界 < 新進下界（無交錯）→ SC-002 L1
# 2026-08-10 錨定：擠出 0.193–0.199／新進 0.299–0.348
```

**每一筆擠出都要能歸因**，不能有「不知道為什麼消失了」的文章。
若出現交錯（某篇擠出者分數高於某篇新進者），表示排序邏輯被動到了，**回頭查**。

## 4. SC-003 雜訊人工判讀（不得略過）

列出匯流新進的文章標題，逐篇判讀是否離題：

```bash
# 從步驟 2 的 ml-cl 取出標題印出（每週約 9 篇，人工讀完約 2 分鐘）
```

**MUST 把判讀結果寫進驗收紀錄**：哪幾篇算離題、為什麼。
2026-08-10 已知一例：「頻變換車道.行駛禁行機車道 一查又是毒駕」（刑案，非政策）。

**這個數字是 BACKLOG #7（政策 token 表）的動機依據**——不記錄，#7 就沒有校準起點。

## 5. 設定驗證的負向測試

```bash
# 暫時把 include_categories 改成字串（非 list），預期載入時 RuntimeError
# 暫時放一個不存在的類別名，預期 WARNING 且流程繼續
```

**兩者都要實際跑一次。** C1-2／C1-4 是本功能對憲章 I「禁止靜默失敗」的答覆，
沒驗證過就只是宣稱。

## 6. Prod 部署（比照 012 T013）

```bash
gh variable set PIPELINE_CONFIG_YML --env production < config/pipeline_config.yml
gh variable get PIPELINE_CONFIG_YML --env production   # 比對
```

**⚠️ 驗證只能用 YAML parse 比物件，不可比位元組。** 012 實測：
`gh variable set < 檔案` 會把尾端 `\r\n` 存成單一 `\n`（bytes −1），偏移方向與大小不可預測。

```bash
.venv/bin/python -c "
import yaml, subprocess
local = yaml.safe_load(open('config/pipeline_config.yml', encoding='utf-8'))
remote = yaml.safe_load(subprocess.run(
    ['gh','variable','get','PIPELINE_CONFIG_YML','--env','production'],
    capture_output=True, text=True).stdout)
print('identical =', local == remote)
"
```

**同步 `config/pipeline_config.example.yml`**——它是唯一進 git 的副本，
不同步的話這個決策在 repo 裡不留痕跡。

## 7. 上線後第一份週報

下一個週一的週報跑完後：

- 確認 log 出現 **C3 的池組成行**（含零篇類別）
- 確認 `digest[道安政策]` 的 `pool` 數字與離線重播一致
- 確認報告標題仍是 **「道安政策 · 彙整」**（FR-009，不得變）
- 執行步驟 4 的雜訊判讀並記錄

---

## 驗收紀錄（2026-08-10，實作當次）

| 步驟 | 結果 |
|---|---|
| 1 單元測試 | **167 passed** |
| 1 **突變驗證** | **4/4 咬到**（見下表） |
| 2 離線重播 | pool 37→46、distinct 3→9、抽掉最大 9→**18** |
| 3 SC-002 歸因 | 擠出 9 ＝ 新進 9；擠出上界 **0.199** < 新進下界 **0.299**，無交錯 |
| 4 SC-003 雜訊 | **明確離題 0/9**；邊緣 2（機車行開業法規）；殘餘近似重複 2 組 |
| 5 設定負向 | 型別錯 → `RuntimeError` ✅；未知類別 → WARNING 且續行 ✅ |
| 6 prod 部署 | **待執行（T017）** |
| 7 週報驗收 | **待下週一（T018）** |

### 突變驗證明細（步驟 1）

「測試通過」與「測試不可能失敗」只能靠故意改壞來分辨。四次改壞、四次變紅、四次還原：

| # | 改壞什麼 | 結果 |
|---|---|---|
| 1 | `major_category in categories` → 改回 `== category` | **2 failed** ✅ |
| 2 | `include_categories` 預設 `[]` → `["路權政策"]` | **2 failed** ✅ |
| 3 | 選材時原地改寫 `major_category` | **2 failed** ✅ |
| 4 | 拿掉未知類別的 `logger.warning` | **1 failed** ✅ |

還原後 167 passed。**第 4 條特別重要**——它守的是憲章 I「禁止靜默失敗」，
若那條測試是空的，任何人拿掉 WARNING 都不會有東西擋。

### 已知的空過測試（誠實標註）

`test_merged_respects_excluded_links` 與 `test_list_order_does_not_affect_output`
在 T005 實作**之前**就是綠的——它們測的是與匯流的*交互*，匯流不存在時自然通過。
實作後才有牙齒。記錄於此，避免日後誤讀成「這兩條從頭就守住了什麼」。
