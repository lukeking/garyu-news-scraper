# Contract: Frontend Tag Cloud (FFXIV Term Pool)

**Feature**: Gemini-Powered Self-Evolving Knowledge Base  
**Files**: `pages/ffxiv/index.html` (modified), `pages/shared/app.js` (modified)

---

## HTML Contract — `pages/ffxiv/index.html`

### Placement

Insert `<div id="unknown-term-pool">` between `<div class="week-nav" id="week-nav">` and `<div class="tag-bar" id="tag-bar">`:

```html
<div class="week-nav" id="week-nav"></div>

<div id="unknown-term-pool" class="term-pool" style="display:none">
  <div class="term-pool-header">
    ⚔ 未知術語池 <span class="term-pool-sub">Unknown Term Pool</span>
  </div>
  <div class="term-pool-tags" id="term-pool-tags"></div>
</div>

<div class="tag-bar" id="tag-bar"></div>
```

### CSS (added to `pages/ffxiv/index.html` `<style>` block)

```css
.term-pool {
  position: relative;
  border: 2px double var(--accent);
  border-radius: var(--radius);
  padding: 12px 16px 12px;
  margin-bottom: 16px;
  background: var(--tag-bg);
  overflow: hidden;
}
.term-pool-header {
  font-size: 0.8rem;
  color: var(--accent2);
  font-weight: 600;
  margin-bottom: 8px;
  user-select: none;
}
.term-pool-sub {
  font-weight: 400;
  color: var(--text-muted);
  margin-left: 6px;
  font-size: 0.75rem;
}
.term-pool-tags {
  position: relative;
  height: 100px;
}
.term-tag {
  position: absolute;
  color: var(--tag-text);
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  white-space: nowrap;
  cursor: default;
  user-select: none;
}
```

---

## JavaScript Contract — `pages/shared/app.js`

### New function: `renderTermPool(articles)`

**Called from**: `renderAll()` — add `renderTermPool(currentArticles);` after `renderCards()`.

**Guard**: Only runs when `C.contentType === 'ffxiv'`. Traffic page is unaffected.

```javascript
function renderTermPool(articles) {
  if (C.contentType !== 'ffxiv') return;
  const pool = document.getElementById('unknown-term-pool');
  const tagsEl = document.getElementById('term-pool-tags');
  if (!pool || !tagsEl) return;

  const termRe = /\[\[([^\]]+)\]\]/g;
  const termSet = new Set();
  articles.forEach(a => {
    const text = JSON.stringify(a.analysis || {});
    let m;
    while ((m = termRe.exec(text)) !== null) {
      termSet.add(m[1].trim());
    }
  });

  if (!termSet.size) {
    pool.style.display = 'none';
    return;
  }

  pool.style.display = '';
  const terms = [...termSet];
  tagsEl.innerHTML = terms.map(t => {
    const size = (0.85 + Math.random() * 0.7).toFixed(2);
    const left = (2 + Math.random() * 88).toFixed(1);
    const top  = (5 + Math.random() * 75).toFixed(1);
    return `<span class="term-tag" style="font-size:${size}rem;left:${left}%;top:${top}%">${t}</span>`;
  }).join('');
}
```

### `renderAll()` update

```javascript
function renderAll() {
  renderStats(currentArticles);
  renderCards(currentArticles);
  renderTermPool(currentArticles);   // add this line
}
```

---

## Behaviour Guarantees

- **Hidden when empty**: `pool.style.display = 'none'` when no `[[term]]` markers exist in displayed articles.
- **Re-renders on week/filter change**: `renderAll()` is called on every `loadWeek()` and filter update, so the pool always reflects currently displayed articles.
- **Deduplicated**: Each unique term appears exactly once regardless of how many articles contain it.
- **Traffic page unaffected**: `C.contentType !== 'ffxiv'` guard exits immediately — no DOM lookup, no rendering.
- **No new API calls**: Terms extracted client-side from `a.analysis` data already received. No new Worker API endpoint.
- **Scatter on each render**: Random `left`/`top` values are re-computed on every `renderTermPool()` call. Tags shift positions on week/filter change — this is expected and intentional.
