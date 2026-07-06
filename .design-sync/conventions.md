# Garyu Traffic News — build conventions

**This is a style-foundation system, not a component library.** There is no JS bundle and no React components — you write your own markup and style it with the class vocabulary and tokens below. All of it is production CSS from the live site (a Traditional-Chinese weekly news digest). Text content is zh-Hant.

## Setup

- Wrap nothing — there is no provider. Just ensure `styles.css` is loaded.
- **Dark mode**: set `data-theme="dark"` on `<html>`. Every token flips automatically; never hardcode dark colors. `--link-color` / `--link-color-visited` exist **only** in dark — always consume them with a fallback, e.g. `color: var(--link-color, var(--accent2))`.
- Base font comes from `body` ('Helvetica Neue', Arial, sans-serif). Content column is `.main` (max-width 860px, centered).

## Tokens (from `tokens/tokens.css`)

- Surfaces & text: `--bg` `--card-bg` `--text` `--text-secondary` `--text-body` `--text-muted` `--border`
- Brand: `--accent` (deep navy, headers/active) `--accent2` (bright blue, links/hover)
- Importance triad: `--high`/`--high-bg` (red), `--mid`/`--mid-bg` (amber), `--low`/`--low-bg` (green)
- Tags: `--tag-bg` `--tag-text`
- Shape: `--radius` (10px) `--shadow`

## Class vocabulary (from `_ds_bundle.css` — read it before styling)

- Header: `site-header` > `header-inner` > (`h1`+`p`) + `header-actions` (`rss-link`, `#theme-toggle`)
- Search: `search-wrap` > `search-input`
- Filter rows: `controls`+`btn-filter`, `week-nav`+`week-btn`, `tag-bar`+`tag-chip` — all take `.active`
- Stats: `stats` > `stat-box` (`stat-high`|`stat-mid`|`stat-low`|`stat-all`) > `.num`+`.lbl`
- Article card: `card` > `card-header` (`card-meta` badges + `card-title`) > `card-body` (`section-label`, `section-text`) > optional `article-tags` (`article-tag`) > `card-footer` (`reason-text`, `line-share`, `read-more`, `dismiss-btn`)
- Hot-topic analysis card: `card ht-card` > `ht-title`, `ht-focus`>`li`>`ht-focus-link`, `ht-axes` > `ht-axis` (`ht-axis-title`, `ht-kv`+`ht-kv-label`+`ht-kv-value`, `ht-text`, `ht-metric`+`ht-metric-label`+`ht-metric-value`, `ht-check`, `ht-muted`)
- Dense list: `tr-group` > `tr-group-head` (`tr-group-caret`, `tr-group-name`, `tr-group-count`) + `tr-group-body` > `card traffic-row` > `tr-main` (`tr-src`, `tr-title`, `tr-time`, `dismiss-btn tr-dismiss`) + `tr-detail` (`tr-summary`, `line-share`, `read-more`)
- States: `empty` (with `h3`+`p`), `site-footer`

## ⚠️ Non-obvious quirks

1. **Chinese class suffixes.** Card and badge importance variants use Chinese: `card-高` `card-中` `card-低`, `imp-高` `imp-中` `imp-低`. But stat boxes use English: `stat-high` `stat-mid` `stat-low`. Both are real — copy exactly.
2. **Source badges are inline-styled**, not classed: `<span class="source-badge" style="background:#4285F4">Google News</span>`. Palette in use: Google News #4285F4, PTT #FF4500, 聯合 #1A3C6E, 中時 #C0392B, 自由 #27AE60, TVBS #2980B9, ETtoday #E74C3C, 交通部 #8E44AD, fallback #555. Same for `tr-src`.
3. `section-label` and `read-more` get their color inline from the card's importance: `style="color:var(--high)"` etc.
4. LINE share button `line-share` uses brand green #06C755 — fixed, not a token.

## Idiomatic snippet (article card, 高 importance)

```html
<div class="card card-高">
  <div class="card-header">
    <div class="card-meta">
      <span class="importance-badge imp-高">🔴 高重要</span>
      <span class="source-badge" style="background:#C0392B">中時新聞網</span>
      <span class="pub-date">發布時間 2026/7/6 10:00</span>
    </div>
    <a class="card-title" href="#">1. 標題文字</a>
  </div>
  <div class="card-body">
    <p class="section-label" style="color:var(--high)">📋 摘要</p>
    <p class="section-text">摘要內文…</p>
  </div>
  <div class="article-tags"><span class="article-tag">標籤</span></div>
  <div class="card-footer">
    <span class="reason-text">💡 重要性理由</span>
    <a class="read-more" href="#" style="color:var(--high)">閱讀原文 →</a>
  </div>
</div>
```
