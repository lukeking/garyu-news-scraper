"""
mailer.py
組裝 HTML 週報信件並透過 Gmail SMTP 寄送
"""

import os
import smtplib
import logging
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

TW_TZ = timezone(timedelta(hours=8))

IMPORTANCE_COLOR = {
    "高": ("#FFF0F0", "#C0392B", "🔴"),
    "中": ("#FFFBF0", "#D68910", "🟡"),
    "低": ("#F0FFF4", "#27AE60", "🟢"),
}

SOURCE_BADGE_COLOR = {
    "Google News":  "#4285F4",
    "PTT/biker":    "#FF4500",
    "PTT/car-moto": "#FF4500",
    "聯合新聞網":   "#1A3C6E",
    "中時新聞網":   "#C0392B",
    "自由時報":     "#27AE60",
    "TVBS新聞":     "#2980B9",
    "ETtoday":      "#E74C3C",
    "交通部":       "#8E44AD",
    "公路局":       "#7D6608",
}


def _source_badge(source: str) -> str:
    color = SOURCE_BADGE_COLOR.get(source, "#555555")
    return (
        f'<span style="display:inline-block;padding:2px 8px;'
        f'border-radius:4px;font-size:11px;font-weight:600;'
        f'background:{color};color:#fff;">{source}</span>'
    )


def _article_card(article: dict, index: int) -> str:
    analysis = article.get("analysis", {})
    importance = analysis.get("importance", "中")
    bg, border_color, dot = IMPORTANCE_COLOR.get(importance, IMPORTANCE_COLOR["中"])
    source = article.get("source", "")
    title = article.get("title", "（無標題）")
    link = article.get("link", "#")
    summary_text = analysis.get("summary", "")
    analysis_text = analysis.get("analysis", "")
    reason = analysis.get("importance_reason", "")
    published = article.get("published", "")

    published_html = (
        f'<span style="color:#999;font-size:12px;margin-left:8px;">{published}</span>'
        if published else ""
    )

    return f"""
<div style="margin-bottom:24px;border-radius:10px;overflow:hidden;
     border:1.5px solid {border_color}30;background:{bg};
     box-shadow:0 2px 6px rgba(0,0,0,0.05);">

  <!-- 標題列 -->
  <div style="padding:14px 18px 10px;border-bottom:1px solid {border_color}20;">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:6px;">
      <span style="font-size:13px;font-weight:700;color:{border_color};">{dot} {importance}重要</span>
      {_source_badge(source)}
      {published_html}
    </div>
    <a href="{link}" style="font-size:16px;font-weight:700;color:#1a1a2e;
       text-decoration:none;line-height:1.4;display:block;">
      {index}. {title}
    </a>
  </div>

  <!-- 摘要 -->
  <div style="padding:12px 18px 0;">
    <p style="margin:0 0 4px;font-size:12px;font-weight:700;
       color:{border_color};letter-spacing:0.5px;">📋 摘要</p>
    <p style="margin:0;font-size:14px;line-height:1.7;color:#333;">{summary_text}</p>
  </div>

  <!-- 深度分析 -->
  <div style="padding:10px 18px 0;">
    <p style="margin:0 0 4px;font-size:12px;font-weight:700;
       color:{border_color};letter-spacing:0.5px;">🔍 深度分析</p>
    <p style="margin:0;font-size:14px;line-height:1.7;color:#333;">{analysis_text}</p>
  </div>

  <!-- 重要性理由 + 原文連結 -->
  <div style="padding:10px 18px 14px;display:flex;justify-content:space-between;
       align-items:flex-end;flex-wrap:wrap;gap:8px;">
    <p style="margin:0;font-size:12px;color:#666;font-style:italic;">
      💡 {reason}
    </p>
    <a href="{link}" style="font-size:12px;color:{border_color};
       font-weight:600;text-decoration:none;white-space:nowrap;">閱讀原文 →</a>
  </div>
</div>
"""


def build_html(articles: list) -> str:
    now_tw = datetime.now(TW_TZ)
    date_str = now_tw.strftime("%Y 年 %m 月 %d 日")
    # ISO 週數
    week_num = now_tw.isocalendar()[1]

    high = [a for a in articles if a.get("analysis", {}).get("importance") == "高"]
    mid  = [a for a in articles if a.get("analysis", {}).get("importance") == "中"]
    low  = [a for a in articles if a.get("analysis", {}).get("importance") == "低"]

    cards_html = ""
    for i, article in enumerate(articles, 1):
        cards_html += _article_card(article, i)

    stats_html = f"""
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px;">
  <div style="flex:1;min-width:100px;background:#FFF0F0;border-radius:8px;
       padding:12px 16px;text-align:center;border:1px solid #C0392B30;">
    <div style="font-size:26px;font-weight:700;color:#C0392B;">{len(high)}</div>
    <div style="font-size:12px;color:#666;margin-top:2px;">🔴 高重要性</div>
  </div>
  <div style="flex:1;min-width:100px;background:#FFFBF0;border-radius:8px;
       padding:12px 16px;text-align:center;border:1px solid #D6891030;">
    <div style="font-size:26px;font-weight:700;color:#D68910;">{len(mid)}</div>
    <div style="font-size:12px;color:#666;margin-top:2px;">🟡 中重要性</div>
  </div>
  <div style="flex:1;min-width:100px;background:#F0FFF4;border-radius:8px;
       padding:12px 16px;text-align:center;border:1px solid #27AE6030;">
    <div style="font-size:26px;font-weight:700;color:#27AE60;">{len(low)}</div>
    <div style="font-size:12px;color:#666;margin-top:2px;">🟢 低重要性</div>
  </div>
  <div style="flex:1;min-width:100px;background:#F0F4FF;border-radius:8px;
       padding:12px 16px;text-align:center;border:1px solid #2980B930;">
    <div style="font-size:26px;font-weight:700;color:#2980B9;">{len(articles)}</div>
    <div style="font-size:12px;color:#666;margin-top:2px;">📰 總計</div>
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台灣機車交通週報 W{week_num}</title>
</head>
<body style="margin:0;padding:0;background:#F5F6FA;font-family:'Helvetica Neue',Arial,sans-serif;">

<div style="max-width:680px;margin:0 auto;padding:20px 12px;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1A3C6E 0%,#2980B9 100%);
       border-radius:12px;padding:28px 28px 22px;margin-bottom:20px;color:#fff;">
    <div style="font-size:12px;opacity:0.8;letter-spacing:1px;margin-bottom:6px;">
      台灣機車交通週報
    </div>
    <div style="font-size:26px;font-weight:800;line-height:1.2;margin-bottom:4px;">
      🏍️ W{week_num} 機車交通新聞
    </div>
    <div style="font-size:14px;opacity:0.85;">{date_str}（自動彙整）</div>
  </div>

  <!-- Stats -->
  {stats_html}

  <!-- 說明 -->
  <div style="background:#E8F4FD;border-radius:8px;padding:12px 16px;
       margin-bottom:24px;font-size:13px;color:#1A5276;line-height:1.6;">
    📌 本週報自動收集台灣交通相關新聞，涵蓋白牌機車、紅黃牌重機、法規異動、
    事故分析等議題。每則新聞均經 AI 摘要與深度分析，依重要性排序呈現。
  </div>

  <!-- 文章卡片 -->
  {cards_html}

  <!-- Footer -->
  <div style="text-align:center;padding:20px 0 8px;
       font-size:12px;color:#999;border-top:1px solid #e0e0e0;margin-top:8px;">
    由 GitHub Actions + Gemini AI 自動產生 · 每週一寄送<br>
    來源：Google News、PTT 機車板、各大新聞網、交通部公告
  </div>

</div>
</body>
</html>"""


def send_email(html_content: str, article_count: int) -> None:
    sender = os.environ["GMAIL_SENDER"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipient = sender  # 同一個 email

    now_tw = datetime.now(TW_TZ)
    week_num = now_tw.isocalendar()[1]
    date_str = now_tw.strftime("%Y/%m/%d")
    subject = f"🏍️ 台灣機車交通週報 W{week_num}（{date_str}）｜共 {article_count} 則新聞"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"機車交通週報 <{sender}>"
    msg["To"] = recipient

    # 純文字版 fallback
    plain = f"台灣機車交通週報 W{week_num}\n本週共 {article_count} 則相關新聞\n請以 HTML 格式查看。"
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    logger.info(f"寄送週報至 {recipient}...")
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
    logger.info("✓ 信件寄送成功！")