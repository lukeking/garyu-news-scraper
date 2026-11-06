// spec 017 FR-002、SC-007：兩條流的並排斷點（1024px）與批次導覽的折行規則，在 Chromium 上量。
// CSS 文字的守門員在 tests/js/traffic-streams.test.mjs；這裡證明的是畫出來對不對。
import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startHarness } from './harness.mjs';

let h;
before(async () => { h = await startHarness(); });
after(() => h.close());

/** 開頁面、在頁面裡跑 measure、確認沒有沒準備的外部請求，最後關掉視窗。 */
async function measureAt(opts, measure) {
  const v = await h.open(opts);
  try {
    const m = await v.page.evaluate(measure);
    assert.deepEqual(v.blocked, [], '頁面要了 harness 沒準備的外部資源');
    return m;
  } finally {
    await v.close();
  }
}

const streams = () => {
  const box = sel => {
    const el = document.querySelector(sel);
    const r = el.getBoundingClientRect();
    return { shown: el.checkVisibility(), top: r.top, left: r.left, right: r.right };
  };
  return { switch: box('.stream-switch'), reports: box('#stream-reports'), articles: box('#stream-articles') };
};

test('1024px：視窗 1023 px 時切換鈕顯示、只看得到目前那一條（熱點）', async () => {
  const m = await measureAt({ width: 1023 }, streams);
  assert.equal(m.switch.shown, true, '切換鈕要顯示');
  assert.equal(m.reports.shown, true, '目前那一條（熱點）要看得到');
  assert.equal(m.articles.shown, false, '另一條（新文章）要藏起來');
});

test('1024px：視窗 1024 px 時切換鈕隱藏、兩條左右並排（同一個 top、熱點在左）', async () => {
  const m = await measureAt({ width: 1024 }, streams);
  assert.equal(m.switch.shown, false, '並排時切換鈕要隱藏');
  assert.equal(m.reports.shown && m.articles.shown, true, '兩條都要看得到');
  assert.equal(m.reports.top, m.articles.top, '兩條的 top 要相同（左右並排，不是上下疊）');
  assert.ok(m.reports.right <= m.articles.left, `熱點要整條在新文章左邊：熱點 right ${m.reports.right}、新文章 left ${m.articles.left}`);
});

const batchNav = () => {
  const nav = document.getElementById('batch-nav');
  const tops = Array.from(nav.querySelectorAll('button'), b => b.offsetTop);
  nav.scrollLeft = nav.scrollWidth;
  return { buttons: tops.length, rows: [...new Set(tops)], scrolledTo: nav.scrollLeft };
};

test('批次導覽：412 px 時 24 批排成一列（所有按鈕同一個 offsetTop）、可以左右捲', async () => {
  const m = await measureAt({ width: 412, height: 915, reports: 'reports-24.json' }, batchNav);
  assert.equal(m.buttons, 24, '前提：fixture 是 24 批');
  assert.equal(m.rows.length, 1, `窄螢幕不折行，offsetTop 只能有一個值：${m.rows.join(', ')}`);
  assert.ok(m.scrolledTo > 0, `導覽要能橫捲：把 scrollLeft 設成 scrollWidth 之後讀回 ${m.scrolledTo}`);
});

test('批次導覽：1280 px 並排時照週次導覽折行（至少兩個不同的 offsetTop）', async () => {
  const m = await measureAt({ width: 1280, reports: 'reports-24.json' }, batchNav);
  assert.equal(m.buttons, 24, '前提：fixture 是 24 批');
  assert.ok(m.rows.length >= 2, `並排時要折行，offsetTop 只有 ${m.rows.length} 個值：${m.rows.join(', ')}`);
});
