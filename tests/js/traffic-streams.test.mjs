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
