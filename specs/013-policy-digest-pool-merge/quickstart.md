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

---

## 上線後驗收紀錄（2026-08-17，prod 第一份週報）— T018

Actions run `31982316426` success，**7m47s**（前次 10m21s；憲章 IV 的 10 分上限本次未被撞到，
與 3.7-flash 生成快 ~2× 的預期方向一致，但這是單點觀察不是對照實驗）。
本週**零個 bucket 通過 novelty gate**，整份週報就是這篇 digest。

| 檢查（步驟 7） | 結果 |
|---|---|
| C3 池組成行 | ✅ `digest[道安政策] 池組成：道安政策 32 ＋ 路權政策 37 ＋ 科技執法 10 ＋ 交通工程 7 = 86` |
| 池組成含**零篇**類別 | ⚠️ **本週未驗到**——四類皆非零（最少的 `交通工程` 是 7）。見下方「缺口」 |
| `pool` 與離線重播一致 | ✅ 逐項相同：pool **86**／effective **84**／selected **25**，且**選材集合與已發布報告逐篇相同** |
| 標題 FR-009 | ✅ `道安政策 · 彙整`（`hot_topic_report upserted: 2026-08-17 / 道安政策 · 彙整`） |
| 步驟 4 SC-003 雜訊判讀 | ✅ 已執行，見下 |

### 重播方法（與 08-10 那次不同，記在這裡以免下次重推）

08-10 是「拿當下的 buffer 重播」。**上線後不能這樣做**——池已被消耗（`consumed=86`），
現在查 buffer 只會拿到 0 篇。這次的做法：從 Actions log 的兩個
`PATCH …/articles?link=in.(…)` 還原被標記的 86 條連結（25 選材 ＋ 61 殘餘，無重疊），
回 DB 取回原始列後重跑 `select_digest_pool`。

**反向檢查（避免「重播只是複述 log」）**：查「run 之前入 buffer、未過期、至今仍未消耗」的
四類文章 → **0 篇**。池若漏抓，殘留物會出現在這裡。

**（2026-08-18）這個方法已收成 `scripts/replay_digest_pool.py`**，任何一週都可直接跑：

```bash
.venv/bin/python scripts/replay_digest_pool.py <RUN_ID>
```

它印出重建池組成（**與 log 的池組成行對帳的自我檢查**）、以**整池為分母**的 SC-001 數字、
以及匯流新進清單供 SC-003 判讀；設定從本機 `config/pipeline_config.yml` 讀，不寫死常數。

### SC-001（真實 prod 資料）

| 指標 | 現行（不匯流） | 匯流後 | 判準 |
|---|---|---|---|
| `pool_all` | 32 | **86** | 變大 ✅ |
| `distinct_sources` | 3 | **13** | L0 嚴格變大 ✅ |
| 最大來源佔比 | 78.1% | **29.1%** | L2（≤50%）**本次達成**，但見下方警語 |
| 抽掉最大來源剩 | **7**（< 門檻 10） | **61** | L1 承重解除 ✅ |

⚠️ **86 不是穩態，L2 不可據此結案。** 013 於 08-14 才部署，08-10 那次跑的是
`pool=37 consumed=37` 且**沒有池組成行**（`include_categories` 尚未生效）→ 兄弟類別
從未被 digest 消耗過，這次是一口氣抽乾積壓。穩態要看 08-24 那份。

另一個**獨立**的事實：若沒有 013，本週抽掉最大 feed 只剩 **7 篇 < `trigger_count` 10**——
承重在真實 prod 資料上再次成立，不是只在 08-10 的抽樣裡成立。

### SC-002 歸因

擠出 **22** ＝ 新進 **22**；擠出區間 **0.188–0.232**、新進區間 **0.325–0.491**，**無交錯**（L1 ✅）。
每一筆擠出都可歸因：全部是 `道安政策` 的低分宣導稿（金安獎、校園宣導、桌遊宣導⋯），
被兄弟類別的高分實文擠掉——正是 013 要的方向。

### SC-003 雜訊判讀（BACKLOG #7 的校準起點）

22 篇新進逐篇讀完：**明確離題 2/22（9.1%）**，邊界 4/22。

| 判定 | 篇數 | 實例 |
|---|---|---|
| 明確離題 | 2 | 「路權至上！宏佳騰 STR X⋯#Aeonmotor」（車媒行銷）／「淡水軍車遭大貨車拖撞行人庇護島」（事故簿，非政策） |
| 邊界 | 4 | 駕艙機車「半殘」評論 ×3、駕艙機車上路時間 ×1——主軸是產品，但確實承載路權／法規內容 |
| 切題 | 16 | 蘆洲取消禁行機車、花蓮科技執法轉型、違停政策解析、待轉區復舊工程⋯ |

**對 #7 的意義**：政策側的雜訊**不是**與 `機車事故` 同一種。6 篇雜訊裡 **5 篇是車媒／產品**
（`路權` token 把車媒的產品報導一起撈進來），只有 1 篇是事故簿。若照 012 的形狀做政策
require 表，要擋的主要是**車媒／產品上市**，不是刑案。

**近似重複比 08-10 明顯**（池變大的副作用）：新埔民生站待轉區復舊 ×4、花蓮科技執法 ×3、
路權鬆綁 ×3、駕艙機車半殘 ×3。屬 `embed_dedup`（threshold 0.88）**非 013**，與既有 Open Question 同一條。

### 缺口（誠實標註）

「池組成行**含零篇類別**」這半**至今沒有任何東西驗到**：本週四類皆非零，而
`grep 池組成 tests/` 是空的——這行的零篇顯示沒有單元測試守著。目前它只能等某週真的出現 0。
補一個 caplog 斷言是低成本做法，**本次刻意未做**（超出 T018 範圍），記在這裡讓它不會靜默消失。

### 補記（2026-08-18，T019 closeout 時補上）

**cloud routine 的驗收草稿**（Gmail 草稿「[驗收] 08-17 首份週報 — 013 政策 digest 池匯流（T018）」，
08-17 07:07Z）獨立跑了 log 可查的三項，結論同為 PASS／PASS／PASS，並**獨立標出同一個零篇缺口**。
它多給一個本地沒查的數字：`交通工程` 過去三週僅 5 篇、**08-10 當週僅 1 篇**——本來最可能出現 0
的就是這一類，本週卻是 7。兩邊獨立得到同一個缺口，這個缺口不是判讀差異。

**它交棒的「逐來源分解」已補跑，但要注意分母不同**（照抄比較會踩到）：

| 分母 | distinct_sources | 最大來源 | 抽掉最大剩 |
|---|---|---|---|
| **整池 86 篇**（08-10 錨定值的算法） | 13 | `交通安全教育` 25（29.1%） | 61 |
| **已發布 25 篇**（草稿腳本的算法） | 10 | `機車待轉` 5（20.0%） | 20 |

08-10 的錨定值（distinct 3→9、75.7%→60.9%、9→18）是**以整池為分母**算的，
所以草稿裡那支腳本的輸出**不能直接跟那三個數字比**——要比就用整池那列。

**最值得記的一個數字**：`Google News 交通安全教育` 在**已發布的 25 篇裡是 0 篇**。
它在 07-27／08-03／08-10 分別佔已發布的 72%／68%／68%，本週池裡仍有 25 篇卻**一篇都沒進報告**——
全部落在 quality 0.188–0.232 的宣導稿區間，被兄弟類別的高分實文擠掉（見上方 SC-002）。
**單一 feed 依賴在「發布面」上已經歸零**，不只是池的佔比下降。
