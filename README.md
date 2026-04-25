# 🏍️ 台灣機車交通週報自動系統

每週自動收集台灣機車交通相關新聞，透過 Gemini AI 分析摘要，寄送至 Gmail。

## 架構

```
收集（collector.py）
  ├── Google News RSS
  ├── PTT 機車板 / car-moto 板
  ├── 聯合/中時/自由/TVBS/ETtoday RSS
  └── 交通部 / 公路局公告
        ↓
過濾去重（filter.py）
        ↓
AI 分析（analyzer.py）── Gemini 2.0 Flash（免費）
        ↓
HTML 週報 + Gmail 寄送（mailer.py）
```

## 排程

每週一台灣時間 08:00 自動執行（GitHub Actions）。

## 設定步驟

### 1. Fork 或 clone 此 repo

### 2. 取得必要的 API Key / 密碼

| 項目 | 取得方式 |
|------|---------|
| Gemini API Key | [aistudio.google.com](https://aistudio.google.com) → Get API key |
| Gmail App Password | Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼 |

### 3. 在 GitHub 設定 Secrets

前往 repo → **Settings → Environments → New environment**，命名為 `production`，
然後在該 environment 加入以下 secrets：

| Secret 名稱 | 說明 |
|------------|------|
| `GEMINI_API_KEY` | Gemini API 金鑰 |
| `GEMINI_MODEL_NAME` | Gemini Model 名稱 (optional, default=gemini-2.5-flash) |
| `GMAIL_APP_PASSWORD` | Gmail 應用程式密碼（16位數）|
| `GMAIL_SENDER` | 你的 Gmail 地址（同時為收件者）|

### 4. 手動測試

在 GitHub → Actions → `台灣機車交通週報` → **Run workflow**，
確認執行成功後即完成設定。

## 本機測試

```bash
pip install -r requirements.txt

export GEMINI_API_KEY="your_key"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export GMAIL_SENDER="your@gmail.com"

python main.py
```

## 注意事項

- Gemini 免費 tier 每分鐘有請求數限制，程式已內建 2 秒間隔
- 每次最多分析 30 篇文章（可在 `main.py` 調整）
- GitHub Actions 免費方案每月 2,000 分鐘，本 job 每次約 5 分鐘，一年約用 260 分鐘
