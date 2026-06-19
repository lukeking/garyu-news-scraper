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
let hotTopicsByWeek = {};

const $ = id => document.getElementById(id);

// HTML 跳脫：報告/摘要等欄位可能含原始 HTML（如 RSS 的 <a>），直接注入會破版。
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Strip HTML tags and decode entities from RSS summaries (Google News wraps text
// in <a> and uses &nbsp;). DOMParser yields an inert document — no script execution
// or resource loading — and tolerates truncated/half-open tags.
function stripHtml(s) {
  const doc = new DOMParser().parseFromString(String(s == null ? '' : s), 'text/html');
  return (doc.body.textContent || '').replace(/\s+/g, ' ').trim();
}

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
// 把報告的 week_start_date（週一日期）換算成 ISO 週字串，對齊文章 week_id（如 2026-W23）。
function isoWeekId(dateStr) {
  const date = new Date(dateStr + 'T00:00:00Z');
  if (isNaN(date)) return '';
  const day = (date.getUTCDay() + 6) % 7;
  date.setUTCDate(date.getUTCDate() - day + 3);   // 當週週四
  const isoYear = date.getUTCFullYear();
  const yearStart = new Date(Date.UTC(isoYear, 0, 1));
  const week = Math.ceil(((date - yearStart) / 86400000 + 1) / 7);
  return `${isoYear}-W${String(week).padStart(2, '0')}`;
}

function groupHotTopicsByWeek(reports) {
  const map = {};
  for (const r of reports) {
    const wid = isoWeekId(r.week_start_date || '');
    if (!wid) continue;
    (map[wid] = map[wid] || []).push(r);
  }
  return map;
}

// 由 topic_label 產生 URL 安全的 slug，作為卡片 id 與 deep-link 錨點。
function slugify(s) { return encodeURIComponent(String(s || '').trim().replace(/\s+/g, '-')); }

// 將 report_text 解析成三軸結構；遇未知格式回傳空陣列（由呼叫端降級）。
function parseReport(text) {
  const axes = [];
  let cur = null;
  for (const raw of (text || '').split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('### ')) {
      cur = { title: line.replace(/^###\s*/, ''), items: [] };
      axes.push(cur);
      continue;
    }
    if (!cur) { cur = { title: '', items: [] }; axes.push(cur); }
    if (line.startsWith('□')) {
      cur.items.push({ type: 'check', text: line.replace(/^□\s*/, '') });
    } else {
      const i = line.indexOf('：');
      if (i === -1) cur.items.push({ type: 'text', text: line });
      else cur.items.push({ type: 'kv', label: line.slice(0, i), value: line.slice(i + 1).trim() });
    }
  }
  return axes;
}

function renderReportBody(text) {
  const axes = parseReport(text);
  if (!axes.length) {  // 降級：非預期格式 → 純文字段落，不破版
    return (text || '').split('\n').filter(l => l.trim())
      .map(l => `<p class="section-text">${esc(l)}</p>`).join('');
  }
  return axes.map(ax => `
    <div class="ht-axis">
      ${ax.title ? `<p class="ht-axis-title">${esc(ax.title)}</p>` : ''}
      ${ax.items.map(it => {
        if (it.type === 'check') {
          const ci = it.text.indexOf('：');
          const cl = ci === -1 ? it.text : it.text.slice(0, ci);
          const cv = ci === -1 ? '' : it.text.slice(ci + 1).trim();
          const finding = /^存在/.test(cv);
          const empty = /^(資訊不足|不存在|不適用)/.test(cv);
          return `<p class="ht-check${empty ? ' ht-muted' : ''}">${finding ? '⚠' : '☐'} ${esc(cl)}${cv ? '：' + esc(cv) : ''}</p>`;
        }
        if (it.type === 'text') return `<p class="ht-text">${esc(it.text)}</p>`;
        const cls = /交織度/.test(it.label) ? 'ht-metric' : 'ht-kv';
        const muted = cls === 'ht-kv' && /^(資訊不足|不存在|不適用|無觸發)/.test(String(it.value).trim());
        return `<div class="${cls}"><span class="${cls}-label">${esc(it.label)}</span><span class="${cls}-value${muted ? ' ht-muted' : ''}">${esc(it.value)}</span></div>`;
      }).join('')}
    </div>`).join('');
}

function renderHotTopics(reports) {
  const container = $('hot-topics-list');
  if (!container) return;
  if (!reports || !reports.length) {
    container.innerHTML = '<p style="color:var(--text-muted);font-size:0.9rem">這一週尚無熱點話題</p>';
    return;
  }
  container.innerHTML = reports.map(r => {
    const slug = slugify(r.topic_label);
    const wid = isoWeekId(r.week_start_date);
    const pageUrl = location.origin + location.pathname + '?week=' + encodeURIComponent(wid) + '#topic-' + slug;
    const lineUrl = 'https://social-plugins.line.me/lineit/share?url=' + encodeURIComponent(pageUrl);
    return `
<div class="card ht-card" id="topic-${slug}" style="margin-bottom:1rem">
  <div class="card-header">
    <div class="card-meta">
      <span class="importance-badge imp-高">🔥 熱點</span>
      <span style="font-size:0.8rem;color:var(--text-muted)">📰 ${r.source_article_count} 篇來源 · ${r.distinct_sources} 個媒體</span>
      ${C.shareToLine ? `<a class="line-share" href="${lineUrl}" target="_blank" rel="noopener" title="分享此深度分析至 LINE">LINE</a>` : ''}
    </div>
    <div class="ht-title">${esc(r.topic_label)}</div>
  </div>
  <div class="card-body">
    ${(r.source_article_links || []).length ? `
    <p class="section-label" style="color:var(--accent2)">焦點事件</p>
    <ol class="ht-focus">
      ${(r.source_article_links).map(a => `
      <li><a href="${typeof a === 'object' ? a.link : a}" target="_blank" rel="noopener" class="ht-focus-link">${esc(typeof a === 'object' ? (a.title || a.link) : a)}</a></li>`).join('')}
    </ol>` : ''}
    <div class="ht-axes">${renderReportBody(r.report_text)}</div>
  </div>
</div>`;
  }).join('');
}

// 深度分析 deep-link：若 URL 有 #topic-<slug> 則捲動定位；找不到則不動作、不報錯。
function scrollToHashTopic() {
  if (!location.hash.startsWith('#topic-')) return;
  const el = document.getElementById(location.hash.slice(1));
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  syncThemeIcon();

  if (C.contentType === 'traffic') {
    const htRes = await fetch(`${API_BASE}/hot-topics`).catch(() => null);
    if (htRes && htRes.ok) {
      const htData = await htRes.json();
      hotTopicsByWeek = groupHotTopicsByWeek(htData.reports || []);
    }
  }

  const res = await fetch(`${API_BASE}/weeks?content_type=${C.contentType}`).catch(() => null);
  if (!res || !res.ok) {
    $('article-list').innerHTML = '<div class="empty"><h3>尚無資料</h3><p>請等待第一次週報產生</p></div>';
    return;
  }
  allWeeks = await res.json();
  renderWeekNav();
  if (allWeeks.length) {
    const wanted = new URLSearchParams(location.search).get('week');
    const target = (wanted && allWeeks.some(w => w.week_id === wanted)) ? wanted : allWeeks[0].week_id;  // 失效則回退最新週
    await loadWeek(target);
    scrollToHashTopic();
  }

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
  if (C.contentType === 'traffic') renderHotTopics(hotTopicsByWeek[weekId] || []);
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

// 交通新聞密集列：來源色標＋標題＋相對時間；點標題展開來源摘要（FR-009/015）
function trafficRow(a, idx) {
  const src = a.source || '';
  const when = a.published || a.created_at || '';
  const summary = stripHtml((a.analysis && a.analysis.summary) || '');
  const lineUrl = `https://social-plugins.line.me/lineit/share?url=${encodeURIComponent(a.link)}`;
  return `
<div class="card traffic-row" data-url="${a.link}">
  <div class="tr-main">
    <span class="tr-src" style="background:${C.srcColor(src)}">${esc(C.srcLabel(src))}</span>
    <button class="tr-title" onclick="toggleRow(this)">${idx}. ${esc(a.title)}</button>
    <span class="tr-time">${when ? relativeTime(when) : ''}</span>
    <button class="dismiss-btn tr-dismiss" data-url="${a.link}" onclick="dismissArticle(this)" title="標記過時">×</button>
  </div>
  <div class="tr-detail" hidden>
    ${summary ? `<p class="tr-summary">${esc(summary)}</p>` : ''}
    ${C.shareToLine ? `<a class="line-share" href="${lineUrl}" target="_blank" rel="noopener" title="分享至 LINE">LINE</a> ` : ''}
    <a class="read-more" href="${a.link}" target="_blank" rel="noopener">閱讀原文 →</a>
  </div>
</div>`;
}

function toggleRow(btn) {
  const detail = btn.closest('.traffic-row')?.querySelector('.tr-detail');
  if (detail) detail.hidden = !detail.hidden;
}

function renderCards(articles) {
  if (!articles.length) {
    $('article-list').innerHTML = `<div class="empty">${C.emptyHtml}</div>`;
    return;
  }
  if (C.contentType === 'traffic') {
    const ts = a => { const d = new Date(a.published || a.created_at || 0); return isNaN(d) ? 0 : d.getTime(); };
    const sorted = [...articles].sort((a, b) => ts(b) - ts(a));   // 時間序，最新在上
    $('article-list').innerHTML = sorted.map((a, i) => trafficRow(a, i + 1)).join('');
  } else {
    $('article-list').innerHTML = articles.map((a, i) => articleCard(a, i + 1)).join('');
  }
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
