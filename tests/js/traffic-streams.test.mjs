// spec 017 US1：交通頁拆成熱點與新文章兩條流。DOM 測試載入真正出貨的 index.html body，
// 測的是出貨的結構；按鈕的 onclick 用 window.eval 執行出貨的那串字（jsdom 的 outside-only 不跑 inline handler）。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadApp, article, TRAFFIC_CONFIG, FFXIV_CONFIG } from './harness.mjs';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const read = rel => fs.readFileSync(path.join(ROOT, rel), 'utf8');
function pageBody(rel) {
  const m = read(rel).match(/<body[^>]*>([\s\S]*)<\/body>/);
  assert.ok(m, `${rel} 沒有 <body>`);
  return m[1];
}
const TRAFFIC_BODY = pageBody('pages/traffic/index.html');
const FFXIV_BODY = pageBody('pages/ffxiv/index.html');
const CSS = read('pages/shared/shared.css');

const EXPORTS = ['reportBatches', 'renderReportStream', 'setStream', 'loadWeek', 'init'];

function report(week_start_date, topic_label) {
  return {
    week_start_date, topic_label,
    report_text: '### 一、事故因果解構\n交織度分布：[工程主導] 0篇 ／ [雙因交織] 8篇',
    source_article_count: 24, distinct_sources: 2,
    source_article_links: [{ link: 'https://example.test/r1', title: '北市大直橋死亡車禍', summary: '摘要' }],
    created_at: `${week_start_date}T01:00:00+00:00`,
  };
}
// API 的順序是 week_start_date desc；這裡故意打亂批次，批次內的順序要原樣保留。
const REPORTS = [
  report('2026-10-26', '道安政策 · 彙整'),
  report('2026-11-02', '機車事故 · 中時'),
  report('2026-10-26', '機車事故 · 聯合'),
  report('2026-11-02', '道安政策 · 彙整'),
];

const W45 = [article(), article({ link: 'https://example.test/a2', title: '台中機車擦撞 1 人送醫' })];
const W44 = [article({ link: 'https://example.test/a3', title: '國道五號回堵' })];

function respond(body, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 500, json: async () => body });
}
/** 依 pathname 回應的假 Worker；`hotTopics` 可換成失敗的回應。calls 記下每個請求的網址。 */
function stubApi({ hotTopics = () => respond({ reports: REPORTS }), weeks, weekBody } = {}) {
  const calls = [];
  const fetch = url => {
    calls.push(url);
    const p = new URL(url, 'https://garyu.test').pathname;
    if (p === '/api/hot-topics') return hotTopics();
    if (p === '/api/weeks') return respond(weeks || [{ week_id: '2026-W45', article_count: 2 }, { week_id: '2026-W44', article_count: 1 }]);
    if (p === '/api/tags') return respond({ ai_tags: {}, user_tags: [] });
    const m = p.match(/^\/api\/weeks\/(.+)$/);
    if (m) {
      const articles = weekBody ? weekBody(m[1]) : (m[1] === '2026-W44' ? W44 : W45);
      return respond({ week_id: m[1], article_count: articles.length, articles });
    }
    return respond({}, false);
  };
  return { fetch, calls };
}

const texts = nodes => Array.from(nodes, n => n.textContent.trim());

test('reportBatches：依 week_start_date 分組、新的在前，標籤是「11-02 · 2 份」', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: EXPORTS });
  const batches = app.reportBatches(REPORTS);
  assert.deepEqual(Array.from(batches, b => b.date), ['2026-11-02', '2026-10-26']);
  assert.deepEqual(Array.from(batches, b => b.label), ['11-02 · 2 份', '10-26 · 2 份']);
  assert.deepEqual(Array.from(batches[0].reports, r => r.topic_label), ['機車事故 · 中時', '道安政策 · 彙整']);
  assert.deepEqual(Array.from(batches[1].reports, r => r.topic_label), ['道安政策 · 彙整', '機車事故 · 聯合']);
});

test('reportBatches：沒有或不是日期的 week_start_date 不成批', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: EXPORTS });
  const batches = app.reportBatches([...REPORTS, report('', '空'), report(null, '沒有'), report('2026-11', '半個')]);
  assert.deepEqual(Array.from(batches, b => b.date), ['2026-11-02', '2026-10-26']);
});

test('載入時熱點那一條是目前那一條（HTML 的預設，JS 還沒跑也一樣）', () => {
  const doc = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, exports: EXPORTS }).window.document;
  assert.ok(doc.getElementById('stream-reports')?.classList.contains('active'), '#stream-reports 要有 active');
  assert.ok(!doc.getElementById('stream-articles')?.classList.contains('active'), '#stream-articles 不該有 active');
  assert.equal(doc.getElementById('tab-reports')?.getAttribute('aria-selected'), 'true');
  assert.equal(doc.getElementById('tab-articles')?.getAttribute('aria-selected'), 'false');
});

test('renderReportStream：畫出那一批，卡片寫所屬週報「11-02 週報」；切到另一批只換熱點那一條', () => {
  const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, exports: EXPORTS });
  const doc = app.window.document;
  const articlesBefore = doc.getElementById('stream-articles')?.innerHTML;
  assert.ok(articlesBefore !== undefined, '頁面上沒有 #stream-articles');

  app.renderReportStream(app.reportBatches(REPORTS), '2026-11-02');
  const cards = doc.querySelectorAll('#stream-reports .ht-card');
  assert.deepEqual(texts(doc.querySelectorAll('#stream-reports .ht-title')), ['機車事故 · 中時', '道安政策 · 彙整']);
  for (const card of cards) {
    const meta = card.querySelector('.card-meta');
    assert.equal(meta.children[0].textContent.trim(), '🔥 熱點');
    assert.equal(meta.children[1].className, 'ht-batch', '所屬週報緊接在「🔥 熱點」後面');
    assert.equal(meta.children[1].textContent, '11-02 週報');
    assert.doesNotMatch(meta.textContent, /產生/);
  }
  const navButtons = () => doc.querySelectorAll('#stream-reports #batch-nav button');
  assert.deepEqual(texts(navButtons()), ['11-02 · 2 份', '10-26 · 2 份']);
  assert.deepEqual(texts(doc.querySelectorAll('#batch-nav .active')), ['11-02 · 2 份']);

  app.window.eval(navButtons()[1].getAttribute('onclick'));
  assert.deepEqual(texts(doc.querySelectorAll('#stream-reports .ht-title')), ['道安政策 · 彙整', '機車事故 · 聯合']);
  assert.deepEqual(texts(doc.querySelectorAll('#stream-reports .ht-batch')), ['10-26 週報', '10-26 週報']);
  assert.deepEqual(texts(doc.querySelectorAll('#batch-nav .active')), ['10-26 · 2 份']);
  assert.equal(doc.getElementById('stream-articles').innerHTML, articlesBefore, '切批次不該動到新文章那一條');
});

test('renderReportStream：沒給或對不到批次時畫最新一批；沒有報告時寫「尚無熱點報告」', () => {
  const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, exports: EXPORTS });
  const doc = app.window.document;
  const batches = app.reportBatches(REPORTS);
  for (const date of [undefined, '1999-01-01']) {
    app.renderReportStream(batches, date);
    assert.deepEqual(texts(doc.querySelectorAll('#stream-reports .ht-batch')), ['11-02 週報', '11-02 週報'], `date=${date}`);
    assert.deepEqual(texts(doc.querySelectorAll('#batch-nav .active')), ['11-02 · 2 份'], `date=${date}`);
  }
  app.renderReportStream(app.reportBatches([]), undefined);
  assert.equal(doc.querySelectorAll('#stream-reports .ht-card, #batch-nav button').length, 0);
  assert.match(doc.getElementById('stream-reports').textContent, /尚無熱點報告/);
});

test('setStream：目前那一條拿到 active，切換鈕的 aria-selected 跟著換', () => {
  const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, exports: EXPORTS });
  const doc = app.window.document;
  const state = () => ({
    reports: doc.getElementById('stream-reports')?.classList.contains('active'),
    articles: doc.getElementById('stream-articles')?.classList.contains('active'),
    tabReports: doc.getElementById('tab-reports')?.getAttribute('aria-selected'),
    tabArticles: doc.getElementById('tab-articles')?.getAttribute('aria-selected'),
  });
  app.setStream('articles');
  assert.deepEqual(state(), { reports: false, articles: true, tabReports: 'false', tabArticles: 'true' });
  app.window.eval(doc.getElementById('tab-reports').getAttribute('onclick'));
  assert.deepEqual(state(), { reports: true, articles: false, tabReports: 'true', tabArticles: 'false' });
  app.window.eval(doc.getElementById('tab-articles').getAttribute('onclick'));
  assert.deepEqual(state(), { reports: false, articles: true, tabReports: 'false', tabArticles: 'true' });
});

test('init：熱點那一條預設最新一批；loadWeek 之後新文章那一條沒有任何報告卡片，熱點那一條不動', async () => {
  const { fetch } = stubApi();
  const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, fetch, exports: EXPORTS });
  const doc = app.window.document;
  await app.init();
  assert.deepEqual(texts(doc.querySelectorAll('#stream-reports .ht-batch')), ['11-02 週報', '11-02 週報']);
  assert.deepEqual(texts(doc.querySelectorAll('#batch-nav .active')), ['11-02 · 2 份']);
  assert.equal(doc.querySelectorAll('#stream-articles .traffic-row').length, 2);
  assert.equal(doc.querySelectorAll('#stream-articles .ht-card').length, 0, 'W45 底下不該有報告');

  const reportsBefore = doc.getElementById('stream-reports').innerHTML;
  await app.loadWeek('2026-W44');
  assert.deepEqual(texts(doc.querySelectorAll('#stream-articles .tr-title')), ['1. 國道五號回堵']);
  assert.equal(doc.querySelectorAll('#stream-articles .ht-card').length, 0, 'W44 底下不該有報告');
  assert.equal(doc.getElementById('stream-reports').innerHTML, reportsBefore, '切週次不該動到熱點那一條');
});

const FAILURES = [
  ['HTTP 500', () => respond({}, false)],
  ['網路錯誤', () => Promise.reject(new Error('offline'))],
  ['回應不是 JSON', () => Promise.resolve({ ok: true, status: 200, json: () => Promise.reject(new SyntaxError('bad json')) })],
];
for (const [name, hotTopics] of FAILURES) {
  test(`init：報告清單載入失敗（${name}）時熱點那一條顯示失敗字樣，新文章那一條照常`, async () => {
    const { fetch } = stubApi({ hotTopics });
    const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, fetch, exports: EXPORTS });
    const doc = app.window.document;
    await app.init();
    assert.match(doc.getElementById('stream-reports')?.textContent || '', /熱點報告載入失敗，請稍後再試/);
    assert.equal(doc.querySelectorAll('#stream-reports .ht-card').length, 0);
    assert.equal(doc.querySelectorAll('#stream-articles .traffic-row').length, 2);
    assert.equal(doc.querySelector('#stream-articles #stats .num')?.textContent, '2');
    assert.doesNotMatch(doc.getElementById('stream-articles').textContent, /載入失敗/);
  });
}

test('init：報告清單的回應沒有 reports 欄位時熱點那一條寫「尚無熱點報告」，新文章那一條照常', async () => {
  const { fetch } = stubApi({ hotTopics: () => respond({}) });
  const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, fetch, exports: EXPORTS });
  const doc = app.window.document;
  await app.init();
  assert.match(doc.getElementById('stream-reports').textContent, /尚無熱點報告/);
  assert.equal(doc.querySelectorAll('#stream-articles .traffic-row').length, 2);
});

test('FFXIV：同一份 app.js 的 init 照舊跑完，沒有切換鈕、齒輪、熱點那一條，也不抓報告清單', async () => {
  const ffxivArticle = {
    title: '7.4 パッチノート', link: 'https://example.test/f1', source: 'Lodestone',
    published: new Date().toISOString(), analysis: { importance: '高', summary: '新副本', tags: ['patch'] },
  };
  const { fetch, calls } = stubApi({ weeks: [{ week_id: '2026-W45', article_count: 1 }], weekBody: () => [ffxivArticle] });
  const app = loadApp(FFXIV_CONFIG, { html: FFXIV_BODY, fetch, exports: ['init'] });
  const doc = app.window.document;
  await app.init();
  assert.equal(doc.querySelector('.stream-switch, [role="tab"], #stream-settings-btn, #stream-reports'), null);
  assert.ok(!calls.some(u => u.includes('/hot-topics')), `FFXIV 不該抓報告清單：${calls.join(', ')}`);
  assert.equal(doc.querySelectorAll('#article-list .card').length, 1);
  assert.match(doc.getElementById('site-subtitle').textContent, /共 1 則 FFXIV 資訊/);
});

/** 取出 `@media (min-width: 1024px) { ... }` 的內容（大括號配對）。 */
function splitBlock() {
  const at = CSS.indexOf('@media (min-width: 1024px)');
  if (at < 0) return null;
  for (let i = CSS.indexOf('{', at), j = i, depth = 0; j < CSS.length; j++) {
    if (CSS[j] === '{') depth++;
    else if (CSS[j] === '}' && --depth === 0) return CSS.slice(i + 1, j);
  }
  return null;
}

test('shared.css：並排斷點是簽核的 1024 px；窄螢幕只顯示 .stream.active；批次導覽一列不折行', () => {
  assert.ok(CSS.includes('@media (min-width: 1024px)'), '並排斷點要是 2026-11-04 簽核的 1024 px');
  const block = splitBlock();
  assert.ok(block, '@media (min-width: 1024px) 區塊不見了');
  assert.match(block, /\.stream-switch\s*\{\s*display:\s*none/, '並排時切換鈕隱藏');
  assert.match(CSS, /\.stream\s*\{\s*display:\s*none/, '窄螢幕預設不顯示任何一條');
  assert.match(CSS, /\.stream\.active\s*\{\s*display:\s*block/, 'setStream 切的 class 是 active');
  assert.match(CSS, /#batch-nav\s*\{[^}]*flex-wrap:\s*nowrap[^}]*overflow-x:\s*auto/, '批次導覽一列、左右捲動');
});

// ── US2：整週載入（FR-016）與「有新的」標記（FR-004） ──────────────────────────
const BADGE_EXPORTS = [...EXPORTS, 'countNewSince', 'weeksToScan', 'newArticleCount', 'badgeText'];

/** n 篇文章，連結各不相同；over(i) 改第 i 篇的欄位。 */
function articles(n, over = () => ({})) {
  return Array.from({ length: n }, (_, i) => article({ link: `https://example.test/p${i}`, title: `文章 ${i}`, ...over(i) }));
}
/** 照 Worker 分頁的假 API：每頁最多 100 篇、article_count 是整週篇數。fail(url) 回傳 Promise 時用它取代回應。 */
function pagedApi(weekData, { fail = () => null, hotTopics = () => respond({ reports: REPORTS }) } = {}) {
  const calls = [];
  const fetch = url => {
    calls.push(url);
    const u = new URL(url, 'https://garyu.test');
    const failed = fail(u);
    if (failed) return failed;
    if (u.pathname === '/api/hot-topics') return hotTopics();
    if (u.pathname === '/api/weeks') {
      return respond(Object.keys(weekData).sort().reverse().map(id => ({ week_id: id, article_count: weekData[id].length })));
    }
    if (u.pathname === '/api/tags') return respond({ ai_tags: {}, user_tags: [] });
    const m = u.pathname.match(/^\/api\/weeks\/(.+)$/);
    if (m && weekData[m[1]]) {
      const all = weekData[m[1]];
      const limit = Math.min(Number(u.searchParams.get('limit') || 100), 100);
      const offset = Number(u.searchParams.get('offset') || 0);
      return respond({ week_id: m[1], article_count: all.length, articles: all.slice(offset, offset + limit) });
    }
    return respond({}, false);
  };
  return { fetch, calls };
}
const weekCalls = (calls, id) => calls.map(u => new URL(u, 'https://garyu.test')).filter(u => u.pathname === `/api/weeks/${id}`);
const offsets = (calls, id) => weekCalls(calls, id).map(u => u.searchParams.get('offset'));
const HIDDEN = { 'hidden-sources-traffic': JSON.stringify(['PTT/biker']) };

test('loadWeek：article_count 135 時抓 offset=0 與 offset=100 兩頁、帶同樣的篩選參數，畫出整週、統計扣掉收起的來源', async () => {
  const week = articles(135, i => (i >= 130 ? { source: 'PTT/biker' } : {}));
  const { fetch, calls } = pagedApi({ '2026-W45': week });
  const app = loadApp(TRAFFIC_CONFIG, {
    html: TRAFFIC_BODY, fetch, exports: BADGE_EXPORTS, storage: { ...HIDDEN, garyu_filter_importance: '高' },
  });
  const doc = app.window.document;
  await app.loadWeek('2026-W45');
  assert.deepEqual(offsets(calls, '2026-W45'), ['0', '100']);
  for (const u of weekCalls(calls, '2026-W45')) {
    const p = new URLSearchParams(u.search);
    p.delete('offset');
    assert.deepEqual(Object.fromEntries(p), { content_type: 'traffic', importance: '高', limit: '100' });
  }
  assert.equal(doc.querySelectorAll('#article-list .traffic-row').length, 130);
  assert.equal(doc.querySelector('#stats .num')?.textContent, '130');
  assert.match(doc.getElementById('site-subtitle').textContent, /共 135 則/);
  const titles = texts(doc.querySelectorAll('#article-list .tr-title'));
  assert.ok(titles.some(t => t.endsWith('文章 129')), '第二頁的文章要畫出來');
});

for (const [total, expected] of [[81, ['0']], [100, ['0']], [101, ['0', '100']], [200, ['0', '100']]]) {
  test(`loadWeek：article_count 是 ${total} 時抓 ${expected.length} 頁（offset ${expected.join('、')}）`, async () => {
    const { fetch, calls } = pagedApi({ '2026-W45': articles(total) });
    const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, fetch, exports: BADGE_EXPORTS });
    await app.loadWeek('2026-W45');
    assert.deepEqual(offsets(calls, '2026-W45'), expected);
    assert.equal(app.window.document.querySelectorAll('#article-list .traffic-row').length, total);
  });
}

for (const [name, failure] of [['HTTP 500', () => respond({}, false)], ['網路錯誤', () => Promise.reject(new Error('offline'))]]) {
  test(`loadWeek：第二頁失敗（${name}）時顯示「載入失敗」，不畫出只有半週的列表`, async () => {
    const { fetch } = pagedApi(
      { '2026-W45': articles(135), '2026-W44': articles(3) },
      { fail: u => (u.pathname === '/api/weeks/2026-W45' && u.searchParams.get('offset') === '100' ? failure() : null) },
    );
    const app = loadApp(TRAFFIC_CONFIG, { html: TRAFFIC_BODY, fetch, exports: BADGE_EXPORTS });
    const doc = app.window.document;
    await app.loadWeek('2026-W44');
    assert.equal(doc.querySelectorAll('#article-list .traffic-row').length, 3);
    await app.loadWeek('2026-W45');
    assert.match(doc.getElementById('article-list').textContent, /載入失敗/);
    assert.equal(doc.querySelectorAll('#article-list .traffic-row').length, 0);
  });
}

test('countNewSince：只算 created_at 嚴格晚於基準的；等於不算、壞日期不算', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: BADGE_EXPORTS });
  const since = '2026-11-02T00:00:00.000Z';
  const items = [
    { created_at: '2026-11-02T08:00:00+08:00' },        // 同一刻、不同寫法
    { created_at: '2026-11-02T00:00:00.001Z' },
    { created_at: '2026-11-03T05:00:00.123456+00:00' },
    { created_at: '2026-11-01T23:59:59.999Z' },
    { created_at: 'not-a-date' },
    {},
  ];
  assert.equal(app.countNewSince(items, since), 2);
  assert.equal(app.countNewSince([], since), 0);
});

const W45_TO_W36 = ['2026-W45', '2026-W44', '2026-W43', '2026-W42', '2026-W41', '2026-W40', '2026-W39', '2026-W38', '2026-W37', '2026-W36']
  .map(week_id => ({ week_id, article_count: 1 }));
const scan = (app, weeks, since) => {
  const r = app.weeksToScan(weeks, since, 8);
  return { weekIds: Array.from(r.weekIds), capped: r.capped };
};

test('weeksToScan：週次用台灣時間切（2026-11-02 00:30 +08:00 是 W45，UTC 會落在 W44）', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: BADGE_EXPORTS });
  assert.deepEqual(scan(app, W45_TO_W36, '2026-11-02T00:30:00+08:00'), { weekIds: ['2026-W45'], capped: false });
  assert.deepEqual(scan(app, W45_TO_W36, '2026-11-01T23:30:00+08:00'), { weekIds: ['2026-W45', '2026-W44'], capped: false });
});

test('weeksToScan：最多 8 週；基準在第 8 週時不觸頂，早於第 8 週時 capped', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: BADGE_EXPORTS });
  const eight = ['2026-W45', '2026-W44', '2026-W43', '2026-W42', '2026-W41', '2026-W40', '2026-W39', '2026-W38'];
  assert.deepEqual(scan(app, W45_TO_W36, '2026-09-15T12:00:00+08:00'), { weekIds: eight, capped: false });   // W38
  assert.deepEqual(scan(app, W45_TO_W36, '2026-09-08T12:00:00+08:00'), { weekIds: eight, capped: true });    // W37
});

test('weeksToScan：基準早於清單最舊的週（清單會被截斷）也算 capped；壞基準不掃', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: BADGE_EXPORTS });
  const three = W45_TO_W36.slice(0, 3);
  const ids = ['2026-W45', '2026-W44', '2026-W43'];
  assert.deepEqual(scan(app, three, '2026-10-20T12:00:00+08:00'), { weekIds: ids, capped: false });   // W43
  assert.deepEqual(scan(app, three, '2026-10-13T12:00:00+08:00'), { weekIds: ids, capped: true });    // W42
  assert.deepEqual(scan(app, three, 'garbage'), { weekIds: [], capped: false });
});

/** W45 81 篇（23 篇在基準之後）、W44 135 篇（30 篇新的都在第二頁）；收起的來源各有幾篇。 */
const SINCE = '2026-10-28T00:00:00.000Z';
const COUNT_WEEKS = {
  '2026-W45': articles(81, i => ({ created_at: i < 23 ? '2026-11-03T05:00:00Z' : '2026-10-27T05:00:00Z', source: i < 4 ? 'PTT/biker' : '聯合新聞網' })),
  '2026-W44': articles(135, i => ({ created_at: i >= 105 ? '2026-10-29T05:00:00Z' : '2026-10-27T05:00:00Z', source: i >= 133 ? 'PTT/biker' : '自由時報' })),
};

test('newArticleCount：逐週逐頁（每頁 100）數出基準之後的篇數，不帶篩選、收起的來源不算', async () => {
  const { fetch, calls } = pagedApi(COUNT_WEEKS);
  const app = loadApp(TRAFFIC_CONFIG, { fetch, exports: BADGE_EXPORTS, storage: { ...HIDDEN, garyu_filter_importance: '高' } });
  assert.equal(await app.newArticleCount(['2026-W45', '2026-W44'], SINCE), (23 - 4) + (30 - 2));
  assert.deepEqual(offsets(calls, '2026-W45'), ['0']);
  assert.deepEqual(offsets(calls, '2026-W44').sort(), ['0', '100']);
  for (const u of [...weekCalls(calls, '2026-W45'), ...weekCalls(calls, '2026-W44')]) {
    const p = new URLSearchParams(u.search);
    p.delete('offset');
    assert.deepEqual(Object.fromEntries(p), { content_type: 'traffic', limit: '100' });
  }
});

for (const [name, failure] of [['HTTP 500', () => respond({}, false)], ['網路錯誤', () => Promise.reject(new Error('offline'))]]) {
  test(`newArticleCount：任何一個請求失敗（${name}）回 null`, async () => {
    const { fetch } = pagedApi(COUNT_WEEKS, {
      fail: u => (u.pathname === '/api/weeks/2026-W44' && u.searchParams.get('offset') === '100' ? failure() : null),
    });
    const app = loadApp(TRAFFIC_CONFIG, { fetch, exports: BADGE_EXPORTS });
    assert.equal(await app.newArticleCount(['2026-W45', '2026-W44'], SINCE), null);
  });
}

test('badgeText：23 → 「23」、觸頂 → 「23+」、0 → 不顯示', () => {
  const app = loadApp(TRAFFIC_CONFIG, { exports: BADGE_EXPORTS });
  assert.equal(app.badgeText(23, false), '23');
  assert.equal(app.badgeText(23, true), '23+');
  assert.equal(app.badgeText(0, false), '');
  assert.equal(app.badgeText(0, true), '');
});

const SEEN_R = 'traffic_seen_reports';
const SEEN_A = 'traffic_seen_articles';
const NARROW = `<style>${CSS}</style>`;                       // jsdom 不套 @media：真正的 CSS 就是窄螢幕
const WIDE = `<style>${CSS}${splitBlock()}</style>`;           // 把 1024 px 區塊攤開＝並排
const settle = () => new Promise(r => setTimeout(r, 0));
const BADGE_WEEKS = {
  '2026-W45': articles(81, i => ({ created_at: i < 23 ? '2026-11-03T05:00:00Z' : '2026-11-02T05:00:00Z' })),
  '2026-W44': articles(135, i => ({ created_at: '2026-10-28T05:00:00Z' })),
};
/** 兩條的 badge（切換鈕上、標頭上）；隱藏是空字串，元素不存在是 null。 */
function badges(doc) {
  const shown = sel => { const el = doc.querySelector(sel); return el ? (el.hidden ? '' : el.textContent) : null; };
  return {
    tabReports: shown('#tab-reports .stream-badge'), headReports: shown('#stream-reports .stream-head .stream-badge'),
    tabArticles: shown('#tab-articles .stream-badge'), headArticles: shown('#stream-articles .stream-head .stream-badge'),
  };
}
const NO_BADGES = { tabReports: '', headReports: '', tabArticles: '', headArticles: '' };
async function openPage({ html = NARROW, storage = {}, weeks = BADGE_WEEKS, opts = {} } = {}) {
  const { fetch, calls } = pagedApi(weeks, opts);
  const app = loadApp(TRAFFIC_CONFIG, { html: html + TRAFFIC_BODY, fetch, storage, exports: BADGE_EXPORTS });
  const t0 = Date.now();
  await app.init();
  const t1 = Date.now();
  await settle();
  return { app, doc: app.window.document, calls, t0, t1, ls: app.window.localStorage };
}
const isNow = (v, t0, t1) => /^\d{4}-\d{2}-\d{2}T/.test(v) && Date.parse(v) >= t0 && Date.parse(v) <= t1;

// 格式不對：一個像 ISO 但不是真的日期、一個 Date.parse 讀得懂但不是 ISO 時間字串。
for (const [name, storage] of [['都沒有', {}], ['格式不對', { [SEEN_R]: '2026-13-45T99:99:99Z', [SEEN_A]: '1' }]]) {
  test(`第一次打開（traffic_seen_* ${name}）：兩條都寫成現在、不顯示 badge、不數新文章`, async () => {
    const { doc, calls, t0, t1, ls } = await openPage({ storage });
    assert.ok(isNow(ls.getItem(SEEN_R), t0, t1), `${SEEN_R}=${ls.getItem(SEEN_R)}`);
    assert.equal(ls.getItem(SEEN_A), ls.getItem(SEEN_R));
    assert.deepEqual(badges(doc), NO_BADGES);
    assert.deepEqual(offsets(calls, '2026-W45'), ['0'], '只有主畫面那一次');
  });
}

test('窄螢幕：有基準時 badge 是「新 2」與「23」；顯示中的熱點改成這次打開的時間、新文章不動；切走的那一條 badge 清掉', async () => {
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-11-03T00:00:00.000Z' };
  const { app, doc, t0, t1, ls } = await openPage({ storage });
  assert.deepEqual(badges(doc), { tabReports: '新 2', headReports: '新 2', tabArticles: '23', headArticles: '23' });
  const opened = ls.getItem(SEEN_R);
  assert.ok(isNow(opened, t0, t1), `${SEEN_R}=${opened}`);
  assert.equal(ls.getItem(SEEN_A), '2026-11-03T00:00:00.000Z');

  await new Promise(r => setTimeout(r, 5));
  app.window.eval(doc.getElementById('tab-articles').getAttribute('onclick'));
  assert.equal(ls.getItem(SEEN_A), opened, '切到新文章：寫成這次打開的時間，不是切換的時間');
  assert.deepEqual(badges(doc), { tabReports: '', headReports: '', tabArticles: '23', headArticles: '23' });
  app.window.eval(doc.getElementById('tab-articles').getAttribute('onclick'));
  assert.deepEqual(badges(doc), { tabReports: '', headReports: '', tabArticles: '23', headArticles: '23' }, '點目前那一條不算切走');
  app.window.eval(doc.getElementById('tab-reports').getAttribute('onclick'));
  assert.deepEqual(badges(doc), NO_BADGES);
  assert.equal(ls.getItem(SEEN_R), opened);
});

test('寬螢幕：兩條都寫成這次打開的時間，badge 這次造訪一直顯示；基準早於清單最舊的週時是「N+」', async () => {
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-09-01T00:00:00.000Z' };
  const { app, doc, t0, t1, ls } = await openPage({ html: WIDE, storage });
  assert.ok(isNow(ls.getItem(SEEN_R), t0, t1));
  assert.equal(ls.getItem(SEEN_A), ls.getItem(SEEN_R));
  const all = { tabReports: '新 2', headReports: '新 2', tabArticles: '216+', headArticles: '216+' };
  assert.deepEqual(badges(doc), all);
  app.setStream('articles');
  app.setStream('reports');
  assert.deepEqual(badges(doc), all);
});

test('只有一條有基準：不算第一次打開——熱點照算 badge，沒有基準的新文章不顯示、窄螢幕沒顯示就不寫', async () => {
  const { doc, calls, ls } = await openPage({ storage: { [SEEN_R]: '2026-11-01T00:00:00.000Z' } });
  assert.deepEqual(badges(doc), { tabReports: '新 2', headReports: '新 2', tabArticles: '', headArticles: '' });
  assert.equal(ls.getItem(SEEN_A), null);
  assert.deepEqual(offsets(calls, '2026-W45'), ['0'], '沒有基準就不數新文章');
});

test('基準之後沒有新的：兩條都不顯示 badge（不是「新 0」「0」）', async () => {
  const storage = { [SEEN_R]: '2026-11-04T00:00:00.000Z', [SEEN_A]: '2026-11-04T00:00:00.000Z' };
  const { doc } = await openPage({ storage });
  assert.deepEqual(badges(doc), NO_BADGES);
});

test('新文章最多掃 8 週：基準在 W37、清單有 10 週時只抓 W45～W38，badge 是「N+」', async () => {
  const ids = W45_TO_W36.map(w => w.week_id);
  const weeks = Object.fromEntries(ids.map(id => [id, articles(3, () => ({ created_at: '2026-11-03T05:00:00Z' }))]));
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-09-08T12:00:00+08:00' };
  const { doc, calls } = await openPage({ storage, weeks });
  const scanned = ids.filter(id => weekCalls(calls, id).length > 0);
  assert.deepEqual(scanned, ids.slice(0, 8));
  assert.equal(badges(doc).tabArticles, '24+');
});

test('shared.css：badge 照簽核是 --high 底、白字，暗色主題深字 #1a1a2e（同 .imp-高）', () => {
  assert.match(CSS, /\.stream-badge\s*\{[^}]*background:\s*var\(--high\)[^}]*color:\s*#fff/);
  assert.match(CSS, /\[data-theme="dark"\]\s*\.stream-badge\s*\{\s*color:\s*#1a1a2e/);
  assert.match(CSS, /\.stream-badge\[hidden\]\s*\{\s*display:\s*none/);
});

test('新文章計數失敗：不顯示篇數，熱點的 badge 照常', async () => {
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-10-28T00:00:00.000Z' };
  const { doc } = await openPage({
    storage, opts: { fail: u => (u.pathname === '/api/weeks/2026-W44' && u.searchParams.get('offset') === '100' ? respond({}, false) : null) },
  });
  assert.deepEqual(badges(doc), { tabReports: '新 2', headReports: '新 2', tabArticles: '', headArticles: '' });
});

test('報告清單載入失敗：熱點不顯示 badge，traffic_seen_reports 不改（讀者沒看到報告）', async () => {
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-11-03T00:00:00.000Z' };
  const { app, doc, ls } = await openPage({ storage, opts: { hotTopics: () => respond({}, false) } });
  assert.equal(ls.getItem(SEEN_R), '2026-11-01T00:00:00.000Z');
  assert.deepEqual(badges(doc), { tabReports: '', headReports: '', tabArticles: '23', headArticles: '23' });
  app.window.eval(doc.getElementById('tab-articles').getAttribute('onclick'));
  app.window.eval(doc.getElementById('tab-reports').getAttribute('onclick'));
  assert.equal(ls.getItem(SEEN_R), '2026-11-01T00:00:00.000Z', '切回熱點也不改');
  assert.notEqual(ls.getItem(SEEN_A), '2026-11-03T00:00:00.000Z', '新文章載入成功、被顯示過，照常寫成這次打開的時間');
});

test('計數在主畫面畫完之後跑、不擋 init；讀者在數完之前已切走那一條，數完也不顯示', { timeout: 2000 }, async () => {
  let release;
  const gate = new Promise(r => { release = r; });
  const storage = { [SEEN_R]: '2026-11-01T00:00:00.000Z', [SEEN_A]: '2026-10-28T00:00:00.000Z' };
  const { fetch } = pagedApi(BADGE_WEEKS);
  const held = url => (new URL(url, 'https://garyu.test').pathname === '/api/weeks/2026-W44' ? gate.then(() => fetch(url)) : fetch(url));
  const app = loadApp(TRAFFIC_CONFIG, { html: NARROW + TRAFFIC_BODY, fetch: held, storage, exports: BADGE_EXPORTS });
  const doc = app.window.document;
  await app.init();
  assert.equal(doc.querySelectorAll('#article-list .traffic-row').length, 81, '主畫面已經畫完');
  assert.deepEqual(badges(doc), { tabReports: '新 2', headReports: '新 2', tabArticles: '', headArticles: '' });
  app.window.eval(doc.getElementById('tab-articles').getAttribute('onclick'));
  app.window.eval(doc.getElementById('tab-reports').getAttribute('onclick'));
  release();
  await settle();
  assert.deepEqual(badges(doc), NO_BADGES);
});

test('FFXIV：不讀寫 traffic_seen_*，每週只打一個請求（不到 100 篇）', async () => {
  const ffxivArticle = { title: '7.4 パッチノート', link: 'https://example.test/f1', source: 'Lodestone', published: new Date().toISOString() };
  const { fetch, calls } = pagedApi({ '2026-W45': [ffxivArticle] });
  const app = loadApp(FFXIV_CONFIG, { html: FFXIV_BODY, fetch, exports: ['init'], storage: { [SEEN_A]: '2026-10-01T00:00:00.000Z' } });
  await app.init();
  await settle();
  assert.equal(app.window.localStorage.getItem(SEEN_R), null);
  assert.equal(app.window.localStorage.getItem(SEEN_A), '2026-10-01T00:00:00.000Z');
  assert.deepEqual(offsets(calls, '2026-W45'), ['0']);
});
