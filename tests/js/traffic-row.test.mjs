/**
 * `pages/shared/app.js` 的密集列渲染 — 特徵化測試（characterization tests）。
 *
 * **為什麼現在才有**：本 repo 的 JS 層一直沒有測試 runner（`CLAUDE.local.md` 的表格寫「無」），
 * 而這件事已經被**兩份 spec 明文記下再繞過**（`008/tasks.md:10`、`011/plan.md` 的
 * Complexity Tracking）。BACKLOG #6 的觸發點寫著「第 3 次記下就不要再繞，直接開 spec」，
 * 而 BACKLOG #5（列模型改成 E 響應式）動的正是這個檔案——那會是第 3 次。
 *
 * 這一批不是 #6 的完整解（Storybook / E2E 仍未做），是它的頭期款：
 * 先讓「改動這個渲染器」這件事有紅燈可看。
 *
 * **這些測試描述的是「現在」的行為，不是「應該」的行為。** 其中
 * `test_thumbnail_is_hidden_until_expanded` 描述的正是 BACKLOG #5 要修掉的缺陷——
 * 刻意寫成測試，好讓 E 落地時那個改動是**紅的、看得見的**，而不是靜靜地變了。
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { loadApp, article } from './harness.mjs';

const app = loadApp();

test('esc 跳脫會破版的字元', () => {
  assert.equal(app.esc('<img src=x onerror="alert(1)">'),
    '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(app.esc(null), '');
});

test('stripHtml 走真正的 DOMParser，不是 regex', () => {
  // 巢狀標籤與實體字元是 regex 版本最容易出錯的地方，用它們證明 harness 真的有 DOM。
  assert.equal(app.stripHtml('<p>前<b>中</b>後</p>'), '前中後');
  assert.equal(app.stripHtml('a &amp; b'), 'a & b');
});

test('articleDisplayState：三種狀態', () => {
  assert.equal(app.articleDisplayState(article()), 'normal');
  assert.equal(app.articleDisplayState({ ...article(), noise_downgrade: true }), 'collapsed');
  // hidden 需要使用者收起該來源，走 localStorage
  app.saveHiddenSources(new Set(['自由時報']));
  assert.equal(app.articleDisplayState({ ...article(), source: '自由時報' }), 'hidden');
  app.saveHiddenSources(new Set());
});

test('★ 與左邊框：高信號突顯不依賴圖片（FR-017）', () => {
  const withStar = app.trafficRow({ ...article(), hot_topic_analyzed: true, image_url: '' }, 1, false);
  assert.match(withStar, /class="[^"]*\btr-strong\b/, '已分析的列要有 tr-strong');
  assert.match(withStar, /tr-badge[^>]*>★/, '已分析的列要有 ★');

  const plain = app.trafficRow(article(), 2, false);
  assert.doesNotMatch(plain, /\btr-strong\b/);
  assert.doesNotMatch(plain, /★/);
});

test('降級列淡化，但不因此拿到 tr-strong', () => {
  const dim = app.trafficRow({ ...article(), hot_topic_analyzed: true }, 1, true);
  assert.match(dim, /\btr-dimmed\b/);
  assert.doesNotMatch(dim, /\btr-strong\b/, 'dimmed 的列不該同時被突顯');
});

test('來源色標用真實的 srcColor / srcLabel', () => {
  const html = app.trafficRow({ ...article(), source: '中時新聞網' }, 1, false);
  assert.match(html, /background:#C0392B/);
  assert.match(html, />中時新聞網</);
  // Google News 的多個 feed 顯示成同一個標籤，但 data-source 必須是原值
  const gn = app.trafficRow({ ...article(), source: 'Google News 機車' }, 1, false);
  assert.match(gn, /data-source="Google News 機車"/);
  assert.match(gn, />Google News</);
});

test('標題回音的 summary 視為無摘要', () => {
  const echo = app.trafficRow({
    ...article(), title: '國道三號連環追撞', summary: '國道三號連環追撞 - 中時新聞網',
  }, 1, false);
  assert.doesNotMatch(echo, /tr-summary/, '只是標題複讀＋來源名，展開沒有東西可看');

  const real = app.trafficRow(article(), 1, false);
  assert.match(real, /tr-summary/);
});

test('⚠️ 現況：縮圖藏在展開後才出現的 tr-detail 裡（BACKLOG #5 要修的就是這個）', () => {
  const html = app.trafficRow({ ...article(), image_url: 'https://img.test/a.jpg' }, 1, false);

  assert.match(html, /tr-thumb/, '有圖有摘要時縮圖存在');
  const detailAt = html.indexOf('class="tr-detail" hidden');
  const thumbAt = html.indexOf('tr-thumb');
  assert.ok(detailAt >= 0, 'tr-detail 預設 hidden');
  assert.ok(thumbAt > detailAt, '縮圖在 tr-detail 之內 → 掃描視圖看不到它');

  // 掃描時看得到的那一段（tr-main）裡沒有任何圖片
  const main = html.slice(html.indexOf('class="tr-main"'), detailAt);
  assert.doesNotMatch(main, /<img/, '這一行就是 #5 的缺陷：列的掃描區完全沒有圖');
});

test('沒有摘要時不放縮圖（現況行為）', () => {
  const html = app.trafficRow({
    ...article(), title: 'A', summary: 'A - 來源', image_url: 'https://img.test/a.jpg',
  }, 1, false);
  assert.doesNotMatch(html, /tr-thumb/);
});
