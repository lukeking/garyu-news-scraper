// Shared app logic for Garyu news sites.
// Each page defines window.SITE_CONFIG before loading this file.
const C = window.SITE_CONFIG;
const API_BASE = window.__API_BASE__ || '/api';
const IMP_DOT = { '高': '🔴', '中': '🟡', '低': '🟢' };

let allWeeks = [];
let currentWeekId = '';
let currentArticles = [];
let activeImp = localStorage.getItem('garyu_filter_importance') || 'all';
let activeTag = '';
let activeQuery = '';
let searchTimer = null;

const $ = id => document.getElementById(id);

// ── Theme ─────────────────────────────────────────────────────
function toggleTheme() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const next = isDark ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch(e) {}
  $('theme-toggle').textContent = next === 'dark' ? '☀️' : '🌙';
}
function syncThemeIcon() {
  const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  const btn = $('theme-toggle');
  if (btn) btn.textContent = isDark ? '☀️' : '🌙';
}

// ── Dismiss ───────────────────────────────────────────────────
function getDismissed() {
  try { return new Set(JSON.parse(localStorage.getItem(C.dismissedKey) || '[]')); }
  catch(e) { return new Set(); }
}
function dismissArticle(btn) {
  const url = btn.dataset.url;
  const set = getDismissed();
  set.add(url);
  try { localStorage.setItem(C.dismissedKey, JSON.stringify([...set])); } catch(e) {}
  const card = btn.closest('.card');
  if (card) card.style.display = 'none';
  checkEmptyDismissed();
}
function checkEmptyDismissed() {
  const list = $('article-list');
  const cards = list.querySelectorAll('.card');
  const allHidden = cards.length > 0 && [...cards].every(c => c.style.display === 'none');
  let emptyState = document.getElementById('empty-dismissed-state');
  if (allHidden && !emptyState) {
    list.insertAdjacentHTML('beforeend',
      '<div id="empty-dismissed-state" class="empty">' +
      '<h3>本週所有文章均已標記為過時。</h3>' +
      '<button onclick="clearDismissed()" style="margin-top:12px;padding:8px 16px;cursor:pointer;' +
      'border:1px solid var(--border);border-radius:6px;background:var(--card-bg);color:var(--text);font-size:14px;">' +
      '清除過時標記</button></div>');
  } else if (!allHidden && emptyState) {
    emptyState.remove();
  }
}
function clearDismissed() {
  try { localStorage.setItem(C.dismissedKey, '[]'); } catch(e) {}
  const emptyState = document.getElementById('empty-dismissed-state');
  if (emptyState) emptyState.remove();
  document.querySelectorAll('#article-list .card').forEach(c => c.style.display = '');
}
function applyDismissed() {
  const dismissed = getDismissed();
  if (!dismissed.size) return;
  document.querySelectorAll('#article-list .card[data-url]').forEach(card => {
    if (dismissed.has(card.dataset.url)) card.style.display = 'none';
  });
  checkEmptyDismissed();
}

// ── Hot Topics (traffic only) ─────────────────────────────────
function renderHotTopics(reports) {
  const container = $('hot-topics-list');
  if (!container) return;
  if (!reports || !reports.length) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.9rem">本週熱點話題尚未產生</p>';
    return;
  }
  container.innerHTML = reports.map(r => `
<div class="card" style="margin-bottom:1rem">
  <div class="card-header">
    <div class="card-meta">
      <span class="importance-badge imp-高">🔥 熱點</span>
      <span class="source-badge" style="background:var(--accent)">${r.topic_label}</span>
      <span style="font-size:0.8rem;color:var(--text-muted)">📰 ${r.source_article_count} 篇來源 · ${r.distinct_sources} 個媒體</span>
    </div>
    <div style="font-weight:600;margin-top:0.4rem;color:var(--text)">${r.topic_label}</div>
  </div>
  <div class="card-body">
    ${r.report_text.split('\n').filter(l => l.trim()).map(line => {
      if (line.startsWith('### ')) {
        return `<p class="section-label" style="color:var(--accent);margin-top:0.75rem;font-size:0.9rem;border-left:3px solid var(--accent2);padding-left:0.5rem">${line.replace(/^###\s*/, '')}</p>`;
      }
      if (line.startsWith('□ ')) {
        return `<p class="section-text" style="padding-left:1rem;color:var(--text-body)">${line}</p>`;
      }
      const colon = line.indexOf('：');
      if (colon === -1) return `<p class="section-text">${line}</p>`;
      return `<p class="section-label" style="color:var(--accent2)">${line.slice(0, colon + 1)}</p>` +
             `<p class="section-text">${line.slice(colon + 1)}</p>`;
    }).join('')}
  </div>
</div>`).join('');
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  syncThemeIcon();

  if (C.contentType === 'traffic') {
    const htRes = await fetch(`${API_BASE}/hot-topics`).catch(() => null);
    if (htRes && htRes.ok) {
      const htData = await htRes.json();
      renderHotTopics(htData.reports || []);
    }
  }

  const res = await fetch(`${API_BASE}/weeks?content_type=${C.contentType}`).catch(() => null);
  if (!res || !res.ok) {
    $('article-list').innerHTML = '<div class="empty"><h3>尚無資料</h3><p>請等待第一次週報產生</p></div>';
    return;
  }
  allWeeks = await res.json();
  renderWeekNav();
  if (allWeeks.length) await loadWeek(allWeeks[0].week_id);

  const tRes = await fetch(`${API_BASE}/tags?content_type=${C.contentType}`).catch(() => null);
  if (tRes && tRes.ok) renderTagBar(await tRes.json());

  $('search-input').addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
      activeQuery = $('search-input').value.trim();
      if (currentWeekId) await loadWeek(currentWeekId);
    }, 250);
  });
}

// ── Week nav ──────────────────────────────────────────────────
function renderWeekNav() {
  $('week-nav').innerHTML = allWeeks.map(w =>
    `<button class="week-btn${w.week_id === currentWeekId ? ' active' : ''}"
      onclick="loadWeek('${w.week_id}')">${w.week_id} (${w.article_count}篇)</button>`
  ).join('');
}

async function loadWeek(weekId) {
  currentWeekId = weekId;
  const params = new URLSearchParams();
  params.set('content_type', C.contentType);
  if (activeImp !== 'all') params.set('importance', activeImp);
  if (activeTag) params.set('tag', activeTag);
  if (activeQuery) params.set('q', activeQuery);
  const res = await fetch(`${API_BASE}/weeks/${weekId}?${params.toString()}`);
  if (!res.ok) {
    $('article-list').innerHTML = '<div class="empty"><h3>載入失敗</h3><p>請稍後再試</p></div>';
    return;
  }
  const data = await res.json();
  currentArticles = data.articles || [];
  document.title = C.pageTitle(weekId);
  const latestAt = currentArticles.reduce((m, a) => a.created_at > m ? a.created_at : m, '');
  const syncLabel = latestAt ? ` · 最後更新 ${relativeTime(latestAt)}` : '';
  $('site-subtitle').textContent = C.subtitle(weekId, data.article_count, syncLabel);
  renderWeekNav();
  renderAll();
}

// ── Tag bar ───────────────────────────────────────────────────
function renderTagBar(tData) {
  const aiTags = tData.ai_tags || {};
  const userTags = tData.user_tags || [];
  const top = Object.entries(aiTags).sort((a,b) => b[1]-a[1]).slice(0,20).map(([t]) => t);
  const all = [...new Set([...userTags, ...top])];
  $('tag-bar').innerHTML = all.map(t =>
    `<button class="tag-chip${t === activeTag ? ' active' : ''}" onclick="filterTag('${t}')">${t}</button>`
  ).join('');
}
function filterTag(tag) {
  activeTag = activeTag === tag ? '' : tag;
  document.querySelectorAll('.tag-chip').forEach(c => {
    c.classList.toggle('active', c.textContent === activeTag);
  });
  loadWeek(currentWeekId);
}

// ── Importance filter ─────────────────────────────────────────
document.querySelectorAll('.btn-filter').forEach(btn => {
  if (btn.dataset.imp === activeImp) {
    document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }
  btn.addEventListener('click', () => {
    activeImp = btn.dataset.imp;
    localStorage.setItem('garyu_filter_importance', activeImp);
    document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadWeek(currentWeekId);
  });
});

// ── Relative time ─────────────────────────────────────────────
function relativeTime(isoStr) {
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  const diff = (new Date(isoStr) - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 3600)  return rtf.format(Math.round(diff / 60), 'minute');
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), 'hour');
  return rtf.format(Math.round(diff / 86400), 'day');
}

// ── Render ────────────────────────────────────────────────────
function renderAll() {
  renderStats(currentArticles);
  renderCards(currentArticles);
  renderTermPool(currentArticles);
}

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

function renderStats(articles) {
  if (C.contentType === 'traffic') {
    $('stats').innerHTML = `<div class="stat-box stat-all"><div class="num">${articles.length}</div><div class="lbl">${C.statAllLabel} 本頁顯示</div></div>`;
    return;
  }
  const cnt = imp => articles.filter(a => (a.analysis?.importance || '中') === imp).length;
  const show = imp => activeImp === 'all' || cnt(imp) > 0;
  $('stats').innerHTML = [
    show('高') ? `<div class="stat-box stat-high"><div class="num">${cnt('高')}</div><div class="lbl">🔴 高重要性</div></div>` : '',
    show('中') ? `<div class="stat-box stat-mid"><div class="num">${cnt('中')}</div><div class="lbl">🟡 中重要性</div></div>` : '',
    show('低') ? `<div class="stat-box stat-low"><div class="num">${cnt('低')}</div><div class="lbl">🟢 低重要性</div></div>` : '',
    `<div class="stat-box stat-all"><div class="num">${articles.length}</div><div class="lbl">${C.statAllLabel} 本頁顯示</div></div>`,
  ].join('');
}

function renderCards(articles) {
  if (!articles.length) {
    $('article-list').innerHTML = `<div class="empty">${C.emptyHtml}</div>`;
    return;
  }
  $('article-list').innerHTML = articles.map((a, i) => articleCard(a, i + 1)).join('');
  applyDismissed();
}

function articleCard(a, idx) {
  const an = a.analysis || {};
  const imp = an.importance || '中';
  const tags = an.tags || [];
  const color = imp === '高' ? 'var(--high)' : imp === '中' ? 'var(--mid)' : 'var(--low)';
  const src = a.source || '';
  const lang = C.sourceLang && C.sourceLang[src];
  const tagHtml = tags.map(t =>
    `<span class="article-tag" onclick="filterTag('${t}')">${t}</span>`
  ).join('');
  const lineUrl = `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(a.link)}`;
  return `
<div class="card card-${imp}" data-url="${a.link}">
  <div class="card-header">
    <div class="card-meta">
      ${C.contentType !== 'traffic' ? `<span class="importance-badge imp-${imp}">${IMP_DOT[imp] || ''} ${imp}重要</span>` : ''}
      <span class="source-badge" style="background:${C.srcColor(src)}">${C.srcLabel(src)}</span>
      ${lang ? `<span class="lang-badge">${lang}</span>` : ''}
      ${an.location && an.location !== '不明' ? `<span class="location-badge">📍 ${an.location}</span>` : ''}
      ${a.published ? `<span class="pub-date">發布時間 ${new Date(a.published).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })}</span>` : ''}
    </div>
    <a class="card-title" href="${a.link}" target="_blank" rel="noopener">${idx}. ${a.title}</a>
  </div>
  <div class="card-body">
    ${an.summary ? `<p class="section-label" style="color:${color}">📋 摘要</p>
    <p class="section-text">${an.summary}</p>` : ''}
    ${an.analysis ? `<p class="section-label" style="color:${color}">🔍 深度分析</p>
    <p class="section-text">${an.analysis}</p>` : ''}
  </div>
  ${tags.length ? `<div class="article-tags">${tagHtml}</div>` : ''}
  <div class="card-footer">
    ${C.contentType !== 'traffic' ? `<span class="reason-text">💡 ${an.importance_reason || ''}</span>` : ''}
    <div style="display:flex;gap:8px;align-items:center;">
      ${C.shareToLine ? `<a class="line-share" href="${lineUrl}" target="_blank" rel="noopener" title="分享至 LINE">LINE</a>` : ''}
      <a class="read-more" href="${a.link}" target="_blank" rel="noopener" style="color:${color}">閱讀原文 →</a>
      <button class="dismiss-btn" data-url="${a.link}" onclick="dismissArticle(this)">標記過時</button>
    </div>
  </div>
</div>`;
}

init();
