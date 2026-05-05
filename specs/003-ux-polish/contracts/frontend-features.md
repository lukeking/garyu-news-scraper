# Contract: Frontend Features

**Feature**: P2 (Dismiss), P3 (Theme Toggle), P4 (Date Label), P5 (FFXIV RSS Link)
**Files**: `pages/traffic/index.html`, `pages/ffxiv/index.html`

---

## P2: Dismiss Button Contract

### DOM Contract

Each article card MUST include a dismiss button as the last child of `.card-footer`:

```html
<button class="dismiss-btn" data-url="{article.link}" aria-label="標記過時">標記過時</button>
```

- `data-url` holds the canonical article URL (same as the article's `link` field)
- The button is visible on all cards by default

### Behavior Contract

**On click ("標記過時")**:
1. Read `dismissed-{site}` from localStorage (parse JSON array or default to `[]`)
2. Append `article.link` if not already present
3. Write updated array back to localStorage
4. Hide the card immediately (set `display: none` or add class `.dismissed`)
5. If all currently visible article cards in the active week are now hidden: render empty state

**On page load / week switch / filter change**:
1. Read `dismissed-{site}` from localStorage
2. For each article card in the rendered list: if its `data-url` is in the dismissed set, hide it
3. Apply AFTER rendering the full article list, BEFORE showing the list container

**localStorage key**: `dismissed-traffic` (traffic site) / `dismissed-ffxiv` (FFXIV site)
**localStorage format**: JSON array of strings — `["https://example.com/a", "https://example.com/b"]`

### Empty State Contract

When all article cards in the active week + filter state are hidden:

```html
<div id="empty-dismissed-state" class="empty-state">
  <p>本週所有文章均已標記為過時。</p>
  <button id="clear-dismissed-btn">清除過時標記</button>
</div>
```

**On "清除過時標記" click**:
1. Set `dismissed-{site}` in localStorage to `[]`
2. Re-render current article list (or show all hidden cards)
3. Hide the empty state element

### localStorage Fallback

If `localStorage` throws (private mode, quota exceeded):
- The dismiss action hides the card for the current session only (via CSS class)
- No error is shown to the user

---

## P3: Theme Toggle Contract

### DOM Contract

The site header MUST include a theme toggle button:

```html
<button id="theme-toggle" aria-label="切換主題">🌙</button>
```

- Icon: `🌙` (moon) when currently in light mode; `☀️` (sun) when in dark mode
- Position: right side of the header, always visible

### CSS Contract

CSS custom properties MUST be defined under `:root` for light mode and overridden by `[data-theme="dark"]` on `<html>`:

```css
:root {
  --bg: #F5F6FA;
  --surface: #ffffff;
  --text: #1a1a2e;
  --text-muted: #666;
  /* ... other tokens */
}

[data-theme="dark"] {
  --bg: #1a1a2e;
  --surface: #2d2d44;
  --text: #e8e8f0;
  --text-muted: #aaa;
  /* ... dark overrides */
}
```

All color values in the page MUST reference these variables (not hardcoded hex). The implementer defines the exact dark palette values.

### Behavior Contract

**On page load** (runs before first paint):
1. Read `theme` from localStorage
2. If `"dark"`: set `document.documentElement.setAttribute('data-theme', 'dark')` + show `☀️` icon
3. If `"light"`: set `data-theme="light"` + show `🌙` icon
4. If no value: check `window.matchMedia('(prefers-color-scheme: dark)').matches`
   - If true: apply dark mode (do NOT write to localStorage — first visit behavior per FR-011)
   - If false: apply light mode (do NOT write to localStorage)

**On toggle button click**:
1. Read current theme from `document.documentElement.getAttribute('data-theme')`
2. Toggle to opposite
3. Write new value (`"light"` or `"dark"`) to localStorage key `theme`
4. Update button icon

**Timing**: Theme MUST be applied before any article content renders to prevent flash of wrong theme. Achieve this by placing the theme-init script in `<head>` before CSS, or by setting the attribute synchronously before body paint.

---

## P4: Date Label Contract

### Display Contract

Every article card that shows a date MUST prefix it with "收錄時間":

```html
<span class="date-label">收錄時間 2026/01/15</span>
```

**Applies to**: All date fields rendered in article cards on both the traffic and FFXIV sites.

**When no date value**: The date element is not rendered (not shown as empty).

---

## P5: FFXIV RSS Link Contract

### DOM Contract (`pages/ffxiv/index.html` only)

The FFXIV site header MUST include an RSS link:

```html
<a href="./feed.xml" class="rss-link" rel="alternate" type="application/rss+xml" title="RSS 訂閱">
  📡 RSS 訂閱
</a>
```

- `href` is relative: `./feed.xml` (resolves to `pages/ffxiv/feed.xml`)
- Must be discoverable in the header area, not hidden

### Pipeline Contract (publisher.py)

`build_feed()` MUST accept `feed_title` and `feed_description` parameters:

```python
def build_feed(
    all_weeks_articles: list,
    week_id: str,
    docs_dir: Path,
    site_url: str,
    feed_title: str = "台灣機車交通週報",
    feed_description: str = "每週自動彙整台灣機車交通相關新聞，含 AI 摘要與深度分析",
):
```

`FFXIVCategory.publish()` MUST pass:
- `feed_title="最終幻想XIV 週報"`
- `feed_description="每週自動彙整 FFXIV 遊戲相關資訊，含 AI 摘要與重點分析"`

The `publish()` function in `publisher.py` MUST pass these through to `build_feed()`.
